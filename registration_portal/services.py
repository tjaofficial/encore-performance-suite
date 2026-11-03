from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from classes.models import Class
from enrollments.models import Enrollment
from families.models import Family, Guardian
from students.models import Student
from studios.models import StudioMembership
from billing.models import (
    Charge,
    FamilyAccount,
    Payment,
    PaymentAllocation,
    RecurringChargeSchedule,
    StudioTuitionSettings,
)
from billing.services import (
    next_schedule_date,
    sync_billing_for_enrollment,
    calculate_studio_wide_tuition,
    weekly_hours_for_class,
)
from .security import registration_identity_verified
from .policy_services import (
    link_policy_acceptances_to_completed_registration,
    registration_policies_satisfied,
)


def matching_guardian_for_request(
    registration_request,
):
    return (
        Guardian.objects
        .filter(
            family__studio=registration_request.studio,
            email__iexact=registration_request.email,
            is_active=True,
        )
        .select_related(
            "family",
            "user",
        )
        .first()
    )


def matching_user_for_request(
    registration_request,
):
    return (
        User.objects
        .filter(
            email__iexact=registration_request.email,
            is_active=True,
        )
        .first()
    )


def matching_student_for_request(
    registration_request,
    family,
):
    return (
        Student.objects
        .filter(
            studio=registration_request.studio,
            family=family,
            first_name__iexact=registration_request.student_first_name,
            last_name__iexact=registration_request.student_last_name,
            birthday=registration_request.student_birthday,
        )
        .first()
    )


def enrollment_status_for_class(
    class_instance,
):
    active_count = (
        Enrollment.objects
        .filter(
            class_instance=class_instance,
            status=Enrollment.Status.ACTIVE,
        )
        .count()
    )

    if (
        class_instance.capacity
        and active_count
        >= class_instance.capacity
    ):
        return Enrollment.Status.WAITLISTED

    return Enrollment.Status.ACTIVE


def _field_names(model):
    return {
        field.name
        for field
        in model._meta.get_fields()
        if getattr(
            field,
            "concrete",
            False,
        )
    }


def _new_family(
    *,
    studio,
    last_name,
):
    """
    Only set fields that exist in the current Family model.

    This protects the signup flow from prototype-era naming drift while
    still using the actual current Encore model.
    """
    fields = _field_names(Family)

    payload = {
        "studio": studio,
    }

    if "family_name" in fields:
        payload[
            "family_name"
        ] = f"{last_name} Family"

    if "is_active" in fields:
        payload[
            "is_active"
        ] = True

    family = Family(
        **payload
    )

    family.full_clean()
    family.save()

    return family


def _new_guardian(
    *,
    family,
    user,
    first_name,
    last_name,
    email,
    phone="",
    is_primary=True,
):
    fields = _field_names(Guardian)

    payload = {
        "family": family,
    }

    optional = {
        "user": user,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "is_active": True,
        "is_primary": is_primary,
        "can_manage_account": True,
        "can_register_students": True,
    }

    for name, value in optional.items():
        if name in fields:
            payload[name] = value

    guardian = Guardian(
        **payload
    )

    guardian.full_clean()
    guardian.save()

    return guardian


def _new_student_from_request(
    *,
    registration_request,
    family,
):
    fields = _field_names(Student)

    payload = {
        "studio": registration_request.studio,
        "family": family,
        "first_name": (
            registration_request.student_first_name
        ),
        "last_name": (
            registration_request.student_last_name
        ),
        "birthday": (
            registration_request.student_birthday
        ),
    }

    if "is_active" in fields:
        payload[
            "is_active"
        ] = True

    student = Student(
        **payload
    )

    student.full_clean()
    student.save()

    return student


def _family_membership(
    *,
    user,
    studio,
):
    membership, created = (
        StudioMembership.objects
        .get_or_create(
            user=user,
            studio=studio,
            role="family",
            defaults={
                "is_active": True,
            },
        )
    )

    if (
        hasattr(
            membership,
            "is_active",
        )
        and not membership.is_active
    ):
        membership.is_active = True
        membership.save(
            update_fields=[
                "is_active",
            ]
        )

    return membership


