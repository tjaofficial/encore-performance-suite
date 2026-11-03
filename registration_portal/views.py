from calendar import monthcalendar
from datetime import date
from decimal import Decimal
import uuid
from urllib.parse import urlencode
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt

from classes.models import Class, ClassLevel, ClassType, Season
from enrollments.models import Enrollment
from families.models import Guardian
from students.models import Student
from studios.models import Studio, StudioSettings
from communications.models import WorkspaceNotification
from communications.notification_services import (
    administrator_users,
    create_workspace_notification,
)
from scheduling.models import CalendarEvent

from .forms import (
    AcceptInviteForm,
    FamilyInviteForm,
    NewFamilyAccountForm,
    PublicRegistrationRequestForm,
    RegistrationTypeForm,
    GuardianAccountDetailsForm,
    ExistingAccountLoginForm,
    SelfAccountDetailsForm,
    StudentDetailsForm,
    ClassSelectionForm,
    RegistrationReviewForm,
)
from .approval_codes import claim as claim_class_code, validate_session as validate_class_codes
from .models import (
    FamilyInvite,
    RegistrationRequest,
    PublicRegistrationSession,
)
from .services import (
    accept_family_invite,
    convert_request_for_existing_family,
    create_new_family_from_request,
    matching_guardian_for_request,
    matching_student_for_request,
    matching_user_for_request,
    registration_pricing_snapshot,
    finalize_public_registration,
)
from .payment_services import (
    connected_subscription_for_registration,
    finalize_if_payment_succeeded,
    prepare_registration_payment,
)
from .policy_services import (
    policy_rows_for_registration,
    record_registration_policy_acceptances,
    registration_policies_satisfied,
)
from .security import (
    SECURITY_KEY,
    client_ip,
    mark_existing_account_trusted,
    mark_registration_email_verified,
    registration_identity_verified,
    registration_security_state,
    registration_start_allowed,
    registration_uses_existing_account,
    security_state_for_account_update,
    seed_registration_security,
    send_registration_verification_email,
    validate_registration_verification_code,
)



def _widget_settings(studio):
    settings_obj, _created = (
        StudioSettings.objects
        .get_or_create(
            studio=studio,
        )
    )

    values = {
        "calendar_enabled": True,
        "calendar_style": "month",
        "calendar_show_details": True,
        "classes_enabled": True,
        "classes_style": "cards",
        "default_season": None,
        "show_class_pricing": True,
        "show_class_capacity": True,
        "registration_enabled": True,
        "registration_style": "clean",
    }

    values.update(
        settings_obj.public_widget_settings
        or {}
    )

    return settings_obj, values


def _registration_available(studio):
    settings_obj, widget_settings = (
        _widget_settings(studio)
    )

    return (
        settings_obj.public_registration_enabled
        and widget_settings[
            "registration_enabled"
        ]
    )


def _month_value(request):
    raw = request.GET.get(
        "month",
        "",
    ).strip()

    today = timezone.localdate()

    if raw:
        try:
            year, month = [
                int(value)
                for value in raw.split("-", 1)
            ]
            if 1 <= month <= 12:
                return date(year, month, 1)
        except (TypeError, ValueError):
            pass

    return today.replace(day=1)


def _shift_month(value, delta):
    index = value.year * 12 + value.month - 1 + delta
    year, zero_month = divmod(index, 12)
    return date(
        year,
        zero_month + 1,
        1,
    )


def _public_calendar_context(
    studio,
    request,
    *,
    embed_mode,
):
    settings_obj, widget_settings = (
        _widget_settings(studio)
    )

    month_start = _month_value(
        request
    )
    next_month = _shift_month(
        month_start,
        1,
    )

    events = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
            is_public=True,
            scope=CalendarEvent.Scope.MAIN,
            audience=CalendarEvent.Audience.STUDIO,
            start_at__lt=timezone.make_aware(
                timezone.datetime.combine(
                    next_month,
                    timezone.datetime.min.time(),
                ),
                timezone.get_current_timezone(),
            ),
            end_at__gte=timezone.make_aware(
                timezone.datetime.combine(
                    month_start,
                    timezone.datetime.min.time(),
                ),
                timezone.get_current_timezone(),
            ),
        )
        .select_related(
            "category",
        )
        .order_by(
            "start_at",
            "title",
        )
    )

    event_map = {}

    for event in events:
        local_start = timezone.localtime(
            event.start_at
        )
        day_key = local_start.date()
        event_map.setdefault(
            day_key,
            [],
        ).append(event)

    weeks = []

    for week in monthcalendar(
        month_start.year,
        month_start.month,
    ):
        days = []

        for day_number in week:
            if not day_number:
                days.append(
                    {
                        "number": None,
                        "date": None,
                        "events": [],
                    }
                )
                continue

            current_date = date(
                month_start.year,
                month_start.month,
                day_number,
            )

            days.append(
                {
                    "number": day_number,
                    "date": current_date,
                    "events": event_map.get(
                        current_date,
                        [],
                    ),
                }
            )

        weeks.append(days)

    return {
        "studio": studio,
        "settings_obj": settings_obj,
        "widget_settings": widget_settings,
        "widget_style": widget_settings[
            "calendar_style"
        ],
        "show_details": widget_settings[
            "calendar_show_details"
        ],
        "month_start": month_start,
        "previous_month": _shift_month(
            month_start,
            -1,
        ),
        "next_month": next_month,
        "weeks": weeks,
        "events": events,
        "embed_mode": embed_mode,
    }


def _public_classes(studio):
    return (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
            season__is_active=True,
        )
        .select_related(
            "season",
            "class_type",
            "level",
            "instructor",
            "tuition_plan",
            "default_location",
        )
        .prefetch_related(
            "meeting_times",
        )
        .annotate(
            active_enrollment_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
        .order_by("name")
    )


def _query_class_type(studio, raw):
    value = str(raw or "").strip()
    if not value:
        return None
    if value.isdigit():
        return ClassType.objects.filter(studio=studio, pk=int(value), is_active=True).first()
    return ClassType.objects.filter(studio=studio, name__iexact=value, is_active=True).first()


def _query_class_level(studio, raw):
    value = str(raw or "").strip()
    if not value:
        return None
    qs = ClassLevel.objects.filter(studio=studio, is_active=True)
    if value.isdigit():
        by_number = qs.filter(number=int(value)).first()
        if by_number:
            return by_number
        return qs.filter(pk=int(value)).first()
    by_name = qs.filter(name__iexact=value).first()
    if by_name:
        return by_name
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    for level in qs:
        candidates = [level.name, *list(level.aliases or [])]
        if any(re.sub(r"[^a-z0-9]+", "", str(item).lower()) == normalized for item in candidates):
            return level
    return None


def _age_query_value(raw):
    value = str(raw or "").strip().lower()
    if not value:
        return None

    month_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(?:months?|mos?|mo)",
        value,
        re.IGNORECASE,
    )
    if month_match:
        return (
            Decimal(month_match.group(1))
            / Decimal("12")
        ).quantize(
            Decimal("0.01")
        )

    try:
        return Decimal(value)
    except Exception:
        return None


def _age_group_values(request):
    age = str(
        request.GET.get("age", "")
        or ""
    ).strip()
    age_group = str(
        request.GET.get("age_group", "")
        or ""
    ).strip()
    minimum = str(
        request.GET.get("min_age", "")
        or ""
    ).strip()
    maximum = str(
        request.GET.get("max_age", "")
        or ""
    ).strip()

    single = _age_query_value(age)
    if single is not None:
        return single, single

    if age_group:
        match = re.search(
            r"(\d+(?:\.\d+)?\s*(?:months?|mos?|mo)?)"
            r"\s*(?:-|–|—|to)\s*"
            r"(\d+(?:\.\d+)?\s*(?:months?|mos?|mo)?)",
            age_group,
            re.IGNORECASE,
        )
        if match:
            return (
                _age_query_value(
                    match.group(1)
                ),
                _age_query_value(
                    match.group(2)
                ),
            )

        single_group = _age_query_value(
            age_group
        )
        if single_group is not None:
            return (
                single_group,
                single_group,
            )

    return (
        _age_query_value(minimum),
        _age_query_value(maximum),
    )


