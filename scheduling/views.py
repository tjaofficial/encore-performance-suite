from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from instructors.models import Instructor
from studios.models import Studio

from .calendar_services import (
    absence_calendar_items,
    ensure_default_main_categories,
    event_json,
    expand_calendar_event,
    get_calendar_preference,
    affected_occurrences_for_time_off_date,
    approved_occurrences_needing_coverage,
    complete_time_off_admin_task,
    create_time_off_admin_task,
    notify_substitute_assignment,
    notify_teacher_time_off_decision,
    substitute_availability_for_occurrence,
    substitute_calendar_items,
    substitute_conflicts_for_occurrence,
    task_calendar_items,
    teacher_is_off_for_occurrence,
    time_off_calendar_items,
    time_off_has_complete_coverage,
    visible_calendar_events,
)
from .forms import (
    CalendarCategoryForm,
    CalendarEventForm,
    CalendarPreferenceForm,
    SubstituteCoverageForm,
    TeacherTimeOffRequestForm,
    TimeOffDecisionForm,
)
from .models import (
    CalendarCategory,
    CalendarEvent,
    CalendarPreference,
    ClassOccurrenceOverride,
    TeacherTimeOffDate,
    TeacherTimeOffRequest,
)
from .services import (
    generate_class_occurrences,
    get_user_role_for_studio,
    get_visible_classes_for_user,
)


def _access_denied(request, studio):
    return render(
        request,
        "scheduling/calendar_access_denied.html",
        {"studio": studio},
        status=403,
    )


def _date_range(request):
    start_raw = request.GET.get("start")
    end_raw = request.GET.get("end")

    start_dt = parse_datetime(start_raw) if start_raw else None
    end_dt = parse_datetime(end_raw) if end_raw else None

    start_date = (
        start_dt.date()
        if start_dt
        else parse_date(start_raw)
        if start_raw
        else date.today().replace(day=1)
    )

    if end_dt:
        end_date = end_dt.date()
    elif end_raw and parse_date(end_raw):
        end_date = parse_date(end_raw)
    else:
        end_date = start_date

    return start_date, end_date


def _csv_ids(value):
    if not value:
        return set()

    return {
        int(item)
        for item in value.split(",")
        if item.strip().isdigit()
    }


