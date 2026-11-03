from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from enrollments.models import Enrollment

from .models import (
    Charge,
    CreditAllocation,
    FamilyAccount,
    PaymentAllocation,
    RecurringChargeSchedule,
    StudioTuitionSettings,
)


def enrollment_tuition_amount(enrollment):
    if enrollment.tuition_override is not None:
        return enrollment.tuition_override

    return (
        enrollment.class_instance.tuition_amount
        or Decimal("0.00")
    )



def _studio_tuition_settings(studio):
    settings_obj, _ = StudioTuitionSettings.objects.get_or_create(studio=studio)
    return settings_obj


def weekly_hours_for_class(class_instance):
    total_minutes = sum(
        meeting.duration_minutes
        for meeting in class_instance.meeting_times.all()
        if meeting.is_active
    )
    return Decimal(total_minutes) / Decimal("60")


def calculate_studio_wide_tuition(settings_obj, weekly_hours):
    weekly_hours = Decimal(weekly_hours or 0)
    if weekly_hours <= 0:
        return Decimal("0.00")

    if settings_obj.studio_wide_method == settings_obj.StudioWideMethod.FLAT_HOURLY:
        amount = weekly_hours * (settings_obj.flat_hourly_rate or Decimal("0.00"))
    else:
        tiers = list(settings_obj.rate_tiers.order_by("hour_number"))
        if not tiers:
            return Decimal("0.00")
        tier_rates = {tier.hour_number: tier.hourly_rate for tier in tiers}
        last_tier = tiers[-1]
        remaining = weekly_hours
        hour_number = 1
        amount = Decimal("0.00")
        while remaining > 0:
            portion = min(remaining, Decimal("1.00"))
            rate = tier_rates.get(hour_number)
            if rate is None:
                if hour_number > last_tier.hour_number:
                    rate = (
                        settings_obj.additional_hour_rate
                        if settings_obj.additional_hour_rate is not None
                        else last_tier.hourly_rate
                    )
                else:
                    previous = [
                        tier.hourly_rate
                        for tier in tiers
                        if tier.hour_number < hour_number
                    ]
                    rate = previous[-1] if previous else Decimal("0.00")
            amount += portion * rate
            remaining -= portion
            hour_number += 1

    if settings_obj.family_monthly_cap is not None:
        amount = min(amount, settings_obj.family_monthly_cap)
    return amount.quantize(Decimal("0.01"))


@transaction.atomic
def sync_studio_wide_billing_for_family(family, season):
    if family is None:
        return {"action": "no_family"}

    studio = family.studio
    settings_obj = _studio_tuition_settings(studio)
    if not settings_obj.is_studio_wide:
        return {"action": "not_studio_wide"}

    policy = settings_obj.default_tuition_plan
    if policy is None:
        return {"action": "missing_policy"}

    account, _ = FamilyAccount.objects.get_or_create(
        family=family, defaults={"studio": studio}
    )

    enrollments = list(
        Enrollment.objects.filter(
            student__family=family,
            class_instance__studio=studio,
            class_instance__season=season,
            status=Enrollment.Status.ACTIVE,
            tuition_override__isnull=True,
            class_instance__tuition_amount__isnull=True,
        )
        .select_related("student", "class_instance", "class_instance__season")
        .prefetch_related("class_instance__meeting_times")
    )

    weekly_hours = sum(
        (weekly_hours_for_class(enrollment.class_instance) for enrollment in enrollments),
        Decimal("0.00"),
    )
    amount = calculate_studio_wide_tuition(settings_obj, weekly_hours)

    schedule = (
        RecurringChargeSchedule.objects.select_for_update()
        .filter(account=account, season=season, universal_tuition=True)
        .first()
    )

    if not enrollments or amount <= Decimal("0.00"):
        if schedule:
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.amount_override = amount
            schedule.save(
                update_fields=[
                    "is_active",
                    "next_charge_date",
                    "amount_override",
                    "updated_at",
                ]
            )
        return {"action": "stopped", "weekly_hours": weekly_hours, "amount": amount}

    schedule, created = RecurringChargeSchedule.objects.update_or_create(
        account=account,
        season=season,
        universal_tuition=True,
        defaults={
            "enrollment": None,
            "student": None,
            "class_instance": None,
            "tuition_plan": policy,
            "schedule_type": RecurringChargeSchedule.ScheduleType.TUITION,
            "start_date": season.start_date,
            "end_date": season.end_date,
            "amount_override": amount,
            "is_active": True,
            "notes": (
                "Automatically managed from the family's active studio-wide "
                "tuition enrollments."
            ),
        },
    )
    if created or schedule.next_charge_date is None:
        schedule.next_charge_date = season.start_date
        schedule.save(update_fields=["next_charge_date", "updated_at"])

    return {
        "action": "studio_wide_schedule",
        "schedule_id": schedule.pk,
        "created": created,
        "weekly_hours": weekly_hours,
        "amount": amount,
    }

