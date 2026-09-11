from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from enrollments.models import Enrollment
from families.models import Family, Guardian
from students.models import Student
from studios.models import StudioMembership
from billing.models import (
    Charge,
    FamilyAccount,
    Payment,
    PaymentAllocation,
)
from billing.services import (
    next_schedule_date,
    sync_billing_for_enrollment,
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
        "is_primary": True,
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


def registration_pricing_snapshot(
    registration_session,
    *,
    waitlisted_class_ids=None,
):
    waitlisted_class_ids = set(
        waitlisted_class_ids or []
    )

    rows = []
    due_today = Decimal("0.00")
    future_recurring = Decimal("0.00")

    classes = (
        registration_session
        .selected_classes
        .select_related(
            "season",
            "tuition_plan",
            "class_type",
        )
        .order_by(
            "season__start_date",
            "name",
        )
    )

    settings_obj = getattr(
        registration_session.studio,
        "settings",
        None,
    )

    allow_waitlist = (
        settings_obj.allow_waitlist_requests
        if settings_obj is not None
        else True
    )

    for class_instance in classes:
        tuition = (
            class_instance.tuition_amount
            or Decimal("0.00")
        )

        policy = class_instance.tuition_plan

        registration_fee = (
            policy.registration_fee
            if policy is not None
            else Decimal("0.00")
        )

        is_waitlisted = (
            class_instance.pk in waitlisted_class_ids
        )

        if not waitlisted_class_ids:
            is_waitlisted = class_instance.is_full

        waitlist = (
            is_waitlisted
            and allow_waitlist
        )

        if is_waitlisted:
            class_due_today = Decimal("0.00")
            registration_due = Decimal("0.00")
        else:
            class_due_today = tuition
            registration_due = registration_fee

        row_due_today = (
            class_due_today
            + registration_due
        )

        due_today += row_due_today

        recurring_amount = Decimal("0.00")
        frequency = "One Time"

        if policy is not None:
            frequency = policy.get_frequency_display()

            if policy.frequency in {
                policy.BillingFrequency.WEEKLY,
                policy.BillingFrequency.MONTHLY,
                policy.BillingFrequency.QUARTERLY,
            }:
                recurring_amount = tuition
                if not is_waitlisted:
                    future_recurring += tuition

        rows.append(
            {
                "class_id": class_instance.pk,
                "class_code": class_instance.class_id,
                "class_name": class_instance.name,
                "season": class_instance.season.name,
                "frequency": frequency,
                "tuition": str(tuition),
                "registration_fee": str(registration_fee),
                "due_today": str(row_due_today),
                "future_recurring": str(recurring_amount),
                "is_full": is_waitlisted,
                "waitlist": waitlist,
            }
        )

    snapshot = {
        "items": rows,
        "due_today": str(due_today),
        "future_recurring_total": str(
            future_recurring
        ),
        "currency": "USD",
    }

    registration_session.pricing_snapshot = snapshot
    registration_session.save(
        update_fields=[
            "pricing_snapshot",
            "updated_at",
        ]
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

    student = registration_session.linked_student
    login_url = (
        f"{settings.ENCORE_BASE_URL}/accounts/login/"
    )

    class_lines = "".join(
        (
            f"<li>{enrollment.class_instance.name} "
            f"({enrollment.get_status_display()})</li>"
        )
        for enrollment in enrollments
    )

    payment_line = (
        f"<p><strong>Payment:</strong> "
        f"${payment.amount} USD</p>"
        if payment is not None
        else "<p><strong>Payment:</strong> No payment was due today.</p>"
    )

    html_body = (
        f"<h2>Registration confirmed for {student.first_name} "
        f"{student.last_name}</h2>"
        f"<p>Your registration with "
        f"{registration_session.studio.name} is complete.</p>"
        f"<h3>Classes</h3><ul>{class_lines}</ul>"
        f"{payment_line}"
        f"<h3>Using Encore</h3>"
        f"<p>Go to <a href='{login_url}'>Encore</a> and sign in "
        f"with {recipient}. You can view student information, "
        f"classes, billing, studio updates, and future activity "
        f"from your Encore account.</p>"
    )

    text_classes = "\n".join(
        (
            f"- {enrollment.class_instance.name} "
            f"({enrollment.get_status_display()})"
        )
        for enrollment in enrollments
    )

    text_body = (
        f"Registration confirmed for {student.first_name} "
        f"{student.last_name}\n\n"
        f"Classes:\n{text_classes}\n\n"
        + (
            f"Payment: ${payment.amount} USD\n\n"
            if payment is not None
            else "Payment: No payment was due today.\n\n"
        )
        + (
            f"Sign in to Encore at {login_url} using "
            f"{recipient}."
        )
    )

    return send_email(
        to=[recipient],
        subject=(
            f"Registration confirmed - "
            f"{registration_session.studio.name}"
        ),
        html_body=html_body,
        text_body=text_body,
        tags={
            "message_type": "registration_confirmation",
            "studio_id": registration_session.studio_id,
        },
    )


@transaction.atomic
def finalize_public_registration(
    registration_session,
    *,
    stripe_payment_intent_id="",
    paid_amount=Decimal("0.00"),
):
    from .models import RegistrationClassHold

    registration_session = (
        registration_session.__class__.objects
        .select_for_update()
        .select_related("studio")
        .get(pk=registration_session.pk)
    )

    if (
        registration_session.status
        == registration_session.Status.COMPLETED
    ):
        enrollments = (
            Enrollment.objects
            .filter(
                student=registration_session.linked_student,
                class_instance__in=registration_session.selected_classes.all(),
            )
            .select_related(
                "class_instance",
            )
        )

        return {
            "user": registration_session.linked_user,
            "family": registration_session.linked_family,
            "student": registration_session.linked_student,
            "payment": registration_session.linked_payment,
            "enrollments": list(enrollments),
        }

    account_data = registration_session.account_data
    student_data = registration_session.student_data
    User = get_user_model()

    existing_user_id = account_data.get(
        "existing_user_id"
    )

    if existing_user_id:
        account_user = User.objects.get(
            pk=existing_user_id,
            is_active=True,
        )
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

    existing_family_id = account_data.get(
        "existing_family_id"
    )

    if existing_family_id:
        family = Family.objects.get(
            pk=existing_family_id,
            studio=registration_session.studio,
            is_active=True,
        )
    else:
        family = _family_from_registration(
            registration_session
        )

    if (
        registration_session.registration_type
        == registration_session.RegistrationType.STUDENT
    ):
        existing_guardian_id = account_data.get(
            "existing_guardian_id"
        )

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
                first_name=account_data.get(
                    "guardian_first_name",
                    "",
                ),
                last_name=account_data.get(
                    "guardian_last_name",
                    "",
                ),
                relationship=account_data.get(
                    "guardian_relationship",
                    "",
                ),
                email=account_data.get(
                    "email",
                    "",
                ),
                phone=account_data.get(
                    "phone",
                    "",
                ),
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

        existing_student_id = student_data.get(
            "existing_student_id"
        )

        if existing_student_id:
            student = Student.objects.get(
                pk=existing_student_id,
                studio=registration_session.studio,
                family=family,
                is_active=True,
            )
            student_user = student.user
        else:
            student_user = None

            if student_data.get(
                "create_student_login"
            ):
                student_user = _create_user_from_hash(
                    email=student_data["student_email"],
                    first_name=student_data.get(
                        "student_first_name",
                        "",
                    ),
                    last_name=student_data.get(
                        "student_last_name",
                        "",
                    ),
                    password_hash=student_data[
                        "student_password_hash"
                    ],
                )

                StudioMembership.objects.get_or_create(
                    user=student_user,
                    studio=registration_session.studio,
                    role=StudioMembership.Role.STUDENT,
                    defaults={"is_active": True},
                )

            student = _student_from_registration(
                registration_session,
                family=family,
                student_user=student_user,
            )

    else:
        StudioMembership.objects.get_or_create(
            user=account_user,
            studio=registration_session.studio,
            role=StudioMembership.Role.STUDENT,
            defaults={"is_active": True},
        )

        existing_student_id = student_data.get(
            "existing_student_id"
        )

        if existing_student_id:
            student = Student.objects.get(
                pk=existing_student_id,
                studio=registration_session.studio,
                user=account_user,
                is_active=True,
            )
            family = student.family or family
        else:
            student = _student_from_registration(
                registration_session,
                family=family,
                student_user=account_user,
            )

    family_account, _created = (
        FamilyAccount.objects.get_or_create(
            family=family,
            defaults={
                "studio": registration_session.studio,
                "is_active": True,
            },
        )
    )

    held_class_ids = set(
        RegistrationClassHold.objects.filter(
            registration_session=registration_session,
            is_active=True,
            expires_at__gt=timezone.now(),
        ).values_list(
            "class_instance_id",
            flat=True,
        )
    )

    enrollments = []
    charges_to_pay = []

    pricing_by_class = {
        int(item["class_id"]): item
        for item in (
            registration_session.pricing_snapshot.get(
                "items",
                []
            )
        )
    }

    for class_instance in (
        registration_session
        .selected_classes
        .select_related(
            "season",
            "tuition_plan",
        )
        .order_by("pk")
    ):
        item = pricing_by_class.get(
            class_instance.pk,
            {},
        )

        should_waitlist = bool(
            item.get("waitlist")
        )

        if (
            not should_waitlist
            and class_instance.pk in held_class_ids
        ):
            status = Enrollment.Status.ACTIVE
        elif should_waitlist:
            status = Enrollment.Status.WAITLISTED
        else:
            status = (
                Enrollment.Status.WAITLISTED
                if class_instance.is_full
                else Enrollment.Status.ACTIVE
            )

        enrollment, created = (
            Enrollment.objects.get_or_create(
                student=student,
                class_instance=class_instance,
                defaults={
                    "status": status,
                    "source": Enrollment.Source.ONLINE,
                },
            )
        )

        if not created:
            if enrollment.status in {
                Enrollment.Status.DROPPED,
                Enrollment.Status.CANCELLED,
                Enrollment.Status.COMPLETED,
            }:
                enrollment.status = status
                enrollment.source = Enrollment.Source.ONLINE
                enrollment.full_clean()
                enrollment.save(
                    update_fields=[
                        "status",
                        "source",
                        "updated_at",
                    ]
                )

        enrollments.append(enrollment)

        if status == Enrollment.Status.ACTIVE:
            charges_to_pay.extend(
                _registration_charges_for_enrollment(
                    enrollment
                )
            )

    payment = None

    if paid_amount > Decimal("0.00"):
        payment = Payment(
            account=family_account,
            amount=paid_amount,
            method=Payment.Method.CARD,
            status=Payment.Status.SUCCEEDED,
            external_reference=stripe_payment_intent_id,
            notes=(
                "Online registration payment processed through Stripe."
            ),
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

            amount = min(
                remaining,
                balance,
            )

            PaymentAllocation.objects.create(
                payment=payment,
                charge=charge,
                amount=amount,
            )

            remaining -= amount

    RegistrationClassHold.objects.filter(
        registration_session=registration_session,
    ).update(
        is_active=False,
    )

    registration_session.linked_user = account_user
    registration_session.linked_family = family
    registration_session.linked_student = student
    registration_session.linked_payment = payment
    registration_session.stripe_payment_intent_id = (
        stripe_payment_intent_id
    )
    registration_session.status = (
        registration_session.Status.COMPLETED
    )
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
        "student": student,
        "payment": payment,
        "enrollments": enrollments,
    }