@transaction.atomic
def create_new_family_from_request(
    *,
    registration_request,
    password,
):
    existing_user = (
        User.objects
        .filter(
            email__iexact=registration_request.email,
        )
        .first()
    )

    if existing_user is not None:
        raise ValueError(
            "An Encore user already exists for this email."
        )

    user = User.objects.create_user(
        username=registration_request.email,
        email=registration_request.email,
        password=password,
        first_name=registration_request.guardian_first_name,
        last_name=registration_request.guardian_last_name,
    )

    family = _new_family(
        studio=registration_request.studio,
        last_name=registration_request.guardian_last_name,
    )

    _new_guardian(
        family=family,
        user=user,
        first_name=registration_request.guardian_first_name,
        last_name=registration_request.guardian_last_name,
        email=registration_request.email,
        phone=registration_request.phone,
    )

    _family_membership(
        user=user,
        studio=registration_request.studio,
    )

    student = _new_student_from_request(
        registration_request=registration_request,
        family=family,
    )

    status = enrollment_status_for_class(
        registration_request.class_instance
    )

    enrollment = Enrollment(
        student=student,
        class_instance=registration_request.class_instance,
        status=status,
        source=Enrollment.Source.ONLINE,
    )

    enrollment.full_clean()
    enrollment.save()

    registration_request.status = (
        registration_request.Status.CONVERTED
    )

    registration_request.linked_family = (
        family
    )

    registration_request.linked_student = (
        student
    )

    registration_request.linked_enrollment = (
        enrollment
    )

    registration_request.save(
        update_fields=[
            "status",
            "linked_family",
            "linked_student",
            "linked_enrollment",
            "updated_at",
        ]
    )

    return {
        "user": user,
        "family": family,
        "student": student,
        "enrollment": enrollment,
    }


@transaction.atomic
def convert_request_for_existing_family(
    *,
    registration_request,
    family,
    student=None,
):
    created_student = False

    if student is None:
        student = matching_student_for_request(
            registration_request,
            family,
        )

    if student is None:
        student = _new_student_from_request(
            registration_request=registration_request,
            family=family,
        )
        created_student = True

    existing_enrollment = (
        Enrollment.objects
        .filter(
            student=student,
            class_instance=registration_request.class_instance,
        )
        .first()
    )

    if existing_enrollment:
        enrollment = existing_enrollment
        created_enrollment = False
    else:
        enrollment = Enrollment(
            student=student,
            class_instance=registration_request.class_instance,
            status=enrollment_status_for_class(
                registration_request.class_instance
            ),
            source=Enrollment.Source.ONLINE,
        )

        enrollment.full_clean()
        enrollment.save()
        created_enrollment = True

    registration_request.status = (
        registration_request.Status.CONVERTED
    )
    registration_request.linked_family = family
    registration_request.linked_student = student
    registration_request.linked_enrollment = enrollment
    registration_request.save(
        update_fields=[
            "status",
            "linked_family",
            "linked_student",
            "linked_enrollment",
            "updated_at",
        ]
    )

    return {
        "student": student,
        "enrollment": enrollment,
        "created_student": created_student,
        "created_enrollment": created_enrollment,
    }


@transaction.atomic
def accept_family_invite(
    *,
    invite,
    password,
):
    if not invite.is_usable:
        raise ValueError(
            "This invite is no longer valid."
        )

    user = (
        User.objects
        .filter(
            email__iexact=invite.email,
        )
        .first()
    )

    if user is None:
        user = User.objects.create_user(
            username=invite.email,
            email=invite.email,
            password=password,
            first_name=invite.guardian_first_name,
            last_name=invite.guardian_last_name,
        )
    else:
        user.set_password(
            password
        )

        user.is_active = True

        user.save(
            update_fields=[
                "password",
                "is_active",
            ]
        )

    family = invite.family

    if family is None:
        family = _new_family(
            studio=invite.studio,
            last_name=(
                invite.guardian_last_name
                or "Encore"
            ),
        )

        invite.family = family

    guardian = (
        Guardian.objects
        .filter(
            family=family,
            email__iexact=invite.email,
        )
        .first()
    )

    if guardian is None:
        guardian = _new_guardian(
            family=family,
            user=user,
            first_name=invite.guardian_first_name,
            last_name=invite.guardian_last_name,
            email=invite.email,
            is_primary=not family.guardians.filter(
                is_primary=True,
                is_active=True,
            ).exists(),
        )
    elif hasattr(
        guardian,
        "user_id",
    ):
        guardian.user = user
        guardian.save(
            update_fields=[
                "user",
            ]
        )

    _family_membership(
        user=user,
        studio=invite.studio,
    )

    invite.accepted_at = (
        timezone.now()
    )

    invite.save(
        update_fields=[
            "family",
            "accepted_at",
        ]
    )

    return {
        "user": user,
        "family": family,
        "guardian": guardian,
    }