def _filter_public_class_queryset(request, studio, classes, widget_settings=None):
    search = str(request.GET.get("q", "") or "").strip()
    season_raw = str(request.GET.get("season", "") or "").strip()
    type_raw = str(request.GET.get("class_type", "") or request.GET.get("type", "") or "").strip()
    level_raw = str(request.GET.get("level", "") or "").strip()
    availability = str(request.GET.get("availability", "") or "").strip()

    if search:
        classes = classes.filter(
            Q(name__icontains=search)
            | Q(class_id__icontains=search)
            | Q(description__icontains=search)
        )

    effective_season = season_raw or ((widget_settings or {}).get("default_season") or "")
    if effective_season:
        if str(effective_season).isdigit():
            classes = classes.filter(season_id=int(effective_season))
        else:
            classes = classes.filter(season__name__iexact=str(effective_season))

    class_type = _query_class_type(studio, type_raw)
    if type_raw:
        classes = classes.filter(class_type=class_type) if class_type else classes.none()

    level = _query_class_level(studio, level_raw)
    if level_raw:
        classes = classes.filter(level=level) if level else classes.none()

    requested_min, requested_max = _age_group_values(request)
    if requested_min is not None:
        classes = classes.filter(Q(max_age__isnull=True) | Q(max_age__gte=requested_min))
    if requested_max is not None:
        classes = classes.filter(Q(min_age__isnull=True) | Q(min_age__lte=requested_max))

    return classes, {
        "q": search,
        "season": season_raw,
        "type": str(class_type.pk) if class_type else "",
        "class_type": type_raw,
        "level": str(level.number) if level else level_raw,
        "age": str(request.GET.get("age", "") or ""),
        "age_group": str(request.GET.get("age_group", "") or ""),
        "min_age": str(request.GET.get("min_age", "") or ""),
        "max_age": str(request.GET.get("max_age", "") or ""),
        "availability": availability,
        "hide_filters": str(request.GET.get("hide_filters", "") or "") in {"1", "true", "yes"},
    }


def _class_rows(classes):
    rows = []

    for class_instance in classes:
        capacity = (
            class_instance.capacity
            or 0
        )

        enrolled = (
            class_instance.active_enrollment_count
        )

        remaining = (
            max(
                capacity - enrolled,
                0,
            )
            if capacity
            else None
        )

        rows.append(
            {
                "class": class_instance,
                "enrolled": enrolled,
                "remaining": remaining,
                "is_full": (
                    capacity > 0
                    and enrolled >= capacity
                ),
            }
        )

    return rows