@login_required
def calendar_page(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role is None:
        return _access_denied(
            request,
            studio,
        )

    preference = get_calendar_preference(
        request.user,
        studio,
    )

    if role == "administrator":
        ensure_default_main_categories(
            studio
        )

    visible_classes = (
        get_visible_classes_for_user(
            request.user,
            studio,
        )
        .select_related(
            "instructor",
            "instructor__user",
            "assistant_instructor",
            "assistant_instructor__user",
        )
        .order_by("name")
    )

    main_categories = (
        CalendarCategory.objects
        .filter(
            studio=studio,
            scope=CalendarCategory.Scope.MAIN,
            owner__isnull=True,
            is_active=True,
        )
        .order_by(
            "sort_order",
            "name",
        )
    )

    personal_categories = (
        CalendarCategory.objects
        .filter(
            studio=studio,
            scope=CalendarCategory.Scope.PERSONAL,
            owner=request.user,
            is_active=True,
        )
        .order_by(
            "sort_order",
            "name",
        )
    )

    instructors = []

    if role == "administrator":
        instructor_ids = set()

        for class_instance in visible_classes:
            if class_instance.instructor_id:
                instructor_ids.add(
                    class_instance.instructor_id
                )

            if class_instance.assistant_instructor_id:
                instructor_ids.add(
                    class_instance.assistant_instructor_id
                )

        instructors = (
            Instructor.objects
            .filter(
                studio=studio,
                pk__in=instructor_ids,
                is_active=True,
            )
            .order_by(
                "last_name",
                "first_name",
            )
        )

    pending_time_off_count = 0

    if role == "administrator":
        pending_time_off_count = (
            TeacherTimeOffRequest.objects
            .filter(
                studio=studio,
                dates__status=TeacherTimeOffDate.Status.PENDING,
            )
            .distinct()
            .count()
        )

    return render(
        request,
        "scheduling/calendar.html",
        {
            "studio": studio,
            "role": role,
            "preference": preference,
            "visible_classes": visible_classes,
            "main_categories": main_categories,
            "personal_categories": personal_categories,
            "instructors": instructors,
            "can_create_main": role == "administrator",
            "can_create_personal": role in {
                "administrator",
                "teacher",
            },
            "pending_time_off_count": pending_time_off_count,
        },
    )


@login_required
def calendar_feed(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role is None:
        return JsonResponse(
            {
                "detail": (
                    "You do not have access to this studio."
                )
            },
            status=403,
        )

    start_date, end_date = _date_range(
        request
    )

    source_groups = {
        value.strip()
        for value
        in request.GET.get(
            "sources",
            "main,personal,classes,tasks,absences,time_off_requested,time_off_approved,substitutes",
        ).split(",")
        if value.strip()
    }

    selected_class_ids = _csv_ids(
        request.GET.get("class_ids")
    )

    selected_instructor_ids = _csv_ids(
        request.GET.get("instructor_ids")
    )

    hidden_category_ids = _csv_ids(
        request.GET.get("hidden_category_ids")
    )

    preference = get_calendar_preference(
        request.user,
        studio,
    )

    events = []

    if "classes" in source_groups:
        visible_classes = get_visible_classes_for_user(
            request.user,
            studio,
        )

        if selected_class_ids:
            visible_classes = visible_classes.filter(
                pk__in=selected_class_ids,
            )

        if selected_instructor_ids:
            visible_classes = visible_classes.filter(
                Q(
                    instructor_id__in=selected_instructor_ids
                )
                | Q(
                    assistant_instructor_id__in=selected_instructor_ids
                )
            ).distinct()

        for class_instance in visible_classes:
            occurrences = generate_class_occurrences(
                class_instance,
                start_date,
                end_date,
            )

            for occurrence in occurrences:
                if (
                    role == "teacher"
                    and teacher_is_off_for_occurrence(
                        request.user,
                        class_instance,
                        occurrence.start_at.date(),
                    )
                ):
                    continue

                events.append(
                    {
                        "id": (
                            f"class-{class_instance.pk}-"
                            f"{occurrence.start_at.isoformat()}"
                        ),
                        "title": occurrence.class_name,
                        "start": occurrence.start_at.isoformat(),
                        "end": occurrence.end_at.isoformat(),
                        "allDay": False,
                        "backgroundColor": "#0E169D",
                        "borderColor": "#0E169D",
                        "extendedProps": {
                            "sourceType": "class",
                            "sourceGroup": "classes",
                            "classId": class_instance.pk,
                            "classCode": occurrence.class_code,
                            "eventType": "Class",
                            "instructor": occurrence.instructor_name,
                            "instructorId": (
                                class_instance.instructor_id
                            ),
                            "assistantInstructorId": (
                                class_instance.assistant_instructor_id
                            ),
                            "location": occurrence.location_name,
                            "editable": False,
                            "deletable": False,
                            "detailUrl": reverse(
                                "classes:class_detail",
                                kwargs={
                                    "studio_slug": studio.slug,
                                    "class_id": class_instance.pk,
                                },
                            ),
                        },
                    }
                )

    calendar_events = visible_calendar_events(
        request.user,
        studio,
        role,
    )

    scope_query = Q(pk__in=[])

    if "main" in source_groups:
        scope_query |= Q(
            scope=CalendarEvent.Scope.MAIN
        )

    if "personal" in source_groups:
        scope_query |= Q(
            scope=CalendarEvent.Scope.PERSONAL,
            owner=request.user,
        )

    if scope_query:
        calendar_events = (
            calendar_events
            .filter(scope_query)
            .exclude(
                category_id__in=hidden_category_ids,
            )
        )

        for event in calendar_events:
            for occurrence in expand_calendar_event(
                event,
                start_date,
                end_date,
            ):
                events.append(
                    event_json(
                        event,
                        occurrence,
                        role=role,
                        user=request.user,
                    )
                )

    if "tasks" in source_groups:
        events.extend(
            task_calendar_items(
                request.user,
                studio,
                role,
                start_date,
                end_date,
                include_completed=(
                    preference.show_completed_tasks
                ),
            )
        )

    if "absences" in source_groups:
        events.extend(
            absence_calendar_items(
                request.user,
                studio,
                role,
                start_date,
                end_date,
            )
        )

    time_off_items = time_off_calendar_items(
        request.user,
        studio,
        role,
        start_date,
        end_date,
    )

    if (
        "time_off_requested"
        not in source_groups
    ):
        time_off_items = [
            item
            for item in time_off_items
            if item["extendedProps"][
                "sourceGroup"
            ]
            != "time_off_requested"
        ]

    if (
        "time_off_approved"
        not in source_groups
    ):
        time_off_items = [
            item
            for item in time_off_items
            if item["extendedProps"][
                "sourceGroup"
            ]
            != "time_off_approved"
        ]

    events.extend(
        time_off_items
    )

    if "substitutes" in source_groups:
        events.extend(
            substitute_calendar_items(
                request.user,
                studio,
                role,
                start_date,
                end_date,
            )
        )

    return JsonResponse(
        events,
        safe=False,
    )


@login_required
def event_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return JsonResponse(
            {
                "ok": False,
                "error": "You cannot create calendar events.",
            },
            status=403,
        )

    if request.method != "POST":
        return JsonResponse(
            {"ok": False},
            status=405,
        )

    form = CalendarEventForm(
        request.POST,
        studio=studio,
        user=request.user,
        role=role,
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    try:
        event = form.save()
    except ValidationError as exc:
        message_dict = getattr(exc, "message_dict", None)

        if message_dict:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {
                        field: [
                            {
                                "message": message,
                                "code": "",
                            }
                            for message in messages
                        ]
                        for field, messages
                        in message_dict.items()
                    },
                },
                status=400,
            )

        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(exc.messages),
            },
            status=400,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Encore could not save this calendar event. "
                    f"{exc}"
                ),
            },
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "eventId": event.pk,
        }
    )