def _registration_student_payloads(registration_session):
    raw = registration_session.student_data or {}
    if isinstance(raw.get("students"), list):
        students = [dict(item) for item in raw.get("students", [])]
        assignments = {
            str(key): [int(value) for value in values if str(value).isdigit()]
            for key, values in (raw.get("assignments") or {}).items()
            if isinstance(values, list)
        }
        return students, assignments

    if raw:
        item = dict(raw)
        item.setdefault("draft_key", "legacy-student")
        return [item], {
            item["draft_key"]: list(
                registration_session.selected_classes.values_list("pk", flat=True)
            )
        }

    return [], {}


def _registration_student_name(student):
    first_name = (
        student.get("student_first_name")
        or student.get("first_name")
        or ""
    )
    last_name = (
        student.get("student_last_name")
        or student.get("last_name")
        or ""
    )
    return f"{first_name} {last_name}".strip() or "Student"


def registration_pricing_snapshot(
    registration_session,
    *,
    waitlisted_class_ids=None,
):
    from .addon_services import is_addon, addon_pricing_snapshot
    if is_addon(registration_session):
        return addon_pricing_snapshot(registration_session, waitlisted_class_ids=waitlisted_class_ids)
    waitlisted_class_ids = set(waitlisted_class_ids or [])
    students, assignments = _registration_student_payloads(
        registration_session
    )

    all_class_ids = {
        int(class_id)
        for values in assignments.values()
        for class_id in values
        if str(class_id).isdigit()
    }
    if not all_class_ids:
        all_class_ids = set(
            registration_session.selected_classes.values_list("pk", flat=True)
        )

    classes = {
        class_instance.pk: class_instance
        for class_instance in Class.objects.filter(
            studio=registration_session.studio,
            pk__in=all_class_ids,
        ).select_related(
            "season",
            "tuition_plan",
            "class_type",
        ).prefetch_related("meeting_times")
    }

    settings_obj = getattr(registration_session.studio, "settings", None)
    allow_waitlist = (
        settings_obj.allow_waitlist_requests
        if settings_obj is not None
        else True
    )
    tuition_settings = StudioTuitionSettings.objects.filter(
        studio=registration_session.studio
    ).select_related("default_tuition_plan").first()

    rows = []
    due_today = Decimal("0.00")
    recurring_total = Decimal("0.00")
    student_totals = []
    studio_wide_by_season = {}

    if not students and classes:
        students = [{
            "draft_key": "legacy-student",
            "student_first_name": "Student",
        }]
        assignments = {
            "legacy-student": sorted(classes.keys())
        }

    for student in students:
        student_key = student.get("draft_key", "legacy-student")
        student_name = _registration_student_name(student)
        student_monthly = Decimal("0.00")
        student_due = Decimal("0.00")

        for class_id in assignments.get(student_key, []):
            class_instance = classes.get(int(class_id))
            if class_instance is None:
                continue

            is_waitlisted = class_instance.pk in waitlisted_class_ids
            if not waitlisted_class_ids:
                is_waitlisted = class_instance.is_full
            waitlist = is_waitlisted and allow_waitlist

            policy = class_instance.tuition_plan
            registration_fee = (
                policy.registration_fee
                if policy is not None
                else Decimal("0.00")
            )
            if is_waitlisted:
                registration_fee = Decimal("0.00")

            tuition = class_instance.tuition_amount
            uses_studio_wide = bool(
                tuition is None
                and tuition_settings is not None
                and tuition_settings.is_studio_wide
            )

            class_due = Decimal("0.00")
            class_recurring = Decimal("0.00")
            frequency = (
                policy.get_frequency_display()
                if policy is not None
                else "Tuition policy not set"
            )

            if uses_studio_wide and not is_waitlisted:
                season_bucket = studio_wide_by_season.setdefault(
                    class_instance.season_id,
                    {
                        "season": class_instance.season,
                        "weekly_hours": Decimal("0.00"),
                    },
                )
                season_bucket["weekly_hours"] += weekly_hours_for_class(
                    class_instance
                )
            elif tuition is not None and not is_waitlisted:
                tuition = Decimal(tuition)
                class_due = tuition
                if policy is not None and policy.frequency in {
                    policy.BillingFrequency.WEEKLY,
                    policy.BillingFrequency.MONTHLY,
                    policy.BillingFrequency.QUARTERLY,
                }:
                    class_recurring = tuition
                    recurring_total += tuition
                    if policy.frequency == policy.BillingFrequency.MONTHLY:
                        student_monthly += tuition

            row_due = class_due + registration_fee
            due_today += row_due
            student_due += row_due

            rows.append({
                "student_key": student_key,
                "student_name": student_name,
                "class_id": class_instance.pk,
                "class_code": class_instance.class_id,
                "class_name": class_instance.name,
                "season": class_instance.season.name,
                "frequency": frequency,
                "tuition": str(tuition or Decimal("0.00")),
                "registration_fee": str(registration_fee),
                "due_today": str(row_due),
                "future_recurring": str(class_recurring),
                "is_full": is_waitlisted,
                "waitlist": waitlist,
                "studio_wide": uses_studio_wide,
            })

        student_totals.append({
            "student_key": student_key,
            "student_name": student_name,
            "due_today": str(student_due),
            "estimated_monthly": str(student_monthly),
        })

    studio_wide_rows = []
    if tuition_settings is not None and tuition_settings.is_studio_wide:
        for season_id, bucket in studio_wide_by_season.items():
            amount = calculate_studio_wide_tuition(
                tuition_settings,
                bucket["weekly_hours"],
            )
            recurring_total += amount
            due_today += amount
            studio_wide_rows.append({
                "season_id": season_id,
                "season": bucket["season"].name,
                "weekly_hours": str(bucket["weekly_hours"]),
                "amount": str(amount),
                "due_today": str(amount),
                "frequency": (
                    tuition_settings.default_tuition_plan.get_frequency_display()
                    if tuition_settings.default_tuition_plan_id
                    else "Monthly"
                ),
            })

    snapshot = {
        "items": rows,
        "student_totals": student_totals,
        "studio_wide_items": studio_wide_rows,
        "due_today": str(due_today.quantize(Decimal("0.01"))),
        "future_recurring_total": str(
            recurring_total.quantize(Decimal("0.01"))
        ),
        "estimated_monthly_total": str(
            recurring_total.quantize(Decimal("0.01"))
        ),
        "currency": "USD",
    }

    registration_session.pricing_snapshot = snapshot
    registration_session.save(
        update_fields=["pricing_snapshot", "updated_at"]
    )
    return snapshot