def public_calendar(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    context = _public_calendar_context(
        studio,
        request,
        embed_mode=False,
    )

    if not context[
        "widget_settings"
    ]["calendar_enabled"]:
        return render(
            request,
            "registration_portal/widget_disabled.html",
            {
                "studio": studio,
                "widget_name": "Calendar",
            },
            status=403,
        )

    return render(
        request,
        "registration_portal/public_calendar.html",
        context,
    )


@xframe_options_exempt
def embedded_calendar(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    context = _public_calendar_context(
        studio,
        request,
        embed_mode=True,
    )

    if not context[
        "widget_settings"
    ]["calendar_enabled"]:
        return render(
            request,
            "registration_portal/widget_disabled.html",
            {
                "studio": studio,
                "widget_name": "Calendar",
            },
            status=403,
        )

    return render(
        request,
        "registration_portal/public_calendar.html",
        context,
    )


def _registration_home_context(
    studio,
    *,
    embed_mode,
):
    settings_obj, widget_settings = (
        _widget_settings(studio)
    )

    classes = _public_classes(
        studio
    ).filter(
        registration_open=True,
        season__registration_open=True,
    )

    default_season_id = (
        widget_settings.get(
            "default_season"
        )
    )

    if default_season_id:
        classes = classes.filter(
            season_id=default_season_id,
        )

    return {
        "studio": studio,
        "settings_obj": settings_obj,
        "widget_settings": widget_settings,
        "widget_style": widget_settings[
            "registration_style"
        ],
        "class_rows": _class_rows(
            classes
        ),
        "embed_mode": embed_mode,
    }


def public_registration_home(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _registration_available(
        studio
    ):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    return render(
        request,
        "registration_portal/registration_home.html",
        _registration_home_context(
            studio,
            embed_mode=False,
        ),
    )


@xframe_options_exempt
def embedded_registration_home(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _registration_available(
        studio
    ):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    return render(
        request,
        "registration_portal/registration_home.html",
        _registration_home_context(
            studio,
            embed_mode=True,
        ),
    )


REGISTRATION_WIZARD_STEPS = {
    "type",
    "account",
    "student",
    "classes",
    "review",
    "policies",
    "ready",
}


def _wizard_class_queryset(
    studio,
    student_data=None,
    *,
    apply_default_season=True,
    registration_only=True,
):
    # Start from the same active class pool used by the public class widget.
    # This lets the registration picker show age-matched classes even when a
    # class/season is closed, so the parent can see why it is unavailable
    # instead of getting an empty modal with empty filters.
    classes = _public_classes(studio)

    if registration_only:
        classes = classes.filter(
            registration_open=True,
            season__registration_open=True,
        )

    if apply_default_season:
        _settings_obj, widget_settings = _widget_settings(studio)
        default_season_id = widget_settings.get("default_season")
        if default_season_id:
            classes = classes.filter(season_id=default_season_id)

    birthday_raw = (student_data or {}).get("birthday") or ""
    age = None
    if birthday_raw:
        try:
            birthday = date.fromisoformat(str(birthday_raw))
            today = timezone.localdate()
            age_months = (
                (today.year - birthday.year) * 12
                + today.month
                - birthday.month
            )
            if today.day < birthday.day:
                age_months -= 1

            age = (
                Decimal(age_months)
                / Decimal("12")
            ).quantize(
                Decimal("0.01")
            )
        except (TypeError, ValueError):
            age = None

    if age is not None:
        classes = classes.filter(
            Q(min_age__isnull=True) | Q(min_age__lte=age),
            Q(max_age__isnull=True) | Q(max_age__gte=age),
        )

    existing_student_id = (student_data or {}).get("existing_student_id")
    if existing_student_id:
        classes = classes.exclude(
            enrollments__student_id=existing_student_id,
            enrollments__status__in=[
                Enrollment.Status.ACTIVE,
                Enrollment.Status.WAITLISTED,
            ],
        )

    return classes


def _serialize_form_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _safe_saved_form_data(data):
    return {
        key: value
        for key, value in (data or {}).items()
        if not key.endswith("_hash")
    }


def _registration_student_state(registration_session):
    raw = registration_session.student_data or {}

    if isinstance(raw.get("students"), list):
        students = [dict(item) for item in raw.get("students", [])]
        assignments = {
            str(key): [int(value) for value in values if str(value).isdigit()]
            for key, values in (raw.get("assignments") or {}).items()
            if isinstance(values, list)
        }
    elif raw:
        legacy = dict(raw)
        legacy.setdefault("draft_key", "legacy-student")
        students = [legacy]
        assignments = {
            legacy["draft_key"]: list(
                registration_session.selected_classes.values_list("pk", flat=True)
            )
        }
    else:
        students = []
        assignments = {}

    for student in students:
        if not student.get("draft_key"):
            if student.get("existing_student_id"):
                student["draft_key"] = f"existing-{student['existing_student_id']}"
            else:
                student["draft_key"] = f"draft-{uuid.uuid4().hex}"

    return students, assignments


def _store_registration_student_state(
    registration_session,
    students,
    assignments,
    *,
    save=True,
):
    registration_session.student_data = {
        "approval_grants": (registration_session.student_data or {}).get("approval_grants", {}),
        "students": students,
        "assignments": {
            str(key): [int(value) for value in values]
            for key, values in assignments.items()
        },
    }
    if save:
        registration_session.save(
            update_fields=["student_data", "updated_at"]
        )


def _student_display_name(student):
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


def _sync_session_selected_classes(
    registration_session,
    assignments,
):
    class_ids = sorted({
        int(class_id)
        for values in assignments.values()
        for class_id in values
        if str(class_id).isdigit()
    })
    valid = Class.objects.filter(
        studio=registration_session.studio,
        pk__in=class_ids,
        is_active=True,
    )
    registration_session.selected_classes.set(valid)


def _student_review_rows(registration_session):
    students, assignments = _registration_student_state(
        registration_session
    )
    all_ids = {
        int(class_id)
        for values in assignments.values()
        for class_id in values
        if str(class_id).isdigit()
    }
    classes = {
        class_instance.pk: class_instance
        for class_instance in Class.objects.filter(
            studio=registration_session.studio,
            pk__in=all_ids,
        ).select_related(
            "season",
            "class_type",
            "level",
            "tuition_plan",
        ).prefetch_related("meeting_times")
    }

    rows = []
    for student in students:
        key = student["draft_key"]
        rows.append({
            "key": key,
            "data": student,
            "name": _student_display_name(student),
            "classes": [
                classes[class_id]
                for class_id in assignments.get(key, [])
                if class_id in classes
            ],
        })
    return rows


@login_required
def register_existing_student(
    request,
    studio_slug,
    student_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _registration_available(studio):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    guardian = (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family")
        .order_by("-is_primary", "pk")
        .first()
    )

    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    student = get_object_or_404(
        Student,
        pk=student_id,
        studio=studio,
        family=guardian.family,
        is_active=True,
    )

    source_ip = client_ip(request)
    if not registration_start_allowed(source_ip):
        return render(
            request,
            "registration_portal/registration_security_error.html",
            {
                "studio": studio,
                "message": (
                    "Too many registrations were started from this connection. "
                    "Please wait before trying again."
                ),
            },
            status=429,
        )

    registration_session = PublicRegistrationSession.objects.create(
        studio=studio,
        registration_type=(
            PublicRegistrationSession.RegistrationType.STUDENT
        ),
        contact_email=request.user.email,
        current_step="classes",
    )

    seed_registration_security(
        registration_session,
        request,
    )

    registration_session.account_data = {
        "registration_flow": "add_classes",
        "account_mode": "existing",
        "existing_user_id": request.user.pk,
        "existing_family_id": guardian.family_id,
        "existing_guardian_id": guardian.pk,
        "guardian_first_name": guardian.first_name,
        "guardian_last_name": guardian.last_name,
        "guardian_relationship": guardian.relationship,
        "email": request.user.email,
        "phone": guardian.phone,
        "family_name": guardian.family.family_name,
        "address_line_1": guardian.family.address_line_1,
        "address_line_2": guardian.family.address_line_2,
        "city": guardian.family.city,
        "state": guardian.family.state,
        "postal_code": guardian.family.postal_code,
        SECURITY_KEY: mark_existing_account_trusted(
            registration_session,
            request,
        ),
    }

    students = [{
        "draft_key": f"existing-{student.pk}",
        "existing_student_id": student.pk,
        "student_first_name": student.first_name,
        "student_last_name": student.last_name,
        "birthday": student.birthday.isoformat(),
        "gender": student.gender,
    }]

    _store_registration_student_state(
        registration_session,
        students,
        {},
        save=False,
    )

    registration_session.save(
        update_fields=[
            "account_data",
            "student_data",
            "contact_email",
            "current_step",
            "updated_at",
        ]
    )
    registration_session.touch()

    return redirect(
        "registration_portal:registration_wizard",
        studio_slug=studio.slug,
        token=registration_session.token,
        step="classes",
    )


@xframe_options_exempt
def registration_wizard_start(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _registration_available(studio):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    source_ip = client_ip(request)
    if not registration_start_allowed(source_ip):
        return render(
            request,
            "registration_portal/registration_security_error.html",
            {
                "studio": studio,
                "message": (
                    "Too many registrations were started from this connection. "
                    "Please wait before trying again."
                ),
            },
            status=429,
        )

    embed_mode = request.GET.get("embed") == "1"
    registration_session = PublicRegistrationSession.objects.create(
        studio=studio,
        embed_mode=embed_mode,
    )
    seed_registration_security(registration_session, request)

    raw_ids = []
    single_id = str(request.GET.get("class", "") or "").strip()
    if single_id:
        raw_ids.append(single_id)

    raw_many = str(request.GET.get("classes", "") or "")
    raw_ids.extend(part.strip() for part in raw_many.split(",") if part.strip())

    class_ids = {
        int(value)
        for value in raw_ids
        if str(value).isdigit()
    }
    if class_ids:
        selected = _wizard_class_queryset(studio).filter(pk__in=class_ids)
        registration_session.selected_classes.set(selected)

    return redirect(
        "registration_portal:registration_wizard",
        studio_slug=studio.slug,
        token=registration_session.token,
        step="type",
    )


@xframe_options_exempt
def validate_registration_class_code(request, studio_slug, token):
    """Validate an in-person class code before showing it as added in the class picker."""
    if request.method != "POST":
        return JsonResponse({"valid": False, "error": "Invalid request."}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    session = get_object_or_404(PublicRegistrationSession, studio=studio, token=token)
    session.mark_expired()
    if session.status == PublicRegistrationSession.Status.EXPIRED:
        return JsonResponse({"valid": False, "error": "This registration session has expired."}, status=410)
    student_key = request.POST.get("student_key", "")
    students, _assignments = _registration_student_state(session)
    student = next((item for item in students if item.get("draft_key") == student_key), None)
    if student is None:
        return JsonResponse({"valid": False, "error": "Student could not be verified."}, status=400)
    class_id = request.POST.get("class_id", "")
    klass = Class.objects.filter(pk=class_id, studio=studio, registration_mode="approval").first() if class_id.isdigit() else None
    if klass is None or not klass.registration_open or not klass.season.registration_open:
        return JsonResponse({"valid": False, "error": "This class isn't available for registration."}, status=400)
    from .approval_codes import code_is_eligible
    valid = code_is_eligible(session, student_key, klass, request.POST.get("code", ""))
    return JsonResponse({"valid": valid, "error": "" if valid else "Invalid, expired, or previously used code for this student and parent."})


@xframe_options_exempt
def registration_wizard(
    request,
    studio_slug,
    token,
    step,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    from .addon_services import is_addon
    addon = is_addon(registration_session)
    if addon:
        account_data = registration_session.account_data or {}
        if not request.user.is_authenticated or request.user.pk != account_data.get('existing_user_id'):
            return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)
        if not Guardian.objects.filter(user=request.user, family_id=account_data.get('existing_family_id'),
                family__studio=studio, is_active=True).exists():
            return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)
        if step in {'type','account','student'}:
            return redirect('registration_portal:registration_wizard',
                studio_slug=studio.slug, token=registration_session.token, step='classes')

    if addon and registration_session.status == PublicRegistrationSession.Status.PAYMENT_PENDING and step != 'ready':
        return redirect('registration_portal:registration_wizard',
            studio_slug=studio.slug, token=registration_session.token, step='ready')

    registration_session.mark_expired()
    if registration_session.status == PublicRegistrationSession.Status.EXPIRED:
        return render(
            request,
            "registration_portal/registration_expired.html",
            {
                "studio": studio,
                "registration_session": registration_session,
                "embed_mode": registration_session.embed_mode,
            },
            status=410,
        )

    if step not in REGISTRATION_WIZARD_STEPS:
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step=registration_session.current_step,
        )

    if not _registration_available(studio):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    _settings_obj, widget_settings = _widget_settings(studio)
    form = None
    returning_form = None
    existing_students = Student.objects.none()
    class_rows = []
    pricing = None
    payment_setup = None
    payment_error = ""
    payments_available = False
    policy_rows = []
    policy_error = ""
    student_groups = []
    registration_students = _student_review_rows(registration_session)
    student_form_open = False
    student_form_mode = "new"

    if step == "type":
        form = RegistrationTypeForm(
            request.POST or None,
            initial={
                "registration_type": (
                    registration_session.registration_type
                    or PublicRegistrationSession.RegistrationType.STUDENT
                )
            },
        )
        if request.method == "POST" and form.is_valid():
            registration_session.registration_type = form.cleaned_data[
                "registration_type"
            ]
            registration_session.current_step = "account"
            registration_session.save(
                update_fields=[
                    "registration_type",
                    "current_step",
                    "updated_at",
                ]
            )
            registration_session.touch()
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="account",
            )

    elif step == "account":
        if not registration_session.registration_type:
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="type",
            )

        saved = _safe_saved_form_data(registration_session.account_data)
        returning_form = ExistingAccountLoginForm(
            request.POST
            if request.method == "POST"
            and request.POST.get("account_action") == "existing"
            else None,
            request=request,
        )

        if (
            registration_session.registration_type
            == PublicRegistrationSession.RegistrationType.SELF
        ):
            form = SelfAccountDetailsForm(
                request.POST
                if request.method == "POST"
                and request.POST.get("account_action") != "existing"
                else None,
                saved_data=saved,
            )
        else:
            form = GuardianAccountDetailsForm(
                request.POST
                if request.method == "POST"
                and request.POST.get("account_action") != "existing"
                else None,
                saved_data=saved,
            )

        if (
            request.method == "POST"
            and request.POST.get("account_action") == "existing"
            and returning_form.is_valid()
        ):
            user = returning_form.user
            if (
                registration_session.registration_type
                == PublicRegistrationSession.RegistrationType.STUDENT
            ):
                guardian = (
                    Guardian.objects.filter(
                        user=user,
                        family__studio=studio,
                        is_active=True,
                    )
                    .select_related("family")
                    .order_by("-is_primary", "pk")
                    .first()
                )
                if guardian is None:
                    returning_form.add_error(
                        None,
                        "This Encore account is not connected to a family at this studio.",
                    )
                else:
                    registration_session.account_data = {
                        "account_mode": "existing",
                        "existing_user_id": user.pk,
                        "existing_family_id": guardian.family_id,
                        "existing_guardian_id": guardian.pk,
                        "guardian_first_name": guardian.first_name,
                        "guardian_last_name": guardian.last_name,
                        "guardian_relationship": guardian.relationship,
                        "email": user.email,
                        "phone": guardian.phone,
                        "family_name": guardian.family.family_name,
                        "address_line_1": guardian.family.address_line_1,
                        "address_line_2": guardian.family.address_line_2,
                        "city": guardian.family.city,
                        "state": guardian.family.state,
                        "postal_code": guardian.family.postal_code,
                        SECURITY_KEY: mark_existing_account_trusted(
                            registration_session, request
                        ),
                    }
                    registration_session.contact_email = user.email
                    registration_session.current_step = "student"
                    registration_session.save(
                        update_fields=[
                            "account_data",
                            "contact_email",
                            "current_step",
                            "updated_at",
                        ]
                    )
                    registration_session.touch()
                    return redirect(
                        "registration_portal:registration_wizard",
                        studio_slug=studio.slug,
                        token=registration_session.token,
                        step="student",
                    )
            else:
                existing_student = (
                    Student.objects.filter(
                        user=user,
                        studio=studio,
                        is_active=True,
                    )
                    .select_related("family")
                    .first()
                )
                if existing_student is None:
                    returning_form.add_error(
                        None,
                        "This account is not connected to a student at this studio.",
                    )
                else:
                    registration_session.account_data = {
                        "account_mode": "existing",
                        "existing_user_id": user.pk,
                        "existing_family_id": existing_student.family_id,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "email": user.email,
                        SECURITY_KEY: mark_existing_account_trusted(
                            registration_session, request
                        ),
                    }
                    registration_session.contact_email = user.email
                    students = [{
                        "draft_key": f"existing-{existing_student.pk}",
                        "existing_student_id": existing_student.pk,
                        "student_first_name": existing_student.first_name,
                        "student_last_name": existing_student.last_name,
                        "birthday": existing_student.birthday.isoformat(),
                        "gender": existing_student.gender,
                    }]
                    _store_registration_student_state(
                        registration_session,
                        students,
                        {},
                        save=False,
                    )
                    registration_session.current_step = "classes"
                    registration_session.save(
                        update_fields=[
                            "account_data",
                            "contact_email",
                            "student_data",
                            "current_step",
                            "updated_at",
                        ]
                    )
                    registration_session.touch()
                    return redirect(
                        "registration_portal:registration_wizard",
                        studio_slug=studio.slug,
                        token=registration_session.token,
                        step="classes",
                    )

        elif (
            request.method == "POST"
            and request.POST.get("account_action") != "existing"
            and form.is_valid()
        ):
            serialized = {
                key: _serialize_form_value(value)
                for key, value in form.serialized_data().items()
            }
            serialized["account_mode"] = "new"
            serialized[SECURITY_KEY] = security_state_for_account_update(
                registration_session, request
            )
            registration_session.account_data = serialized
            registration_session.contact_email = serialized.get("email", "")
            registration_session.current_step = "student"
            registration_session.save(
                update_fields=[
                    "account_data",
                    "contact_email",
                    "current_step",
                    "updated_at",
                ]
            )
            registration_session.touch()
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="student",
            )

    elif step == "student":
        if not (registration_session.account_data or {}).get("account_mode"):
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="account",
            )

        students, assignments = _registration_student_state(registration_session)
        existing_family_id = registration_session.account_data.get(
            "existing_family_id"
        )
        if (
            registration_session.registration_type
            == PublicRegistrationSession.RegistrationType.STUDENT
            and existing_family_id
        ):
            existing_students = Student.objects.filter(
                studio=studio,
                family_id=existing_family_id,
                is_active=True,
            ).order_by("first_name", "last_name")

        action = (
            request.POST.get("student_action", "")
            if request.method == "POST"
            else ""
        )

        if action == "existing":
            existing_student = existing_students.filter(
                pk=request.POST.get("existing_student_id")
            ).first()
            if existing_student is None:
                messages.error(request, "Choose a student from this household.")
            elif any(
                item.get("existing_student_id") == existing_student.pk
                for item in students
            ):
                messages.info(request, "That student is already included.")
            else:
                students.append({
                    "draft_key": f"existing-{existing_student.pk}",
                    "existing_student_id": existing_student.pk,
                    "student_first_name": existing_student.first_name,
                    "student_last_name": existing_student.last_name,
                    "birthday": existing_student.birthday.isoformat(),
                    "gender": existing_student.gender,
                })
                _store_registration_student_state(
                    registration_session,
                    students,
                    assignments,
                )
                registration_session.touch()
                return redirect(
                    "registration_portal:registration_wizard",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                    step="student",
                )

        if action == "remove":
            remove_key = request.POST.get("student_key", "")
            students = [
                item for item in students
                if item.get("draft_key") != remove_key
            ]
            assignments.pop(remove_key, None)
            _store_registration_student_state(
                registration_session,
                students,
                assignments,
            )
            _sync_session_selected_classes(registration_session, assignments)
            registration_session.touch()
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="student",
            )

        edit_key = str(request.GET.get("edit", "") or "").strip()
        add_requested = request.GET.get("add") == "1"
        edit_student = next(
            (
                item for item in students
                if item.get("draft_key") == edit_key
                and not item.get("existing_student_id")
            ),
            None,
        )
        student_form_open = bool(
            not students
            or add_requested
            or edit_student is not None
            or action == "save"
        )
        student_form_mode = "edit" if edit_student is not None else "new"
        saved_student = edit_student or {}

        if student_form_open:
            form = StudentDetailsForm(
                request.POST if action == "save" else None,
                registration_type=registration_session.registration_type,
                account_email=registration_session.contact_email,
                account_data=registration_session.account_data,
                saved_data=_safe_saved_form_data(saved_student),
            )

        if action == "save" and form is not None and form.is_valid():
            serialized = {
                key: _serialize_form_value(value)
                for key, value in form.serialized_data().items()
            }
            target_key = request.POST.get("student_key", "").strip()
            if target_key:
                serialized["draft_key"] = target_key
                students = [
                    serialized if item.get("draft_key") == target_key else item
                    for item in students
                ]
            else:
                serialized["draft_key"] = f"draft-{uuid.uuid4().hex}"
                students.append(serialized)

            _store_registration_student_state(
                registration_session,
                students,
                assignments,
            )
            registration_session.touch()
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="student",
            )

        if action == "continue":
            if not students:
                messages.error(request, "Save at least one student before continuing.")
            else:
                if not any(assignments.values()):
                    cart_ids = list(
                        registration_session.selected_classes.values_list(
                            "pk", flat=True
                        )
                    )
                    if cart_ids:
                        assignments[students[0]["draft_key"]] = cart_ids
                        _store_registration_student_state(
                            registration_session,
                            students,
                            assignments,
                            save=False,
                        )
                registration_session.current_step = "classes"
                registration_session.save(
                    update_fields=[
                        "student_data",
                        "current_step",
                        "updated_at",
                    ]
                )
                registration_session.touch()
                return redirect(
                    "registration_portal:registration_wizard",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                    step="classes",
                )

        registration_students = [
            {
                "key": item["draft_key"],
                "data": item,
                "name": _student_display_name(item),
                "existing": bool(item.get("existing_student_id")),
                "editing": item.get("draft_key") == edit_key,
            }
            for item in students
        ]

    elif step == "classes":
        students, assignments = _registration_student_state(registration_session)
        if not students:
            if addon:
                raise ValueError("No authorized existing dancer is selected.")
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="student",
            )

        has_errors = False
        new_assignments = {}
        for student in students:
            key = student["draft_key"]
            visible_classes = _wizard_class_queryset(
                studio,
                student,
                apply_default_season=False,
                registration_only=False,
            )
            rows = _class_rows(visible_classes)

            # A class can be visible in the picker but unavailable for online
            # registration. Keep those rows visible (with a clear Closed
            # status) while only accepting selectable class IDs on submit.
            selectable_ids = set()
            for row in rows:
                class_instance = row["class"]
                row["registration_closed"] = not (
                    class_instance.registration_open
                    and class_instance.season.registration_open
                )
                row["approval_required"] = class_instance.registration_mode == "approval"
                if not row["registration_closed"]:
                    selectable_ids.add(class_instance.pk)

            allowed_ids = selectable_ids

            if request.method == "POST":
                posted_ids = {
                    int(value)
                    for value in request.POST.getlist(f"classes__{key}")
                    if str(value).isdigit()
                }
                selected_ids = sorted(posted_ids & allowed_ids)
                if not selected_ids:
                    has_errors = True
                    messages.error(
                        request,
                        f"Add at least one class for {_student_display_name(student)}.",
                    )
                new_assignments[key] = selected_ids
                grants = (registration_session.student_data or {}).get("approval_grants", {})
                student_grants = grants.setdefault(key, {})
                for class_id in selected_ids:
                    cls = next((r["class"] for r in rows if r["class"].pk == class_id), None)
                    if cls is None or cls.registration_mode != "approval":
                        continue
                    existing_id = student_grants.get(str(class_id))
                    if existing_id:
                        from .models import ClassApprovalCode
                        if ClassApprovalCode.objects.filter(
                            pk=existing_id, studio=studio, class_instance=cls,
                            claimed_session=registration_session, claimed_student_key=key,
                            parent_email=(registration_session.contact_email or "").strip().lower(),
                            expires_at__gt=timezone.now(), revoked_at__isnull=True, used_at__isnull=True,
                        ).exists():
                            continue
                    code = request.POST.get(f"approval__{key}__{class_id}", "").strip()
                    approved_id = claim_class_code(registration_session, key, cls, code) if code else None
                    if approved_id:
                        student_grants[str(class_id)] = approved_id
                    else:
                        has_errors = True
                        messages.error(request, f"{cls.name}: enter the studio-issued approval code for {_student_display_name(student)}.")
                registration_session.student_data["approval_grants"] = grants
            else:
                selected_ids = [
                    class_id
                    for class_id in assignments.get(key, [])
                    if class_id in allowed_ids
                ]

            student_groups.append({
                "key": key,
                "student": student,
                "name": _student_display_name(student),
                "class_rows": rows,
                "selected_ids": selected_ids,
                "class_types": sorted({
                    row["class"].class_type.name
                    for row in rows
                    if row["class"].class_type_id
                }),
                "seasons": sorted(
                    {
                        (row["class"].season_id, row["class"].season.name)
                        for row in rows
                    },
                    key=lambda item: item[1].lower(),
                ),
                "levels": sorted(
                    {
                        (row["class"].level_id, str(row["class"].level))
                        for row in rows
                        if row["class"].level_id
                    },
                    key=lambda item: item[1].lower(),
                ),
            })

        if request.method == "POST" and has_errors:
            # Keep any successfully claimed dancer-specific codes when another
            # field fails validation, so retries cannot strand a code.
            registration_session.save(update_fields=["student_data", "updated_at"])

        if request.method == "POST" and not has_errors:
            _store_registration_student_state(
                registration_session,
                students,
                new_assignments,
                save=False,
            )
            _sync_session_selected_classes(
                registration_session,
                new_assignments,
            )
            try:
                validate_class_codes(registration_session)
                registration_pricing_snapshot(registration_session)
            except ValueError as exc:
                messages.error(request, str(exc))
                has_errors = True
            if not has_errors:
                registration_session.current_step = "review"
            registration_session.save(
                update_fields=[
                    "student_data",
                    "current_step",
                    "pricing_snapshot",
                    "updated_at",
                ]
            )
            registration_session.touch()
            if not has_errors:
                return redirect(
                    "registration_portal:registration_wizard",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                    step="review",
                )

    elif step == "review":
        students, assignments = _registration_student_state(registration_session)
        if not students or not any(assignments.values()):
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="classes",
            )

        _sync_session_selected_classes(registration_session, assignments)
        pricing = registration_pricing_snapshot(registration_session)
        registration_students = _student_review_rows(registration_session)
        form = RegistrationReviewForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            if registration_identity_verified(registration_session):
                registration_session.status = (
                    PublicRegistrationSession.Status.IN_PROGRESS
                )
                registration_session.current_step = "policies"
                registration_session.save(
                    update_fields=[
                        "status",
                        "current_step",
                        "pricing_snapshot",
                        "updated_at",
                    ]
                )
                registration_session.touch()
                return redirect(
                    "registration_portal:registration_wizard",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                    step="policies",
                )

            try:
                send_registration_verification_email(
                    request, registration_session
                )
            except Exception as exc:
                message = (
                    str(exc)
                    if settings.DEBUG
                    else (
                        "Encore could not send the verification email. "
                        "Please try again shortly."
                    )
                )
                form.add_error(None, message)
            else:
                registration_session.current_step = "verify_email"
                registration_session.save(
                    update_fields=["current_step", "updated_at"]
                )
                registration_session.touch()
                return redirect(
                    "registration_portal:registration_verification_pending",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                )

    elif step == "policies":
        if not registration_identity_verified(registration_session):
            return redirect(
                "registration_portal:registration_verification_pending",
                studio_slug=studio.slug,
                token=registration_session.token,
            )

        students, assignments = _registration_student_state(registration_session)
        if not students or not any(assignments.values()):
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="classes",
            )

        _sync_session_selected_classes(registration_session, assignments)
        pricing = registration_pricing_snapshot(registration_session)
        registration_students = _student_review_rows(registration_session)
        policy_rows = policy_rows_for_registration(registration_session)

        if not policy_rows:
            registration_session.status = (
                PublicRegistrationSession.Status.READY_FOR_PAYMENT
            )
            registration_session.current_step = "ready"
            registration_session.save(
                update_fields=["status", "current_step", "pricing_snapshot", "updated_at"]
            )
            registration_session.touch()
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="ready",
            )

        if request.method == "POST":
            accepted_policy_ids = [
                row["policy"].pk
                for row in policy_rows
                if request.POST.get(f"policy_accept_{row['policy'].pk}") == "on"
            ]
            signatures = {
                str(row["policy"].pk): request.POST.get(
                    f"policy_signature_{row['policy'].pk}",
                    "",
                )
                for row in policy_rows
            }
            try:
                record_registration_policy_acceptances(
                    registration_session,
                    request=request,
                    accepted_policy_ids=accepted_policy_ids,
                    signatures=signatures,
                )
            except ValueError as exc:
                policy_error = str(exc)
                policy_rows = policy_rows_for_registration(registration_session)
            else:
                registration_session.status = (
                    PublicRegistrationSession.Status.READY_FOR_PAYMENT
                )
                registration_session.current_step = "ready"
                registration_session.save(
                    update_fields=[
                        "status",
                        "current_step",
                        "pricing_snapshot",
                        "updated_at",
                    ]
                )
                registration_session.touch()
                return redirect(
                    "registration_portal:registration_wizard",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                    step="ready",
                )

    elif step == "ready":
        if not registration_identity_verified(registration_session):
            return redirect(
                "registration_portal:registration_verification_pending",
                studio_slug=studio.slug,
                token=registration_session.token,
            )

        if not registration_policies_satisfied(registration_session):
            registration_session.status = PublicRegistrationSession.Status.IN_PROGRESS
            registration_session.current_step = "policies"
            registration_session.save(
                update_fields=["status", "current_step", "updated_at"]
            )
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="policies",
            )

        if registration_session.status not in {
            PublicRegistrationSession.Status.READY_FOR_PAYMENT,
            PublicRegistrationSession.Status.PAYMENT_PENDING,
        }:
            if registration_session.status == PublicRegistrationSession.Status.COMPLETED:
                return redirect(
                    "registration_portal:registration_complete",
                    studio_slug=studio.slug,
                    token=registration_session.token,
                )
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="review",
            )

        pricing = (
            registration_session.pricing_snapshot
            or registration_pricing_snapshot(registration_session)
        )
        payment_setup = {
            "amount": Decimal(str(pricing.get("due_today", "0.00"))),
            "client_secret": "",
            "connected_account_id": "",
            "payment_intent_id": "",
        }
        payments_available = (
            connected_subscription_for_registration(registration_session)
            is not None
        )
        if addon and payment_setup["amount"] > Decimal("0.00") and not payments_available:
            payment_error = "This studio must connect its Stripe account before paid class additions can be completed."
        if payment_setup["amount"] > Decimal("0.00") and payments_available:
            try:
                payment_setup = prepare_registration_payment(
                    request,
                    registration_session,
                )
                registration_session.refresh_from_db()
                pricing = registration_session.pricing_snapshot
            except Exception as exc:
                payment_error = str(exc)

        registration_students = _student_review_rows(registration_session)

    context = {
        "studio": studio,
        "registration_session": registration_session,
        "step": step,
        "addon_flow": addon,
        "form": form,
        "class_rows": class_rows,
        "student_groups": student_groups,
        "registration_students": registration_students,
        "student_form_open": student_form_open,
        "student_form_mode": student_form_mode,
        "pricing": pricing,
        "account_data": _safe_saved_form_data(registration_session.account_data),
        "returning_form": returning_form,
        "existing_students": existing_students,
        "embed_mode": registration_session.embed_mode,
        "widget_style": widget_settings["registration_style"],
        "payment_setup": payment_setup,
        "payment_error": payment_error,
        "payments_available": payments_available,
        "policy_rows": policy_rows,
        "policy_error": policy_error,
        "registration_requires_verification": (
            step == "review"
            and not registration_identity_verified(registration_session)
        ),
        "stripe_publishable_key": (
            settings.STRIPE_PUBLISHABLE_KEY if step == "ready" else ""
        ),
    }

    return render(
        request,
        "registration_portal/registration_wizard.html",
        context,
    )