@login_required
def event_detail(request, studio_slug, event_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role is None:
        return JsonResponse(
            {"ok": False},
            status=403,
        )

    event = get_object_or_404(
        visible_calendar_events(
            request.user,
            studio,
            role,
        ),
        pk=event_id,
    )

    can_edit = (
        (
            event.scope
            == CalendarEvent.Scope.MAIN
            and role == "administrator"
        )
        or (
            event.scope
            == CalendarEvent.Scope.PERSONAL
            and event.owner_id
            == request.user.id
        )
    )

    recurrence = None

    try:
        rule = event.recurrence
        recurrence = {
            "frequency": rule.frequency,
            "interval": rule.interval,
            "weekdays": rule.weekdays,
            "endType": rule.end_type,
            "endDate": (
                rule.end_date.isoformat()
                if rule.end_date
                else None
            ),
            "occurrenceCount": rule.occurrence_count,
        }
    except Exception:
        pass

    return JsonResponse(
        {
            "ok": True,
            "event": {
                "id": event.pk,
                "scope": event.scope,
                "title": event.title,
                "description": event.description,
                "eventType": event.event_type,
                "categoryId": event.category_id,
                "startAt": event.start_at.isoformat(),
                "endAt": event.end_at.isoformat(),
                "allDay": event.all_day,
                "location": event.location,
                "notes": event.notes,
                "isPublic": event.is_public,
                "recurrence": recurrence,
                "canEdit": can_edit,
                "canDelete": can_edit,
            },
        }
    )


@login_required
def event_update(request, studio_slug, event_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    event = get_object_or_404(
        CalendarEvent,
        pk=event_id,
        studio=studio,
        is_active=True,
    )

    can_edit = (
        (
            event.scope
            == CalendarEvent.Scope.MAIN
            and role == "administrator"
        )
        or (
            event.scope
            == CalendarEvent.Scope.PERSONAL
            and event.owner_id
            == request.user.id
        )
    )

    if not can_edit:
        return JsonResponse(
            {
                "ok": False,
                "error": "You cannot edit this event.",
            },
            status=403,
        )

    if request.method != "POST":
        return JsonResponse(
            {"ok": False},
            status=405,
        )

    form = CalendarEventForm(
        request.POST,
        instance=event,
        studio=studio,
        user=request.user,
        role=role,
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    try:
        form.save()
    except ValidationError as exc:
        message_dict = getattr(exc, "message_dict", None)

        if message_dict:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {
                        field: [
                            {
                                "message": message,
                                "code": "",
                            }
                            for message in messages
                        ]
                        for field, messages
                        in message_dict.items()
                    },
                },
                status=400,
            )

        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(exc.messages),
            },
            status=400,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Encore could not update this calendar event. "
                    f"{exc}"
                ),
            },
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
        }
    )