def _get_family_account_for_enrollment(enrollment):
    family = enrollment.student.family

    if family is None:
        return None

    account, _ = FamilyAccount.objects.get_or_create(
        family=family,
        defaults={
            "studio": enrollment.class_instance.studio,
        },
    )

    return account


def _description(enrollment, suffix=None):
    class_instance = enrollment.class_instance
    student = enrollment.student

    value = (
        f"{class_instance.name} · "
        f"{student.first_name} {student.last_name}"
    )

    if suffix:
        value += f" · {suffix}"

    return value


def _create_registration_fee_if_needed(
    enrollment,
    account,
):
    class_instance = enrollment.class_instance
    policy = class_instance.tuition_plan

    if (
        policy is None
        or policy.registration_fee <= Decimal("0.00")
    ):
        return None

    existing = Charge.objects.filter(
        enrollment=enrollment,
        charge_type=Charge.ChargeType.REGISTRATION,
    ).first()

    if existing:
        return existing

    return Charge.objects.create(
        account=account,
        enrollment=enrollment,
        student=enrollment.student,
        class_instance=class_instance,
        charge_type=Charge.ChargeType.REGISTRATION,
        description=_description(
            enrollment,
            "Registration Fee",
        ),
        amount=policy.registration_fee,
        due_date=class_instance.season.start_date,
        status=Charge.Status.OPEN,
        notes=(
            "Automatically generated from the class billing policy "
            "when enrollment became active."
        ),
    )