def _unique_username(email):
    User = get_user_model()

    base = email.strip().lower()
    candidate = base
    counter = 2

    while User.objects.filter(
        username=candidate,
    ).exists():
        candidate = f"{base}-{counter}"
        counter += 1

    return candidate


def _create_user_from_hash(
    *,
    email,
    first_name,
    last_name,
    password_hash,
):
    User = get_user_model()

    user = User(
        username=_unique_username(email),
        email=email.strip().lower(),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
    )
    user.password = password_hash
    user.full_clean()
    user.save()

    return user


def _family_from_registration(
    registration_session,
):
    data = registration_session.account_data

    if (
        registration_session.registration_type
        == registration_session.RegistrationType.SELF
    ):
        first_name = data.get(
            "first_name",
            "",
        )
        last_name = data.get(
            "last_name",
            "",
        )
        family_name = (
            f"{last_name} Household"
            if last_name
            else "Adult Student Household"
        )
    else:
        first_name = data.get(
            "guardian_first_name",
            "",
        )
        last_name = data.get(
            "guardian_last_name",
            "",
        )
        family_name = (
            data.get("family_name")
            or (
                f"{last_name} Family"
                if last_name
                else "Encore Family"
            )
        )

    return Family.objects.create(
        studio=registration_session.studio,
        family_name=family_name,
        primary_contact_first_name=first_name,
        primary_contact_last_name=last_name,
        primary_email=data.get("email", ""),
        primary_phone=data.get("phone", ""),
        address_line_1=data.get("address_line_1", ""),
        address_line_2=data.get("address_line_2", ""),
        city=data.get("city", ""),
        state=data.get("state", ""),
        postal_code=data.get("postal_code", ""),
        emergency_contact_name=data.get(
            "emergency_contact_name",
            "",
        ),
        emergency_contact_phone=data.get(
            "emergency_contact_phone",
            "",
        ),
        emergency_contact_relationship=data.get(
            "emergency_contact_relationship",
            "",
        ),
        how_did_you_hear_about_us=data.get(
            "how_did_you_hear_about_us",
            "",
        ),
        is_active=True,
    )