@xframe_options_exempt
def registration_verification_pending(
    request,
    studio_slug,
    token,
):
    studio = get_object_or_404(
        Studio, slug=studio_slug, is_active=True
    )
    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    if registration_uses_existing_account(registration_session):
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="policies",
        )

    if registration_identity_verified(registration_session):
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="policies",
        )

    if request.method == "POST":
        try:
            send_registration_verification_email(
                request, registration_session
            )
        except Exception as exc:
            messages.error(
                request,
                str(exc)
                if settings.DEBUG
                else (
                    "Encore could not send another verification email. "
                    "Please wait and try again."
                ),
            )
        else:
            messages.success(
                request,
                "A new verification email was sent.",
            )
            registration_session.touch()

    return render(
        request,
        "registration_portal/registration_verification_pending.html",
        {
            "studio": studio,
            "registration_session": registration_session,
            "embed_mode": registration_session.embed_mode,
        },
    )


@xframe_options_exempt
def registration_verify_email(
    request,
    studio_slug,
    token,
):
    studio = get_object_or_404(
        Studio, slug=studio_slug, is_active=True
    )
    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    if registration_uses_existing_account(registration_session):
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="policies",
        )

    code = (
        request.POST.get("code")
        if request.method == "POST"
        else request.GET.get("code")
    ) or ""
    code = code.strip()
    valid, error = validate_registration_verification_code(
        registration_session, code
    )

    if request.method == "POST" and valid:
        mark_registration_email_verified(registration_session)
        registration_session.status = (
            PublicRegistrationSession.Status.IN_PROGRESS
        )
        registration_session.current_step = "policies"
        registration_session.save(
            update_fields=[
                "status",
                "current_step",
                "updated_at",
            ]
        )
        registration_session.touch()
        messages.success(
            request,
            "Email verified. Review the studio policies and agreements to continue.",
        )
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="policies",
        )

    return render(
        request,
        "registration_portal/registration_verify_email.html",
        {
            "studio": studio,
            "registration_session": registration_session,
            "code": code,
            "verification_valid": valid,
            "verification_error": error,
            "embed_mode": registration_session.embed_mode,
        },
        status=200 if valid else 400,
    )