@transaction.atomic
def sync_billing_for_enrollment(enrollment):
    """
    Make billing reflect the Enrollment.

    ACTIVE:
      - Amount comes from Enrollment.tuition_override, otherwise Class.tuition_amount.
      - Dates come from Class.season.
      - Frequency comes from Class.tuition_plan.
      - Monthly/weekly/quarterly creates or activates a recurring schedule.
      - Full Class/Season or One Time creates one tuition charge.

    WAITLISTED/DROPPED/CANCELLED/COMPLETED:
      - future recurring billing is stopped.
      - existing historical charges are not silently deleted.
    """
    enrollment = (
        Enrollment.objects
        .select_for_update()
        .get(pk=enrollment.pk)
    )

    try:
        schedule = enrollment.billing_schedule
    except RecurringChargeSchedule.DoesNotExist:
        schedule = None

    settings_obj = _studio_tuition_settings(enrollment.class_instance.studio)
    uses_studio_wide = (
        settings_obj.is_studio_wide
        and enrollment.tuition_override is None
        and enrollment.class_instance.tuition_amount is None
    )

    if uses_studio_wide:
        if schedule and schedule.is_active:
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.save(
                update_fields=["is_active", "next_charge_date", "updated_at"]
            )

        if enrollment.status == Enrollment.Status.ACTIVE:
            account = _get_family_account_for_enrollment(enrollment)
            if account is not None and settings_obj.default_tuition_plan_id:
                original_policy = enrollment.class_instance.tuition_plan
                if original_policy is None:
                    enrollment.class_instance.tuition_plan = settings_obj.default_tuition_plan
                _create_registration_fee_if_needed(enrollment, account)
                enrollment.class_instance.tuition_plan = original_policy

        return sync_studio_wide_billing_for_family(
            enrollment.student.family, enrollment.class_instance.season
        )

    if enrollment.status != Enrollment.Status.ACTIVE:
        if schedule and schedule.is_active:
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.save(
                update_fields=[
                    "is_active",
                    "next_charge_date",
                    "updated_at",
                ]
            )

        return {
            "action": "stopped",
            "schedule_id": schedule.pk if schedule else None,
        }

    class_instance = enrollment.class_instance
    policy = class_instance.tuition_plan
    amount = enrollment_tuition_amount(enrollment)

    if amount <= Decimal("0.00"):
        if schedule and schedule.is_active:
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.save(
                update_fields=[
                    "is_active",
                    "next_charge_date",
                    "updated_at",
                ]
            )

        return {
            "action": "no_tuition",
        }

    if policy is None:
        return {
            "action": "missing_policy",
        }

    account = _get_family_account_for_enrollment(enrollment)

    if account is None:
        return {
            "action": "no_family_account",
        }

    season = class_instance.season

    _create_registration_fee_if_needed(
        enrollment,
        account,
    )

    if policy.frequency in [
        policy.BillingFrequency.ONE_TIME,
        policy.BillingFrequency.SEASON,
    ]:
        if schedule and schedule.is_active:
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.save(
                update_fields=[
                    "is_active",
                    "next_charge_date",
                    "updated_at",
                ]
            )

        charge, created = Charge.objects.get_or_create(
            enrollment=enrollment,
            charge_type=Charge.ChargeType.TUITION,
            due_date=season.start_date,
            defaults={
                "account": account,
                "student": enrollment.student,
                "class_instance": class_instance,
                "description": _description(
                    enrollment,
                    season.name,
                ),
                "amount": amount,
                "service_period_start": season.start_date,
                "service_period_end": season.end_date,
                "status": Charge.Status.OPEN,
                "notes": (
                    "Automatically generated when the enrollment "
                    "became active."
                ),
            },
        )

        # If not yet paid/credited, keep the single charge synchronized
        # with a changed class price/override.
        if (
            not created
            and charge.paid_amount == Decimal("0.00")
            and charge.credit_amount == Decimal("0.00")
            and charge.status != Charge.Status.VOID
        ):
            charge.amount = amount
            charge.description = _description(
                enrollment,
                season.name,
            )
            charge.save(
                update_fields=[
                    "amount",
                    "description",
                    "updated_at",
                ]
            )
            charge.refresh_status_from_balance()

        return {
            "action": "single_charge",
            "charge_id": charge.pk,
            "created": created,
        }

    schedule, created = RecurringChargeSchedule.objects.update_or_create(
        enrollment=enrollment,
        defaults={
            "account": account,
            "student": enrollment.student,
            "class_instance": class_instance,
            "season": season,
            "tuition_plan": policy,
            "schedule_type": RecurringChargeSchedule.ScheduleType.TUITION,
            "start_date": season.start_date,
            "end_date": season.end_date,
            "amount_override": None,
            "is_active": True,
            "notes": (
                "Automatically managed from the active enrollment. "
                "Price comes from Enrollment override or Class tuition."
            ),
        },
    )

    # Do not reset an already-progressed schedule back to the beginning
    # every time the enrollment saves.
    if created or schedule.next_charge_date is None:
        schedule.next_charge_date = season.start_date
        schedule.save(
            update_fields=[
                "next_charge_date",
                "updated_at",
            ]
        )

    return {
        "action": "recurring_schedule",
        "schedule_id": schedule.pk,
        "created": created,
    }


@transaction.atomic
def allocate_payment_to_oldest_open_charges(payment):
    if payment.status != payment.Status.SUCCEEDED:
        return Decimal("0.00")

    remaining = payment.unallocated_amount

    if remaining <= 0:
        return Decimal("0.00")

    allocated = Decimal("0.00")

    charges = (
        Charge.objects
        .select_for_update()
        .filter(
            account=payment.account,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
            ],
        )
        .order_by("due_date", "created_at")
    )

    for charge in charges:
        if remaining <= 0:
            break

        charge_balance = charge.balance_remaining

        if charge_balance <= 0:
            continue

        amount = min(remaining, charge_balance)

        PaymentAllocation.objects.create(
            payment=payment,
            charge=charge,
            amount=amount,
        )

        allocated += amount
        remaining -= amount

    return allocated


@transaction.atomic
def allocate_credit_to_oldest_open_charges(credit):
    if credit.is_void:
        return Decimal("0.00")

    remaining = credit.remaining_amount

    if remaining <= 0:
        return Decimal("0.00")

    allocated = Decimal("0.00")

    charges = (
        Charge.objects
        .select_for_update()
        .filter(
            account=credit.account,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
            ],
        )
        .order_by("due_date", "created_at")
    )

    for charge in charges:
        if remaining <= 0:
            break

        charge_balance = charge.balance_remaining

        if charge_balance <= 0:
            continue

        amount = min(remaining, charge_balance)

        CreditAllocation.objects.create(
            credit=credit,
            charge=charge,
            amount=amount,
        )

        allocated += amount
        remaining -= amount

    return allocated