def _student_from_registration(
    registration_session,
    *,
    family,
    student_user=None,
):
    data = registration_session.student_data

    if (
        registration_session.registration_type
        == registration_session.RegistrationType.SELF
    ):
        first_name = registration_session.account_data.get(
            "first_name",
            "",
        )
        last_name = registration_session.account_data.get(
            "last_name",
            "",
        )
    else:
        first_name = data.get(
            "student_first_name",
            "",
        )
        last_name = data.get(
            "student_last_name",
            "",
        )

    student = Student(
        studio=registration_session.studio,
        family=family,
        user=student_user,
        first_name=first_name,
        last_name=last_name,
        birthday=data["birthday"],
        gender=data.get("gender", ""),
        medical_conditions=data.get(
            "medical_conditions",
            "",
        ),
        allergies=data.get(
            "allergies",
            "",
        ),
        comments=data.get(
            "comments",
            "",
        ),
        emergency_contact_name=registration_session.account_data.get(
            "emergency_contact_name",
            "",
        ),
        emergency_contact_phone=registration_session.account_data.get(
            "emergency_contact_phone",
            "",
        ),
        emergency_contact_relationship=registration_session.account_data.get(
            "emergency_contact_relationship",
            "",
        ),
        how_did_you_hear_about_us=registration_session.account_data.get(
            "how_did_you_hear_about_us",
            "",
        ),
        is_active=True,
    )
    student.full_clean()
    student.save()

    return student


def _ensure_first_recurring_tuition_charge(
    enrollment,
):
    try:
        schedule = enrollment.billing_schedule
    except Exception:
        return None

    if not schedule or not schedule.is_active:
        return None

    today = timezone.localdate()
    season_start = enrollment.class_instance.season.start_date

    cycle_date = season_start

    while True:
        candidate = next_schedule_date(
            schedule,
            cycle_date,
        )

        if candidate is None:
            break

        if candidate > today:
            schedule.next_charge_date = candidate
            break

        cycle_date = candidate

    if schedule.next_charge_date is None:
        schedule.is_active = False

    schedule.save(
        update_fields=[
            "next_charge_date",
            "is_active",
            "updated_at",
        ]
    )

    charge, _created = Charge.objects.get_or_create(
        enrollment=enrollment,
        recurring_schedule=schedule,
        charge_type=Charge.ChargeType.TUITION,
        due_date=today,
        defaults={
            "account": schedule.account,
            "student": enrollment.student,
            "class_instance": enrollment.class_instance,
            "description": (
                f"{enrollment.class_instance.name} · "
                f"{enrollment.student.first_name} "
                f"{enrollment.student.last_name} · "
                "Initial Tuition"
            ),
            "amount": enrollment.tuition_amount
            or Decimal("0.00"),
            "service_period_start": max(
                season_start,
                cycle_date,
            ),
            "status": Charge.Status.OPEN,
            "notes": (
                "Initial tuition collected during online registration."
            ),
        },
    )

    return charge


def _registration_charges_for_enrollment(
    enrollment,
):
    billing_result = sync_billing_for_enrollment(
        enrollment
    )

    charges = list(
        Charge.objects
        .filter(
            enrollment=enrollment,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
                Charge.Status.PAID,
            ],
        )
        .order_by(
            "charge_type",
            "created_at",
        )
    )

    if (
        billing_result.get("action")
        == "recurring_schedule"
    ):
        first_charge = (
            _ensure_first_recurring_tuition_charge(
                enrollment
            )
        )

        if (
            first_charge
            and first_charge not in charges
        ):
            charges.append(
                first_charge
            )

    return charges