@xframe_options_exempt
def registration_complete_free(
    request,
    studio_slug,
    token,
):
    if request.method != "POST":
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio_slug,
            token=token,
            step="ready",
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    if not registration_identity_verified(registration_session):
        return redirect(
            "registration_portal:registration_verification_pending",
            studio_slug=studio.slug,
            token=registration_session.token,
        )

    if not registration_policies_satisfied(registration_session):
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="policies",
        )

    pricing = registration_session.pricing_snapshot or {}

    amount = Decimal(
        str(
            pricing.get(
                "due_today",
                "0.00",
            )
        )
    )

    from .addon_services import is_addon
    if is_addon(registration_session):
        if not request.user.is_authenticated or request.user.pk != (registration_session.account_data or {}).get('existing_user_id'):
            return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)
        if registration_session.status not in {
            PublicRegistrationSession.Status.READY_FOR_PAYMENT,
            PublicRegistrationSession.Status.PAYMENT_PENDING,
        }:
            return redirect('registration_portal:registration_wizard',
                studio_slug=studio.slug, token=registration_session.token, step='review')
        if amount > Decimal('0.00'):
            return redirect('registration_portal:registration_wizard',
                studio_slug=studio.slug, token=registration_session.token, step='ready')
    payments_available = (
        connected_subscription_for_registration(registration_session)
        is not None
    )
    if amount > Decimal("0.00") and payments_available:
        return redirect(
            "registration_portal:registration_wizard",
            studio_slug=studio.slug,
            token=registration_session.token,
            step="ready",
        )

    finalize_public_registration(
        registration_session,
        paid_amount=Decimal("0.00"),
    )

    return redirect(
        "registration_portal:registration_complete",
        studio_slug=studio.slug,
        token=registration_session.token,
    )