@login_required
def event_delete(request, studio_slug, event_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    event = get_object_or_404(
        CalendarEvent,
        pk=event_id,
        studio=studio,
        is_active=True,
    )

    can_delete = (
        (
            event.scope
            == CalendarEvent.Scope.MAIN
            and role == "administrator"
        )
        or (
            event.scope
            == CalendarEvent.Scope.PERSONAL
            and event.owner_id
            == request.user.id
        )
    )

    if not can_delete:
        return JsonResponse(
            {
                "ok": False,
                "error": "You cannot delete this event.",
            },
            status=403,
        )

    if request.method != "POST":
        return JsonResponse(
            {"ok": False},
            status=405,
        )

    event.is_active = False
    event.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
        }
    )


@login_required
def category_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return JsonResponse(
            {"ok": False},
            status=403,
        )

    if request.method != "POST":
        return JsonResponse(
            {"ok": False},
            status=405,
        )

    requested_scope = request.POST.get(
        "scope",
        CalendarCategory.Scope.PERSONAL,
    )

    if (
        requested_scope
        == CalendarCategory.Scope.MAIN
        and role != "administrator"
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Only administrators can create Main Event categories.",
            },
            status=403,
        )

    if requested_scope not in {
        CalendarCategory.Scope.MAIN,
        CalendarCategory.Scope.PERSONAL,
    }:
        requested_scope = (
            CalendarCategory.Scope.PERSONAL
        )

    form = CalendarCategoryForm(
        request.POST,
        studio=studio,
        user=request.user,
        scope=requested_scope,
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    category = form.save()

    return JsonResponse(
        {
            "ok": True,
            "category": {
                "id": category.pk,
                "name": category.name,
                "scope": category.scope,
                "color": category.color,
            },
        }
    )


@login_required
def preference_update(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role is None:
        return JsonResponse(
            {"ok": False},
            status=403,
        )

    if request.method != "POST":
        return JsonResponse(
            {"ok": False},
            status=405,
        )

    preference = get_calendar_preference(
        request.user,
        studio,
    )

    form = CalendarPreferenceForm(
        request.POST,
        instance=preference,
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    preference = form.save(
        commit=False
    )

    source_visibility = {}

    for key in [
        "main",
        "personal",
        "classes",
        "tasks",
        "absences",
        "time_off_requested",
        "time_off_approved",
        "substitutes",
    ]:
        source_visibility[key] = (
            request.POST.get(
                f"source_{key}"
            )
            == "1"
        )

    source_visibility[
        "hidden_category_ids"
    ] = [
        int(value)
        for value
        in request.POST.get(
            "hidden_category_ids",
            "",
        ).split(",")
        if value.strip().isdigit()
    ]

    source_visibility[
        "selected_class_ids"
    ] = [
        int(value)
        for value
        in request.POST.get(
            "selected_class_ids",
            "",
        ).split(",")
        if value.strip().isdigit()
    ]

    source_visibility[
        "selected_instructor_ids"
    ] = [
        int(value)
        for value
        in request.POST.get(
            "selected_instructor_ids",
            "",
        ).split(",")
        if value.strip().isdigit()
    ]

    preference.source_visibility = (
        source_visibility
    )
    preference.save()

    return JsonResponse(
        {
            "ok": True,
        }
    )



def _teacher_instructor_for_request(
    request,
    studio,
):
    return (
        Instructor.objects
        .filter(
            studio=studio,
            user=request.user,
            is_active=True,
        )
        .first()
    )


@login_required
@transaction.atomic
def time_off_request_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role != "teacher":
        return _access_denied(
            request,
            studio,
        )

    instructor = (
        _teacher_instructor_for_request(
            request,
            studio,
        )
    )

    if instructor is None:
        messages.error(
            request,
            (
                "Your teacher account is not linked "
                "to an active instructor profile."
            ),
        )

        return redirect(
            "scheduling:calendar",
            studio_slug=studio.slug,
        )

    form = TeacherTimeOffRequestForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        time_off_request = (
            form.save(
                commit=False
            )
        )

        time_off_request.studio = studio
        time_off_request.instructor = (
            instructor
        )
        time_off_request.created_by = (
            request.user
        )

        time_off_request.full_clean()
        time_off_request.save()

        for requested_date in (
            form.cleaned_data[
                "dates"
            ]
        ):
            TeacherTimeOffDate.objects.create(
                request=time_off_request,
                date=requested_date,
            )

        create_time_off_admin_task(
            time_off_request,
            creator=request.user,
        )

        messages.success(
            request,
            (
                "Your time off request was sent "
                "to the studio administrator."
            ),
        )

        return redirect(
            "scheduling:calendar",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "scheduling/time_off_request_form.html",
        {
            "studio": studio,
            "role": role,
            "instructor": instructor,
            "form": form,
        },
    )


@login_required
def time_off_admin_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role != "administrator":
        return _access_denied(
            request,
            studio,
        )

    requests = (
        TeacherTimeOffRequest.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "instructor",
            "created_by",
            "reviewed_by",
        )
        .prefetch_related(
            "dates",
        )
        .order_by(
            "-created_at",
        )
    )

    status_filter = request.GET.get(
        "status",
        "pending",
    )

    if status_filter == "pending":
        requests = requests.filter(
            dates__status__in=[
                TeacherTimeOffDate.Status.PENDING,
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
            ],
        ).distinct()

    elif status_filter in {
        TeacherTimeOffRequest.Status.APPROVED,
        TeacherTimeOffRequest.Status.DENIED,
        TeacherTimeOffRequest.Status.PARTIAL,
    }:
        requests = requests.filter(
            status=status_filter,
        )

    return render(
        request,
        "scheduling/time_off_admin_list.html",
        {
            "studio": studio,
            "role": role,
            "requests": requests,
            "status_filter": status_filter,
        },
    )


@login_required
@transaction.atomic
def time_off_admin_review(
    request,
    studio_slug,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role != "administrator":
        return _access_denied(
            request,
            studio,
        )

    time_off_request = get_object_or_404(
        TeacherTimeOffRequest.objects
        .select_related(
            "instructor",
            "instructor__user",
            "admin_task",
        )
        .prefetch_related(
            "dates",
        ),
        pk=request_id,
        studio=studio,
    )

    form = TimeOffDecisionForm(
        request.POST or None,
        time_off_request=time_off_request,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        decision_note = (
            form.cleaned_data.get(
                "decision_note",
                "",
            )
        )

        for date_record in (
            time_off_request.dates.all()
        ):
            decision = (
                form.cleaned_data[
                    f"date_{date_record.pk}"
                ]
            )

            final_decision = decision

            if (
                decision
                == TeacherTimeOffDate.Status.APPROVED
                and affected_occurrences_for_time_off_date(
                    date_record
                )
            ):
                final_decision = (
                    TeacherTimeOffDate.Status.COVERAGE_REQUIRED
                )

            date_record.status = (
                final_decision
            )
            date_record.decision_note = (
                decision_note
            )
            date_record.reviewed_by = (
                request.user
            )
            date_record.reviewed_at = (
                timezone.now()
            )

            date_record.save(
                update_fields=[
                    "status",
                    "decision_note",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )

            if (
                final_decision
                == TeacherTimeOffDate.Status.DENIED
            ):
                date_record.class_occurrence_overrides.update(
                    status=ClassOccurrenceOverride.Status.CANCELLED,
                )

        time_off_request.reviewed_by = (
            request.user
        )
        time_off_request.reviewed_at = (
            timezone.now()
        )
        time_off_request.save(
            update_fields=[
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        time_off_request.refresh_status()

        coverage_rows = (
            approved_occurrences_needing_coverage(
                time_off_request
            )
        )

        if coverage_rows:
            return redirect(
                "scheduling:time_off_coverage",
                studio_slug=studio.slug,
                request_id=(
                    time_off_request.pk
                ),
            )

        complete_time_off_admin_task(
            time_off_request,
            admin_user=request.user,
        )

        notify_teacher_time_off_decision(
            time_off_request
        )

        messages.success(
            request,
            (
                "The time off request was reviewed."
            ),
        )

        return redirect(
            "scheduling:time_off_admin_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "scheduling/time_off_admin_review.html",
        {
            "studio": studio,
            "role": role,
            "time_off_request": (
                time_off_request
            ),
            "form": form,
        },
    )


@login_required
@transaction.atomic
def time_off_coverage(
    request,
    studio_slug,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = get_user_role_for_studio(
        request.user,
        studio,
    )

    if role != "administrator":
        return _access_denied(
            request,
            studio,
        )

    time_off_request = get_object_or_404(
        TeacherTimeOffRequest.objects
        .select_related(
            "instructor",
            "instructor__user",
            "admin_task",
        )
        .prefetch_related(
            "dates",
        ),
        pk=request_id,
        studio=studio,
    )

    occurrence_rows = (
        approved_occurrences_needing_coverage(
            time_off_request
        )
    )

    for row in occurrence_rows:
        row[
            "substitute_availability"
        ] = (
            substitute_availability_for_occurrence(
                studio=studio,
                absent_instructor=(
                    row[
                        "absent_instructor"
                    ]
                ),
                occurrence_date=(
                    row[
                        "time_off_date"
                    ].date
                ),
                meeting=row[
                    "meeting"
                ],
                existing_override=(
                    row.get(
                        "existing_override"
                    )
                ),
            )
        )

    if not occurrence_rows:
        complete_time_off_admin_task(
            time_off_request,
            admin_user=request.user,
        )

        notify_teacher_time_off_decision(
            time_off_request
        )

        return redirect(
            "scheduling:time_off_admin_list",
            studio_slug=studio.slug,
        )

    form = SubstituteCoverageForm(
        request.POST or None,
        occurrence_rows=occurrence_rows,
        studio=studio,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        for row in occurrence_rows:
            date_record = row[
                "time_off_date"
            ]
            meeting = row[
                "meeting"
            ]
            class_instance = row[
                "class_instance"
            ]
            absent = row[
                "absent_instructor"
            ]

            field_name = (
                f"substitute_"
                f"{date_record.pk}_"
                f"{meeting.pk}"
            )

            substitute = (
                form.cleaned_data[
                    field_name
                ]
            )

            conflicts = (
                substitute_conflicts_for_occurrence(
                    instructor=substitute,
                    studio=studio,
                    occurrence_date=(
                        date_record.date
                    ),
                    meeting=meeting,
                    ignore_override_id=(
                        row[
                            "existing_override"
                        ].pk
                        if row.get(
                            "existing_override"
                        )
                        else None
                    ),
                )
            )

            if conflicts:
                form.add_error(
                    field_name,
                    " ".join(
                        conflicts
                    ),
                )

                continue

            previous_override = (
                ClassOccurrenceOverride.objects
                .filter(
                    studio=studio,
                    class_instance=class_instance,
                    meeting=meeting,
                    occurrence_date=(
                        date_record.date
                    ),
                    absent_instructor=absent,
                )
                .first()
            )

            previous_substitute_id = (
                previous_override.substitute_instructor_id
                if previous_override
                else None
            )

            override, created = (
                ClassOccurrenceOverride.objects
                .update_or_create(
                    studio=studio,
                    class_instance=class_instance,
                    meeting=meeting,
                    occurrence_date=(
                        date_record.date
                    ),
                    absent_instructor=absent,
                    defaults={
                        "substitute_instructor": (
                            substitute
                        ),
                        "time_off_date": (
                            date_record
                        ),
                        "status": (
                            ClassOccurrenceOverride.Status.ACTIVE
                        ),
                        "created_by": (
                            request.user
                        ),
                    },
                )
            )

            override.full_clean()

            if (
                created
                or previous_substitute_id
                != substitute.pk
            ):
                notify_substitute_assignment(
                    override
                )

        if form.errors:
            messages.error(
                request,
                (
                    "One or more substitute assignments "
                    "became unavailable. Review the conflicts below."
                ),
            )

        elif not time_off_has_complete_coverage(
            time_off_request
        ):
            messages.error(
                request,
                (
                    "Every affected class occurrence "
                    "must have substitute coverage."
                ),
            )

        else:
            time_off_request.dates.filter(
                status=TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
            ).update(
                status=TeacherTimeOffDate.Status.APPROVED,
                reviewed_by=request.user,
                reviewed_at=timezone.now(),
            )

            time_off_request.refresh_status()

            complete_time_off_admin_task(
                time_off_request,
                admin_user=request.user,
            )

            notify_teacher_time_off_decision(
                time_off_request
            )

            messages.success(
                request,
                (
                    "Time off approval and substitute "
                    "coverage were finalized."
                ),
            )

            return redirect(
                "scheduling:time_off_admin_list",
                studio_slug=studio.slug,
            )

    display_rows = []

    for row in occurrence_rows:
        field_name = (
            f"substitute_"
            f"{row['time_off_date'].pk}_"
            f"{row['meeting'].pk}"
        )

        display_row = dict(
            row
        )
        display_row[
            "substitute_field"
        ] = form[
            field_name
        ]

        display_row[
            "unavailable_substitutes"
        ] = (
            row[
                "substitute_availability"
            ].get(
                "unavailable",
                [],
            )
        )

        display_row[
            "unavailable_count"
        ] = len(
            display_row[
                "unavailable_substitutes"
            ]
        )

        display_row[
            "available_count"
        ] = (
            row[
                "substitute_availability"
            ].get(
                "available_ids",
                [],
            )
        )

        display_row[
            "available_count"
        ] = len(
            display_row[
                "available_count"
            ]
        )

        display_rows.append(
            display_row
        )

    return render(
        request,
        "scheduling/time_off_coverage.html",
        {
            "studio": studio,
            "role": role,
            "time_off_request": (
                time_off_request
            ),
            "form": form,
            "occurrence_rows": (
                display_rows
            ),
        },
    )