def _send_registration_confirmation(
    registration_session,
    *,
    enrollments,
    payment,
):
    try:
        from communications.email_service import send_email
    except ImportError:
        return None

    recipient = registration_session.contact_email
    if not recipient:
        return None

    is_additional_classes = (registration_session.account_data or {}).get('registration_flow') == 'add_classes'
    confirmation_heading = ('Additional classes confirmed' if is_additional_classes
                            else 'Registration confirmed')
    login_url = f"{settings.ENCORE_BASE_URL}/accounts/login/"
    enrollments = list(enrollments)
    class_lines = "".join(
        (
            f"<li><strong>{enrollment.student.first_name} "
            f"{enrollment.student.last_name}</strong> — "
            f"{enrollment.class_instance.name} "
            f"({enrollment.get_status_display()})</li>"
        )
        for enrollment in enrollments
    )
    payment_line = (
        f"<p><strong>Payment:</strong> ${payment.amount} USD</p>"
        if payment is not None
        else "<p><strong>Payment:</strong> No online payment was collected today.</p>"
    )

    html_body = (
        f"<h2>{confirmation_heading} with {registration_session.studio.name}</h2>"
        f"<p>{'Your additional classes are confirmed.' if is_additional_classes else 'Your family registration is complete.'}</p>"
        f"<h3>Students & Classes</h3><ul>{class_lines}</ul>"
        f"{payment_line}"
        f"<h3>Using Encore</h3>"
        f"<p>Go to <a href='{login_url}'>Encore</a> and sign in "
        f"with {recipient} to view students, classes, billing, and studio updates.</p>"
    )

    text_classes = "\n".join(
        (
            f"- {enrollment.student.first_name} {enrollment.student.last_name}: "
            f"{enrollment.class_instance.name} "
            f"({enrollment.get_status_display()})"
        )
        for enrollment in enrollments
    )
    text_body = (
        f"{confirmation_heading} with {registration_session.studio.name}\n\n"
        f"Students & Classes:\n{text_classes}\n\n"
        + (
            f"Payment: ${payment.amount} USD\n\n"
            if payment is not None
            else "Payment: No online payment was collected today.\n\n"
        )
        + f"Sign in to Encore at {login_url} using {recipient}."
    )

    return send_email(
        to=[recipient],
        subject=f"{confirmation_heading} - {registration_session.studio.name}",
        html_body=html_body,
        text_body=text_body,
        tags={
            "message_type": "registration_confirmation",
            "studio_id": registration_session.studio_id,
        },
    )


def _student_from_payload(
    registration_session,
    payload,
    *,
    family,
    student_user=None,
):
    student = Student(
        studio=registration_session.studio,
        family=family,
        user=student_user,
        first_name=payload.get("student_first_name", ""),
        last_name=payload.get("student_last_name", ""),
        birthday=payload["birthday"],
        gender=payload.get("gender", ""),
        medical_conditions=payload.get("medical_conditions", ""),
        allergies=payload.get("allergies", ""),
        comments=payload.get("comments", ""),
        emergency_contact_name=registration_session.account_data.get(
            "emergency_contact_name", ""
        ),
        emergency_contact_phone=registration_session.account_data.get(
            "emergency_contact_phone", ""
        ),
        emergency_contact_relationship=registration_session.account_data.get(
            "emergency_contact_relationship", ""
        ),
        how_did_you_hear_about_us=registration_session.account_data.get(
            "how_did_you_hear_about_us", ""
        ),
        is_active=True,
    )
    student.full_clean()
    student.save()
    return student


def _initial_universal_tuition_charge(schedule):
    if not schedule or not schedule.is_active:
        return None

    today = timezone.localdate()
    charge, _created = Charge.objects.get_or_create(
        account=schedule.account,
        recurring_schedule=schedule,
        charge_type=Charge.ChargeType.TUITION,
        due_date=today,
        defaults={
            "student": None,
            "class_instance": None,
            "description": (
                f"Studio-Wide Tuition · {schedule.season.name if schedule.season else 'Registration'}"
            ),
            "amount": schedule.amount,
            "service_period_start": today,
            "status": Charge.Status.OPEN,
            "notes": "Initial studio-wide tuition collected during online registration.",
        },
    )

    cycle_date = schedule.start_date
    while True:
        candidate = next_schedule_date(schedule, cycle_date)
        if candidate is None:
            schedule.next_charge_date = None
            schedule.is_active = False
            break
        if candidate > today:
            schedule.next_charge_date = candidate
            break
        cycle_date = candidate

    schedule.save(
        update_fields=["next_charge_date", "is_active", "updated_at"]
    )
    return charge


