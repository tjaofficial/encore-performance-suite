from calendar import monthcalendar
from datetime import date
from urllib.parse import urlencode

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

from classes.models import Class, ClassType, Season
from enrollments.models import Enrollment
from families.models import Guardian
from studios.models import Studio, StudioSettings
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
    "ready",
}


def _wizard_class_queryset(
    studio,
    student_data=None,
):
    classes = _public_classes(
        studio
    ).filter(
        registration_open=True,
        season__registration_open=True,
    )

    settings_obj, widget_settings = (
        _widget_settings(studio)
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

    birthday_raw = (
        (student_data or {}).get(
            "birthday"
        )
        or ""
    )

    age = None

    if birthday_raw:
        try:
            birthday = date.fromisoformat(
                birthday_raw
            )
            today = timezone.localdate()
            age = (
                today.year
                - birthday.year
                - (
                    (today.month, today.day)
                    < (
                        birthday.month,
                        birthday.day,
                    )
                )
            )
        except ValueError:
            age = None

    if age is not None:
        classes = classes.filter(
            Q(min_age__isnull=True)
            | Q(min_age__lte=age),
            Q(max_age__isnull=True)
            | Q(max_age__gte=age),
        )

    existing_student_id = (
        (student_data or {}).get(
            "existing_student_id"
        )
    )

    if existing_student_id:
        classes = classes.exclude(
            enrollments__student_id=existing_student_id,
        )

    return classes


def _serialize_form_value(value):
    if hasattr(
        value,
        "isoformat",
    ):
        return value.isoformat()

    return value


def _safe_saved_form_data(data):
    return {
        key: value
        for key, value in (
            data or {}
        ).items()
        if not key.endswith(
            "_hash"
        )
    }


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

    if not _registration_available(
        studio
    ):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    embed_mode = (
        request.GET.get(
            "embed"
        ) == "1"
    )

    registration_session = (
        PublicRegistrationSession.objects.create(
            studio=studio,
            embed_mode=embed_mode,
        )
    )

    preselected_class_id = (
        request.GET.get(
            "class",
            "",
        ).strip()
    )

    if preselected_class_id:
        class_instance = (
            _wizard_class_queryset(
                studio
            )
            .filter(
                pk=preselected_class_id
            )
            .first()
        )

        if class_instance is not None:
            registration_session.selected_classes.add(
                class_instance
            )

    return redirect(
        "registration_portal:registration_wizard",
        studio_slug=studio.slug,
        token=registration_session.token,
        step="type",
    )


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

    registration_session.mark_expired()

    if (
        registration_session.status
        == PublicRegistrationSession.Status.EXPIRED
    ):
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

    if not _registration_available(
        studio
    ):
        return render(
            request,
            "registration_portal/registration_disabled.html",
            {"studio": studio},
            status=403,
        )

    _settings_obj, widget_settings = (
        _widget_settings(studio)
    )

    form = None
    class_rows = []
    pricing = None

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

        if (
            request.method == "POST"
            and form.is_valid()
        ):
            registration_session.registration_type = (
                form.cleaned_data[
                    "registration_type"
                ]
            )
            registration_session.current_step = (
                "account"
            )
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

        saved = _safe_saved_form_data(
            registration_session.account_data
        )

        returning_form = ExistingAccountLoginForm(
            request.POST if (
                request.method == "POST"
                and request.POST.get("account_action") == "existing"
            ) else None,
            request=request,
        )

        if (
            registration_session.registration_type
            == PublicRegistrationSession.RegistrationType.SELF
        ):
            form = SelfAccountDetailsForm(
                request.POST if (
                    request.method == "POST"
                    and request.POST.get("account_action") != "existing"
                ) else None,
                saved_data=saved,
            )
        else:
            form = GuardianAccountDetailsForm(
                request.POST if (
                    request.method == "POST"
                    and request.POST.get("account_action") != "existing"
                ) else None,
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
                    Guardian.objects
                    .filter(
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
                        (
                            "This Encore account is valid, but it is not "
                            "connected to a family at this studio yet. "
                            "Use New to Encore below for this studio, or "
                            "ask the studio to connect the account."
                        ),
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
                    }
                    registration_session.contact_email = user.email
                    registration_session.student_data = {}
                    registration_session.current_step = "student"
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
                        step="student",
                    )

            else:
                existing_student = (
                    Student.objects
                    .filter(
                        user=user,
                        studio=studio,
                        is_active=True,
                    )
                    .select_related("family")
                    .first()
                )

                if (
                    existing_student is None
                    and hasattr(user, "student_profile")
                    and user.student_profile is not None
                ):
                    returning_form.add_error(
                        None,
                        (
                            "This login is already attached to a student "
                            "record at another studio. Multi-studio student "
                            "profiles are not enabled yet."
                        ),
                    )
                else:
                    registration_session.account_data = {
                        "account_mode": "existing",
                        "existing_user_id": user.pk,
                        "existing_family_id": (
                            existing_student.family_id
                            if existing_student is not None
                            else None
                        ),
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "email": user.email,
                    }
                    registration_session.contact_email = user.email

                    if existing_student is not None:
                        registration_session.student_data = {
                            "existing_student_id": existing_student.pk,
                            "student_first_name": existing_student.first_name,
                            "student_last_name": existing_student.last_name,
                            "birthday": existing_student.birthday.isoformat(),
                            "gender": existing_student.gender,
                        }
                        registration_session.current_step = "classes"
                    else:
                        registration_session.student_data = {}
                        registration_session.current_step = "student"

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
                        step=registration_session.current_step,
                    )

        elif (
            request.method == "POST"
            and request.POST.get("account_action") != "existing"
            and form.is_valid()
        ):
            serialized = {
                key: _serialize_form_value(
                    value
                )
                for key, value in form.serialized_data().items()
            }

            serialized["account_mode"] = "new"

            registration_session.account_data = serialized
            registration_session.contact_email = (
                serialized.get(
                    "email",
                    "",
                )
            )
            registration_session.student_data = {}
            registration_session.current_step = (
                "student"
            )
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
                step="student",
            )

    elif step == "student":
        if not registration_session.account_data:
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="account",
            )

        existing_students = Student.objects.none()
        existing_family_id = (
            registration_session.account_data.get(
                "existing_family_id"
            )
        )

        if (
            registration_session.registration_type
            == PublicRegistrationSession.RegistrationType.STUDENT
            and existing_family_id
        ):
            existing_students = (
                Student.objects
                .filter(
                    studio=studio,
                    family_id=existing_family_id,
                    is_active=True,
                )
                .order_by(
                    "first_name",
                    "last_name",
                )
            )

        if (
            request.method == "POST"
            and request.POST.get("student_action") == "existing"
        ):
            student_id = request.POST.get(
                "existing_student_id"
            )

            existing_student = (
                existing_students
                .filter(pk=student_id)
                .first()
            )

            if existing_student is None:
                messages.error(
                    request,
                    "Choose a student from this household.",
                )
            else:
                registration_session.student_data = {
                    "existing_student_id": existing_student.pk,
                    "student_first_name": existing_student.first_name,
                    "student_last_name": existing_student.last_name,
                    "birthday": existing_student.birthday.isoformat(),
                    "gender": existing_student.gender,
                }
                registration_session.selected_classes.clear()
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

        saved = _safe_saved_form_data(
            registration_session.student_data
        )

        if saved.get("existing_student_id"):
            saved = {}

        form = StudentDetailsForm(
            request.POST if (
                request.method == "POST"
                and request.POST.get("student_action") != "existing"
            ) else None,
            registration_type=(
                registration_session.registration_type
            ),
            account_email=(
                registration_session.contact_email
            ),
            account_data=(
                registration_session.account_data
            ),
            saved_data=saved,
        )

        if (
            request.method == "POST"
            and request.POST.get("student_action") != "existing"
            and form.is_valid()
        ):
            serialized = {
                key: _serialize_form_value(
                    value
                )
                for key, value in form.serialized_data().items()
            }

            serialized.pop(
                "existing_student_id",
                None,
            )

            registration_session.student_data = (
                serialized
            )
            registration_session.selected_classes.clear()
            registration_session.current_step = (
                "classes"
            )
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

    elif step == "classes":
        if not registration_session.student_data:
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="student",
            )

        classes = _wizard_class_queryset(
            studio,
            registration_session.student_data,
        )

        selected_ids = list(
            registration_session
            .selected_classes
            .values_list(
                "pk",
                flat=True,
            )
        )

        form = ClassSelectionForm(
            request.POST or None,
            queryset=classes,
            selected_ids=selected_ids,
        )

        class_rows = _class_rows(
            classes
        )

        if (
            request.method == "POST"
            and form.is_valid()
        ):
            registration_session.selected_classes.set(
                form.cleaned_data[
                    "classes"
                ]
            )

            registration_pricing_snapshot(
                registration_session
            )

            registration_session.current_step = (
                "review"
            )
            registration_session.save(
                update_fields=[
                    "current_step",
                    "updated_at",
                ]
            )
            registration_session.touch()

            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="review",
            )

    elif step == "review":
        if not registration_session.selected_classes.exists():
            return redirect(
                "registration_portal:registration_wizard",
                studio_slug=studio.slug,
                token=registration_session.token,
                step="classes",
            )

        pricing = registration_pricing_snapshot(
            registration_session
        )

        form = RegistrationReviewForm(
            request.POST or None
        )

        if (
            request.method == "POST"
            and form.is_valid()
        ):
            registration_session.status = (
                PublicRegistrationSession.Status.READY_FOR_PAYMENT
            )
            registration_session.current_step = (
                "ready"
            )
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
        if (
            registration_session.status
            not in {
                PublicRegistrationSession.Status.READY_FOR_PAYMENT,
                PublicRegistrationSession.Status.PAYMENT_PENDING,
            }
        ):
            if (
                registration_session.status
                == PublicRegistrationSession.Status.COMPLETED
            ):
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
            or registration_pricing_snapshot(
                registration_session
            )
        )

        payment_setup = {
            "amount": Decimal(
                str(
                    pricing.get(
                        "due_today",
                        "0.00",
                    )
                )
            ),
            "client_secret": "",
            "connected_account_id": "",
            "payment_intent_id": "",
        }

        payment_error = ""

        if payment_setup["amount"] > Decimal("0.00"):
            try:
                payment_setup = prepare_registration_payment(
                    request,
                    registration_session,
                )

                registration_session.refresh_from_db()
                pricing = (
                    registration_session.pricing_snapshot
                )
            except Exception as exc:
                payment_error = str(exc)
        else:
            payment_setup["amount"] = Decimal("0.00")

    context = {
        "studio": studio,
        "registration_session": registration_session,
        "step": step,
        "form": form,
        "class_rows": class_rows,
        "pricing": pricing,
        "account_data": _safe_saved_form_data(
            registration_session.account_data
        ),
        "student_data": _safe_saved_form_data(
            registration_session.student_data
        ),
        "returning_form": (
            returning_form
            if step == "account"
            else None
        ),
        "existing_students": (
            existing_students
            if step == "student"
            else Student.objects.none()
        ),
        "selected_classes": (
            registration_session
            .selected_classes
            .select_related(
                "season",
                "class_type",
                "tuition_plan",
            )
            .prefetch_related(
                "meeting_times",
            )
            .order_by(
                "season__start_date",
                "name",
            )
        ),
        "embed_mode": registration_session.embed_mode,
        "widget_style": widget_settings[
            "registration_style"
        ],
        "payment_setup": (
            payment_setup
            if step == "ready"
            else None
        ),
        "payment_error": (
            payment_error
            if step == "ready"
            else ""
        ),
        "stripe_publishable_key": (
            settings.STRIPE_PUBLISHABLE_KEY
            if step == "ready"
            else ""
        ),
    }

    return render(
        request,
        "registration_portal/registration_wizard.html",
        context,
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

    pricing = registration_session.pricing_snapshot or {}

    amount = Decimal(
        str(
            pricing.get(
                "due_today",
                "0.00",
            )
        )
    )

    if amount > Decimal("0.00"):
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

    enrollments = (
        Enrollment.objects
        .filter(
            student=registration_session.linked_student,
            class_instance__in=registration_session.selected_classes.all(),
        )
        .select_related(
            "class_instance",
            "class_instance__season",
        )
        .order_by(
            "class_instance__name",
        )
    )

    return render(
        request,
        "registration_portal/registration_complete.html",
        {
            "studio": studio,
            "registration_session": registration_session,
            "student": registration_session.linked_student,
            "payment": registration_session.linked_payment,
            "enrollments": enrollments,
            "embed_mode": registration_session.embed_mode,
        },
    )


def public_class_catalog(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    settings_obj, widget_settings = _widget_settings(
        studio
    )

    classes = _public_classes(
        studio
    )

    search = request.GET.get(
        "q",
        "",
    ).strip()

    season_id = request.GET.get(
        "season",
        "",
    ).strip()

    class_type_id = request.GET.get(
        "type",
        "",
    ).strip()

    availability = request.GET.get(
        "availability",
        "",
    ).strip()

    if search:
        classes = classes.filter(
            Q(name__icontains=search)
            | Q(class_id__icontains=search)
            | Q(description__icontains=search)
        )

    effective_season_id = (
        season_id
        or widget_settings.get(
            "default_season"
        )
    )

    if effective_season_id:
        classes = classes.filter(
            season_id=effective_season_id,
        )

    if class_type_id:
        classes = classes.filter(
            class_type_id=class_type_id,
        )

    rows = _class_rows(
        classes
    )

    if availability == "open":
        rows = [
            row
            for row in rows
            if not row["is_full"]
        ]

    return render(
        request,
        "registration_portal/class_catalog.html",
        {
            "studio": studio,
            "class_rows": rows,
            "seasons": Season.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by(
                "-start_date",
                "name",
            ),
            "class_types": ClassType.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("name"),
            "filters": {
                "q": search,
                "season": season_id,
                "type": class_type_id,
                "availability": availability,
            },
            "embed_mode": False,
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
def embedded_class_catalog(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    settings_obj, widget_settings = _widget_settings(
        studio
    )

    classes = _public_classes(
        studio
    )

    default_season_id = widget_settings.get(
        "default_season"
    )

    if default_season_id:
        classes = classes.filter(
            season_id=default_season_id,
        )

    search = request.GET.get(
        "q",
        "",
    ).strip()

    class_type_id = request.GET.get(
        "type",
        "",
    ).strip()

    if search:
        classes = classes.filter(
            Q(name__icontains=search)
            | Q(class_id__icontains=search)
            | Q(description__icontains=search)
        )

    if class_type_id:
        classes = classes.filter(
            class_type_id=class_type_id,
        )

    return render(
        request,
        "registration_portal/class_catalog.html",
        {
            "studio": studio,
            "class_rows": _class_rows(
                classes
            ),
            "seasons": [],
            "class_types": ClassType.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("name"),
            "filters": {
                "q": search,
                "season": "",
                "type": class_type_id,
                "availability": "",
            },
            "embed_mode": True,
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
                "registration_portal:registration_complete",
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
            "registration_portal:registration_complete",
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
def registration_complete(
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

        send_mail(
            subject=(
                f"You're invited to "
                f"{studio.name} on Encore"
            ),
            message=(
                f"You have been invited to set up "
                f"your family account for {studio.name}.\n\n"
                f"Complete setup here:\n{invite_url}\n\n"
                f"This link expires on "
                f"{invite.expires_at:%B %d, %Y}."
            ),
            from_email=getattr(
                settings,
                "DEFAULT_FROM_EMAIL",
                None,
            ),
            recipient_list=[
                invite.email,
            ],
            fail_silently=True,
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