@xframe_options_exempt
def registration_payment_return(
    request,
    studio_slug,
    token,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    from .addon_services import is_addon
    if is_addon(registration_session) and (
        not request.user.is_authenticated or
        request.user.pk != (registration_session.account_data or {}).get('existing_user_id')
    ):
        return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)

    if not registration_identity_verified(registration_session):
        return redirect(
            "registration_portal:registration_verification_pending",
            studio_slug=studio.slug,
            token=registration_session.token,
        )

    try:
        result = finalize_if_payment_succeeded(
            registration_session
        )
    except Exception:
        result = None

    if result is not None:
        return redirect(
            "registration_portal:registration_complete",
            studio_slug=studio.slug,
            token=registration_session.token,
        )

    return render(
        request,
        "registration_portal/payment_processing.html",
        {
            "studio": studio,
            "registration_session": registration_session,
            "embed_mode": registration_session.embed_mode,
        },
    )


def _notify_admins_registration_complete(registration_session):
    studio = registration_session.studio
    student = registration_session.linked_student

    if student is not None:
        subject = f"{student.first_name} {student.last_name}".strip()
    else:
        subject = registration_session.contact_email or "A new registrant"

    for admin in administrator_users(studio):
        create_workspace_notification(
            studio=studio,
            user=admin,
            category=WorkspaceNotification.Category.REGISTRATION,
            kind="registration_completed",
            title="New Registration Completed",
            message=f"{subject} completed public registration.",
            dedupe_key=(
                f"registration-completed-{registration_session.pk}-"
                f"{admin.pk}"
            ),
            preference_field="registration_new",
        )