@transaction.atomic
def finalize_public_registration(
    registration_session,
    *,
    stripe_payment_intent_id="",
    paid_amount=Decimal("0.00"),
):
    from .models import RegistrationClassHold
    from .addon_services import is_addon, finalize_addon
    if is_addon(registration_session):
        return finalize_addon(registration_session, stripe_payment_intent_id=stripe_payment_intent_id, paid_amount=paid_amount)

    registration_session = (
        registration_session.__class__.objects
        .select_for_update()
        .select_related("studio")
        .get(pk=registration_session.pk)
    )

    if registration_session.status == registration_session.Status.COMPLETED:
        enrollments = list(
            Enrollment.objects.filter(
                student__family=registration_session.linked_family,
                class_instance__studio=registration_session.studio,
                enrolled_at__gte=registration_session.created_at,
            ).select_related("student", "class_instance")
        )
        return {
            "user": registration_session.linked_user,
            "family": registration_session.linked_family,
            "students": list(
                Student.objects.filter(
                    family=registration_session.linked_family,
                    studio=registration_session.studio,
                )
            ),
            "payment": registration_session.linked_payment,
            "enrollments": enrollments,
        }

    from .approval_codes import validate_session as validate_class_codes, consume_session as consume_class_codes
    validate_class_codes(registration_session)

    if not registration_identity_verified(registration_session):
        raise ValueError(
            "This registration must verify its email before permanent records can be created."
        )

    if not registration_policies_satisfied(registration_session):
        raise ValueError(
            "Required registration policies must be accepted before permanent records can be created."
        )

    account_data = registration_session.account_data
    User = get_user_model()
    existing_user_id = account_data.get("existing_user_id")
    if existing_user_id:
        account_user = User.objects.get(pk=existing_user_id, is_active=True)
    else:
        account_user = _create_user_from_hash(
            email=account_data["email"],
            first_name=(
                account_data.get("first_name")
                or account_data.get("guardian_first_name")
                or ""
            ),
            last_name=(
                account_data.get("last_name")
                or account_data.get("guardian_last_name")
                or ""
            ),
            password_hash=account_data["password_hash"],
        )

    existing_family_id = account_data.get("existing_family_id")
    if existing_family_id:
        family = Family.objects.get(
            pk=existing_family_id,
            studio=registration_session.studio,
            is_active=True,
        )
    else:
        family = _family_from_registration(registration_session)

    if (
        registration_session.registration_type
        == registration_session.RegistrationType.STUDENT
    ):
        existing_guardian_id = account_data.get("existing_guardian_id")
        if existing_guardian_id:
            Guardian.objects.get(
                pk=existing_guardian_id,
                family=family,
                user=account_user,
                is_active=True,
            )
        else:
            Guardian.objects.create(
                family=family,
                user=account_user,
                first_name=account_data.get("guardian_first_name", ""),
                last_name=account_data.get("guardian_last_name", ""),
                relationship=account_data.get("guardian_relationship", ""),
                email=account_data.get("email", ""),
                phone=account_data.get("phone", ""),
                is_primary=True,
                is_financially_responsible=True,
                is_active=True,
            )
        StudioMembership.objects.get_or_create(
            user=account_user,
            studio=registration_session.studio,
            role=StudioMembership.Role.FAMILY,
            defaults={"is_active": True},
        )

    students_payload, assignments = _registration_student_payloads(
        registration_session
    )
    if not students_payload:
        raise ValueError("This registration does not contain any students.")

    if (
        registration_session.registration_type
        == registration_session.RegistrationType.SELF
    ):
        StudioMembership.objects.get_or_create(
            user=account_user,
            studio=registration_session.studio,
            role=StudioMembership.Role.STUDENT,
            defaults={"is_active": True},
        )

    created_students = []
    student_by_key = {}
    for payload in students_payload:
        key = payload.get("draft_key") or f"student-{len(created_students) + 1}"
        existing_student_id = payload.get("existing_student_id")
        if existing_student_id:
            student = Student.objects.get(
                pk=existing_student_id,
                studio=registration_session.studio,
                family=family,
                is_active=True,
            )
        else:
            student_user = None
            if (
                registration_session.registration_type
                == registration_session.RegistrationType.SELF
                and len(created_students) == 0
            ):
                student_user = account_user
            elif payload.get("create_student_login"):
                student_user = _create_user_from_hash(
                    email=payload["student_email"],
                    first_name=payload.get("student_first_name", ""),
                    last_name=payload.get("student_last_name", ""),
                    password_hash=payload["student_password_hash"],
                )
                StudioMembership.objects.get_or_create(
                    user=student_user,
                    studio=registration_session.studio,
                    role=StudioMembership.Role.STUDENT,
                    defaults={"is_active": True},
                )
            student = _student_from_payload(
                registration_session,
                payload,
                family=family,
                student_user=student_user,
            )

        created_students.append(student)
        student_by_key[key] = student

    family_account, _created = FamilyAccount.objects.get_or_create(
        family=family,
        defaults={
            "studio": registration_session.studio,
            "is_active": True,
        },
    )

    pricing_by_student_class = {
        (str(item.get("student_key")), int(item["class_id"])): item
        for item in registration_session.pricing_snapshot.get("items", [])
        if item.get("class_id") is not None
    }

    enrollments = []
    charges_to_pay = []
    for key, student in student_by_key.items():
        for class_id in assignments.get(key, []):
            class_instance = Class.objects.select_related(
                "season", "tuition_plan"
            ).get(
                pk=class_id,
                studio=registration_session.studio,
            )
            item = pricing_by_student_class.get((str(key), class_instance.pk), {})
            should_waitlist = bool(item.get("waitlist"))
            status = (
                Enrollment.Status.WAITLISTED
                if should_waitlist or class_instance.is_full
                else Enrollment.Status.ACTIVE
            )

            enrollment, created = Enrollment.objects.get_or_create(
                student=student,
                class_instance=class_instance,
                defaults={
                    "status": status,
                    "source": Enrollment.Source.ONLINE,
                },
            )
            if not created and enrollment.status in {
                Enrollment.Status.DROPPED,
                Enrollment.Status.CANCELLED,
                Enrollment.Status.COMPLETED,
            }:
                enrollment.status = status
                enrollment.source = Enrollment.Source.ONLINE
                enrollment.full_clean()
                enrollment.save(
                    update_fields=["status", "source", "updated_at"]
                )

            enrollments.append(enrollment)
            if status == Enrollment.Status.ACTIVE:
                charges_to_pay.extend(
                    _registration_charges_for_enrollment(enrollment)
                )

    for schedule in RecurringChargeSchedule.objects.filter(
        account=family_account,
        universal_tuition=True,
        is_active=True,
    ).select_related("season", "tuition_plan"):
        charge = _initial_universal_tuition_charge(schedule)
        if charge is not None:
            charges_to_pay.append(charge)

    payment = None
    if paid_amount > Decimal("0.00"):
        payment = Payment(
            account=family_account,
            amount=paid_amount,
            method=Payment.Method.CARD,
            status=Payment.Status.SUCCEEDED,
            external_reference=stripe_payment_intent_id,
            notes="Online registration payment processed through Stripe.",
        )
        payment.full_clean()
        payment.save()

        remaining = paid_amount
        unique_charges = []
        seen_charge_ids = set()
        for charge in charges_to_pay:
            if charge.pk in seen_charge_ids:
                continue
            seen_charge_ids.add(charge.pk)
            unique_charges.append(charge)
        unique_charges.sort(
            key=lambda charge: (
                charge.due_date or timezone.localdate(),
                charge.created_at,
            )
        )
        for charge in unique_charges:
            if remaining <= Decimal("0.00"):
                break
            balance = charge.balance_remaining
            if balance <= Decimal("0.00"):
                continue
            amount = min(remaining, balance)
            PaymentAllocation.objects.create(
                payment=payment,
                charge=charge,
                amount=amount,
            )
            remaining -= amount

    RegistrationClassHold.objects.filter(
        registration_session=registration_session,
    ).update(is_active=False)

    registration_session.linked_user = account_user
    registration_session.linked_family = family
    registration_session.linked_student = created_students[0]
    registration_session.linked_payment = payment
    registration_session.stripe_payment_intent_id = stripe_payment_intent_id
    consume_class_codes(registration_session)
    registration_session.status = registration_session.Status.COMPLETED
    registration_session.current_step = "complete"
    registration_session.finalized_at = timezone.now()
    registration_session.save(
        update_fields=[
            "linked_user",
            "linked_family",
            "linked_student",
            "linked_payment",
            "stripe_payment_intent_id",
            "status",
            "current_step",
            "finalized_at",
            "updated_at",
        ]
    )

    link_policy_acceptances_to_completed_registration(
        registration_session,
        user=account_user,
        family=family,
    )

    transaction.on_commit(
        lambda: _send_registration_confirmation(
            registration_session,
            enrollments=enrollments,
            payment=payment,
        )
    )

    return {
        "user": account_user,
        "family": family,
        "students": created_students,
        "student": created_students[0],
        "payment": payment,
        "enrollments": enrollments,
    }