def _add_months(date_value, months):
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1

    day = min(
        date_value.day,
        monthrange(year, month)[1],
    )

    return date_value.replace(
        year=year,
        month=month,
        day=day,
    )


def next_schedule_date(schedule, current_date):
    frequency = schedule.tuition_plan.frequency

    if frequency == schedule.tuition_plan.BillingFrequency.WEEKLY:
        return current_date + timedelta(days=7)

    if frequency == schedule.tuition_plan.BillingFrequency.MONTHLY:
        return _add_months(current_date, 1)

    if frequency == schedule.tuition_plan.BillingFrequency.QUARTERLY:
        return _add_months(current_date, 3)

    return None


def _recurring_description(schedule, charge_date):
    if schedule.universal_tuition:
        return (
            f"Studio-Wide Tuition · "
            f"{schedule.account.family.family_name} · "
            f"{charge_date.strftime('%B %Y')}"
        )

    enrollment = schedule.enrollment

    if enrollment:
        return _description(
            enrollment,
            charge_date.strftime("%B %Y"),
        )

    parts = [schedule.tuition_plan.name]

    if schedule.student_id:
        parts.append(
            f"{schedule.student.first_name} {schedule.student.last_name}"
        )

    if schedule.class_instance_id:
        parts.append(schedule.class_instance.name)

    parts.append(charge_date.strftime("%B %Y"))

    return " · ".join(parts)


@transaction.atomic
def generate_due_recurring_charges(
    studio=None,
    as_of_date=None,
):
    as_of_date = as_of_date or timezone.localdate()

    schedules = (
        RecurringChargeSchedule.objects
        .select_for_update(of=("self",))
        .select_related(
            "account",
            "account__family",
            "enrollment",
            "enrollment__student",
            "enrollment__class_instance",
            "student",
            "class_instance",
            "season",
            "tuition_plan",
        )
        .filter(
            is_active=True,
            next_charge_date__isnull=False,
            next_charge_date__lte=as_of_date,
        )
    )

    if studio is not None:
        schedules = schedules.filter(
            account__studio=studio,
        )

    created = 0
    skipped = 0
    processed_schedules = 0

    for schedule in schedules:
        processed_schedules += 1

        # Enrollment-driven schedules only bill while active.
        if (
            schedule.enrollment_id
            and schedule.enrollment.status != Enrollment.Status.ACTIVE
        ):
            schedule.is_active = False
            schedule.next_charge_date = None
            schedule.save(
                update_fields=[
                    "is_active",
                    "next_charge_date",
                    "updated_at",
                ]
            )
            continue

        charge_date = schedule.next_charge_date

        while (
            charge_date
            and charge_date <= as_of_date
            and (
                schedule.end_date is None
                or charge_date <= schedule.end_date
            )
        ):
            exists = Charge.objects.filter(
                recurring_schedule=schedule,
                due_date=charge_date,
            ).exists()

            if exists:
                skipped += 1
            else:
                Charge.objects.create(
                    account=schedule.account,
                    enrollment=schedule.enrollment,
                    student=schedule.student,
                    class_instance=schedule.class_instance,
                    recurring_schedule=schedule,
                    charge_type=Charge.ChargeType.TUITION,
                    description=_recurring_description(
                        schedule,
                        charge_date,
                    ),
                    amount=schedule.amount,
                    due_date=charge_date,
                    service_period_start=charge_date,
                    status=Charge.Status.OPEN,
                    notes=(
                        "Automatically generated by Encore recurring billing."
                    ),
                )

                created += 1

            next_date = next_schedule_date(
                schedule,
                charge_date,
            )

            if (
                next_date is None
                or (
                    schedule.end_date
                    and next_date > schedule.end_date
                )
            ):
                schedule.next_charge_date = None
                schedule.is_active = False
                schedule.save(
                    update_fields=[
                        "next_charge_date",
                        "is_active",
                        "updated_at",
                    ]
                )
                charge_date = None
                break

            schedule.next_charge_date = next_date
            schedule.save(
                update_fields=[
                    "next_charge_date",
                    "updated_at",
                ]
            )

            charge_date = next_date

    return {
        "created": created,
        "skipped": skipped,
        "processed_schedules": processed_schedules,
    }