@xframe_options_exempt
def registration_complete(
    request,
    studio_slug,
    token,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_session = get_object_or_404(
        PublicRegistrationSession,
        studio=studio,
        token=token,
    )

    from .addon_services import is_addon
    if is_addon(registration_session) and (
        not request.user.is_authenticated or
        request.user.pk != (registration_session.account_data or {}).get('existing_user_id')
    ):
        return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)

    if not registration_identity_verified(registration_session):
        return redirect(
            "registration_portal:registration_verification_pending",
            studio_slug=studio.slug,
            token=registration_session.token,
        )

    if (
        registration_session.status
        != PublicRegistrationSession.Status.COMPLETED
    ):
        try:
            finalize_if_payment_succeeded(
                registration_session
            )
            registration_session.refresh_from_db()
        except Exception:
            pass

    if (
        registration_session.status
        != PublicRegistrationSession.Status.COMPLETED
    ):
        return redirect(
            "registration_portal:registration_payment_return",
            studio_slug=studio.slug,
            token=registration_session.token,
        )

    _notify_admins_registration_complete(
        registration_session
    )

    linked_user = registration_session.linked_user

    if linked_user is not None:
        login(
            request,
            linked_user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

    if (
        registration_session.registration_type
        == PublicRegistrationSession.RegistrationType.SELF
    ):
        request.session[
            "encore_workspace_role"
        ] = "student"
        request.session[
            "encore_workspace_studio_slug"
        ] = studio.slug

        messages.success(
            request,
            "Registration complete. Welcome to your Encore student portal.",
        )

        return redirect(
            "dashboard:student_dashboard",
            studio_slug=studio.slug,
        )

    request.session[
        "encore_workspace_role"
    ] = "family"
    request.session[
        "encore_workspace_studio_slug"
    ] = studio.slug

    messages.success(
        request,
        "Registration complete. Welcome to your parent portal.",
    )

    return redirect(
        "dashboard:family_dashboard",
        studio_slug=studio.slug,
    )


def public_class_catalog(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    settings_obj, widget_settings = _widget_settings(studio)
    classes, filters = _filter_public_class_queryset(
        request, studio, _public_classes(studio), widget_settings
    )
    rows = _class_rows(classes)
    if filters["availability"] == "open":
        rows = [row for row in rows if not row["is_full"]]

    return render(request, "registration_portal/class_catalog.html", {
        "studio": studio,
        "class_rows": rows,
        "seasons": Season.objects.filter(studio=studio, is_active=True).order_by("-start_date", "name"),
        "class_types": ClassType.objects.filter(studio=studio, is_active=True).order_by("name"),
        "class_levels": ClassLevel.objects.filter(studio=studio, is_active=True).order_by("number", "name"),
        "filters": filters,
        "embed_mode": False,
        "widget_style": widget_settings["classes_style"],
        "show_class_pricing": widget_settings["show_class_pricing"],
        "show_class_capacity": widget_settings["show_class_capacity"],
        "registration_enabled": settings_obj.public_registration_enabled and widget_settings["registration_enabled"],
    })


@xframe_options_exempt
def embedded_class_catalog(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    settings_obj, widget_settings = _widget_settings(studio)
    classes, filters = _filter_public_class_queryset(
        request, studio, _public_classes(studio), widget_settings
    )
    rows = _class_rows(classes)
    if filters["availability"] == "open":
        rows = [row for row in rows if not row["is_full"]]

    return render(request, "registration_portal/class_catalog.html", {
        "studio": studio,
        "class_rows": rows,
        "seasons": Season.objects.filter(studio=studio, is_active=True).order_by("-start_date", "name"),
        "class_types": ClassType.objects.filter(studio=studio, is_active=True).order_by("name"),
        "class_levels": ClassLevel.objects.filter(studio=studio, is_active=True).order_by("number", "name"),
        "filters": filters,
        "embed_mode": True,
        "widget_style": widget_settings["classes_style"],
        "show_class_pricing": widget_settings["show_class_pricing"],
        "show_class_capacity": widget_settings["show_class_capacity"],
        "registration_enabled": settings_obj.public_registration_enabled and widget_settings["registration_enabled"],
    })


@xframe_options_exempt
def public_class_detail(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    settings_obj, widget_settings = _widget_settings(
        studio
    )

    class_instance = get_object_or_404(
        _public_classes(studio),
        pk=class_id,
    )

    embed_mode = (
        request.GET.get("embed") == "1"
    )

    enrolled = (
        class_instance.active_enrollment_count
    )

    capacity = (
        class_instance.capacity
        or 0
    )

    remaining = (
        max(
            capacity - enrolled,
            0,
        )
        if capacity
        else None
    )

    return render(
        request,
        "registration_portal/class_detail.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "remaining": remaining,
            "is_full": (
                capacity > 0
                and enrolled >= capacity
            ),
            "embed_mode": embed_mode,
            "widget_style": widget_settings[
                "classes_style"
            ],
            "show_class_pricing": widget_settings[
                "show_class_pricing"
            ],
            "show_class_capacity": widget_settings[
                "show_class_capacity"
            ],
            "registration_enabled": (
                settings_obj.public_registration_enabled
                and widget_settings[
                    "registration_enabled"
                ]
            ),
        },
    )


@xframe_options_exempt
def public_registration_request(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _registration_available(
        studio
    ):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    _settings_obj, widget_settings = _widget_settings(
        studio
    )

    class_instance = get_object_or_404(
        _public_classes(studio),
        pk=class_id,
    )

    embed_mode = (
        request.GET.get("embed") == "1"
    )

    enrolled = (
        class_instance.active_enrollment_count
    )

    capacity = (
        class_instance.capacity
        or 0
    )

    is_full = (
        capacity > 0
        and enrolled >= capacity
    )

    form = PublicRegistrationRequestForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        registration_request = (
            form.save(
                commit=False
            )
        )

        registration_request.studio = (
            studio
        )

        registration_request.class_instance = (
            class_instance
        )

        registration_request.full_clean()
        registration_request.save()

        guardian = (
            matching_guardian_for_request(
                registration_request
            )
        )

        existing_user = (
            matching_user_for_request(
                registration_request
            )
        )

        if (
            guardian
            and guardian.user_id
        ) or existing_user:
            request.session[
                "pending_registration_request_id"
            ] = registration_request.id

            query = urlencode(
                {
                    "next": (
                        f"/registration/"
                        f"continue/"
                        f"{studio.slug}/"
                        f"{registration_request.id}/"
                    )
                }
            )

            return redirect(
                f"/accounts/login/?{query}"
            )

        return redirect(
            "registration_portal:new_family_signup",
            studio_slug=studio.slug,
            request_id=registration_request.pk,
        )

    return render(
        request,
        "registration_portal/registration_form.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "form": form,
            "is_full": is_full,
            "embed_mode": embed_mode,
            "widget_style": widget_settings[
                "registration_style"
            ],
        },
    )


def new_family_signup(
    request,
    studio_slug,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_request = get_object_or_404(
        RegistrationRequest.objects.select_related(
            "class_instance"
        ),
        pk=request_id,
        studio=studio,
        status=RegistrationRequest.Status.NEW,
    )

    if matching_user_for_request(
        registration_request
    ):
        query = urlencode(
            {
                "next": (
                    f"/registration/"
                    f"continue/"
                    f"{studio.slug}/"
                    f"{registration_request.id}/"
                )
            }
        )

        return redirect(
            f"/accounts/login/?{query}"
        )

    form = NewFamilyAccountForm(
        request.POST or None,
        email=registration_request.email,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            result = (
                create_new_family_from_request(
                    registration_request=registration_request,
                    password=form.cleaned_data[
                        "password1"
                    ],
                )
            )
        except ValueError as exc:
            form.add_error(
                None,
                str(exc),
            )
        else:
            login(
                request,
                result["user"],
            )

            request.session[
                "encore_workspace_role"
            ] = "family"

            request.session[
                "encore_workspace_studio_slug"
            ] = studio.slug

            messages.success(
                request,
                "Your Encore family account is ready.",
            )

            return redirect(
                "registration_portal:legacy_registration_complete",
                studio_slug=studio.slug,
                request_id=registration_request.pk,
            )

    return render(
        request,
        "registration_portal/new_family_signup.html",
        {
            "studio": studio,
            "registration_request": registration_request,
            "form": form,
        },
    )


@login_required
def continue_registration(
    request,
    studio_slug,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_request = get_object_or_404(
        RegistrationRequest.objects.select_related(
            "class_instance"
        ),
        pk=request_id,
        studio=studio,
    )

    guardian = (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related(
            "family"
        )
        .first()
    )

    if guardian is None:
        return render(
            request,
            "registration_portal/account_match_required.html",
            {
                "studio": studio,
                "registration_request": registration_request,
            },
        )

    family = guardian.family

    existing_student = (
        matching_student_for_request(
            registration_request,
            family,
        )
    )

    if request.method == "POST":
        selected_student_id = (
            request.POST.get(
                "student_id",
                "",
            ).strip()
        )

        selected_student = None

        if selected_student_id:
            selected_student = (
                family.students
                .filter(
                    studio=studio,
                    pk=selected_student_id,
                    is_active=True,
                )
                .first()
            )

        result = (
            convert_request_for_existing_family(
                registration_request=registration_request,
                family=family,
                student=selected_student,
            )
        )

        enrollment = (
            result["enrollment"]
        )

        request.session[
            "encore_workspace_role"
        ] = "family"

        request.session[
            "encore_workspace_studio_slug"
        ] = studio.slug

        messages.success(
            request,
            (
                "Registration completed. "
                f"Enrollment status: "
                f"{enrollment.get_status_display()}."
            ),
        )

        return redirect(
            "registration_portal:legacy_registration_complete",
            studio_slug=studio.slug,
            request_id=registration_request.pk,
        )

    return render(
        request,
        "registration_portal/continue_registration.html",
        {
            "studio": studio,
            "registration_request": registration_request,
            "family": family,
            "students": (
                family.students
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "first_name",
                    "last_name",
                )
            ),
            "existing_student": existing_student,
        },
    )


@login_required
def legacy_registration_complete(
    request,
    studio_slug,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    registration_request = get_object_or_404(
        RegistrationRequest.objects.select_related(
            "class_instance",
            "linked_student",
            "linked_enrollment",
        ),
        pk=request_id,
        studio=studio,
    )

    return render(
        request,
        "registration_portal/registration_complete.html",
        {
            "studio": studio,
            "registration_request": registration_request,
        },
    )


def _admin_workspace(
    request,
    studio,
):
    if request.user.is_superuser:
        return True

    return (
        request.session.get(
            "encore_workspace_role"
        )
        == "administrator"
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role="administrator",
            is_active=True,
        ).exists()
    )


@login_required
def invite_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    invites = (
        FamilyInvite.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "family",
            "created_by",
        )
    )

    return render(
        request,
        "registration_portal/invite_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "invites": invites,
        },
    )


@login_required
def invite_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = FamilyInviteForm(
        request.POST or None,
        studio=studio,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        invite = form.save(
            commit=False
        )

        invite.studio = studio
        invite.created_by = request.user
        invite.save()

        invite_url = request.build_absolute_uri(
            f"/registration/"
            f"invite/{invite.token}/"
        )

        from communications.studio_email import send_studio_email
        from django.utils.html import escape
        invite_body = (
            f"You have been invited to set up your family account for {studio.name}.\n\n"
            f"Complete setup here:\n{invite_url}\n\n"
            f"This link expires on {invite.expires_at:%B %d, %Y}."
        )
        send_studio_email(
            studio=studio, to=[invite.email],
            subject=f"You're invited to {studio.name} on Encore",
            html_body=f'<div style="white-space:pre-line">{escape(invite_body)}</div>',
            text_body=invite_body, sensitive=True,
            tags={'message_type':'family_invitation'},
        )


        request.session[
            "last_family_invite_url"
        ] = invite_url

        messages.success(
            request,
            "Family invite created.",
        )

        return redirect(
            "registration_portal:invite_created",
            studio_slug=studio.slug,
            invite_id=invite.pk,
        )

    return render(
        request,
        "registration_portal/invite_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
        },
    )


@login_required
def invite_created(
    request,
    studio_slug,
    invite_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    invite = get_object_or_404(
        FamilyInvite,
        pk=invite_id,
        studio=studio,
    )

    invite_url = request.session.get(
        "last_family_invite_url"
    ) or request.build_absolute_uri(
        f"/registration/"
        f"invite/{invite.token}/"
    )

    return render(
        request,
        "registration_portal/invite_created.html",
        {
            "studio": studio,
            "role": "administrator",
            "invite": invite,
            "invite_url": invite_url,
        },
    )


def accept_invite(
    request,
    token,
):
    invite = get_object_or_404(
        FamilyInvite.objects.select_related(
            "studio",
            "family",
        ),
        token=token,
    )

    form = AcceptInviteForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        if not invite.is_usable:
            form.add_error(
                None,
                "This invite has expired or was already used.",
            )
        else:
            try:
                result = accept_family_invite(
                    invite=invite,
                    password=form.cleaned_data[
                        "password1"
                    ],
                )
            except ValueError as exc:
                form.add_error(
                    None,
                    str(exc),
                )
            else:
                login(
                    request,
                    result["user"],
                )

                request.session[
                    "encore_workspace_role"
                ] = "family"

                request.session[
                    "encore_workspace_studio_slug"
                ] = invite.studio.slug

                return redirect(
                    "dashboard:family_dashboard",
                    studio_slug=invite.studio.slug,
                )

    return render(
        request,
        "registration_portal/accept_invite.html",
        {
            "invite": invite,
            "studio": invite.studio,
            "form": form,
        },
    )
