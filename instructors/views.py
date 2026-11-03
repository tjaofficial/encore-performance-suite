import json
import uuid
from datetime import datetime

from django.contrib import messages
from urllib.parse import urlencode
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.list_preferences import list_sort_url, paginate_list, resolve_list_sort, resolve_list_view_mode
from classes.models import Class
from scheduling.calendar_services import (
    affected_occurrences_for_time_off_date,
    approved_occurrences_needing_coverage,
    complete_time_off_admin_task,
    notify_teacher_time_off_decision,
)
from scheduling.models import (
    ClassOccurrenceOverride,
    TeacherTimeOffDate,
    TeacherTimeOffRequest,
)
from studios.models import Studio, StudioMembership

from .forms import (
    EncoreInstructorForm,
    InstructorClaimProfileForm,
)
from .models import Instructor, InstructorAvailability
from .activation_services import InstructorActivationError, send_instructor_activation


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


def _availability_blocks(instructor):
    grouped = {}

    for row in instructor.availability.order_by(
        "is_available",
        "start_time",
        "end_time",
        "notes",
        "day_of_week",
    ):
        key = (
            row.is_available,
            row.start_time.strftime("%H:%M"),
            row.end_time.strftime("%H:%M"),
            row.notes or "",
        )
        grouped.setdefault(
            key,
            {
                "status": (
                    "available"
                    if row.is_available
                    else "unavailable"
                ),
                "start": key[1],
                "end": key[2],
                "notes": key[3],
                "days": [],
            },
        )["days"].append(row.day_of_week)

    return list(grouped.values())


def _parse_availability_blocks(raw):
    try:
        payload = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Availability could not be read.")

    if not isinstance(payload, list):
        raise ValueError("Availability must be a list.")

    normalized = []

    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue

        days = sorted(
            {
                int(day)
                for day in item.get("days", [])
                if str(day).isdigit()
                and 0 <= int(day) <= 6
            }
        )

        start = str(item.get("start") or "").strip()
        end = str(item.get("end") or "").strip()
        notes = str(item.get("notes") or "").strip()[:255]
        status = str(
            item.get("status") or "available"
        ).strip().lower()

        if not days:
            raise ValueError(
                f"Availability {index} needs at least one day."
            )

        if not start or not end:
            raise ValueError(
                f"Availability {index} needs a start and end time."
            )

        try:
            start_time = datetime.strptime(
                start,
                "%H:%M",
            ).time()
            end_time = datetime.strptime(
                end,
                "%H:%M",
            ).time()
        except ValueError as exc:
            raise ValueError(
                f"Availability {index} has an invalid time."
            ) from exc

        if end_time <= start_time:
            raise ValueError(
                f"Availability {index} must end after it starts."
            )

        if status not in {
            "available",
            "unavailable",
        }:
            raise ValueError(
                f"Availability {index} has an invalid status."
            )

        normalized.append(
            {
                "days": days,
                "start_time": start_time,
                "end_time": end_time,
                "is_available": status == "available",
                "notes": notes,
            }
        )

    return normalized


def _save_availability_blocks(instructor, blocks):
    desired = set()

    for block in blocks:
        for day in block["days"]:
            desired.add(
                (
                    day,
                    block["start_time"],
                    block["end_time"],
                    block["is_available"],
                    block["notes"],
                )
            )

    instructor.availability.all().delete()

    InstructorAvailability.objects.bulk_create(
        [
            InstructorAvailability(
                instructor=instructor,
                day_of_week=day,
                start_time=start_time,
                end_time=end_time,
                is_available=is_available,
                notes=notes,
            )
            for (
                day,
                start_time,
                end_time,
                is_available,
                notes,
            ) in sorted(
                desired,
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2],
                ),
            )
        ]
    )


def _activation_instructor(token):
    instructor = (
        Instructor.objects
        .select_related("studio", "user")
        .filter(
            activation_token=token,
            is_active=True,
        )
        .first()
    )

    if instructor is None:
        return None

    if (
        instructor.activation_expires_at
        and instructor.activation_expires_at < timezone.now()
        and not instructor.claimed_at
    ):
        return None

    return instructor


def _unique_username(email):
    User = get_user_model()
    base = (
        str(email or "teacher")
        .split("@", 1)[0]
        .strip()
        .lower()
    )
    base = "".join(
        character
        for character in base
        if character.isalnum()
        or character in {"_", "-", "."}
    )[:120] or "teacher"

    candidate = base
    suffix = 1

    while User.objects.filter(
        username=candidate
    ).exists():
        suffix += 1
        candidate = f"{base[:110]}-{suffix}"

    return candidate


@login_required
def instructor_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    # A bulk action uses the same administrator-protected list endpoint.
    # Only IDs from this studio can be changed; never trust client-submitted counts.
    if request.method == "POST" and request.POST.get("bulk_action") == "update":
        destination = request.POST.get("next") or ""
        from django.urls import reverse
        from django.utils.http import url_has_allowed_host_and_scheme
        safe_destination = reverse("instructors:instructor_list", kwargs={"studio_slug": studio.slug})
        if destination and url_has_allowed_host_and_scheme(
            destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            safe_destination = destination
        try:
            submitted = json.loads(request.POST.get("selected_ids_json", "[]"))
            if not isinstance(submitted, list) or not submitted or len(submitted) > 500:
                raise ValueError
            ids = {int(item) for item in submitted if str(item).isdigit() and int(item) > 0}
            if len(ids) != len(submitted):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            messages.error(request, "Select one or more valid instructors.")
            return redirect(safe_destination)

        field = request.POST.get("field", "")
        value = request.POST.get("value", "")
        if field == "is_active" and value in ("true", "false"):
            new_value = value == "true"
        elif field == "phone" and len(value) <= 30:
            new_value = value.strip()
        else:
            messages.error(request, "Choose a valid field and value.")
            return redirect(safe_destination)

        with transaction.atomic():
            records = list(Instructor.objects.select_for_update().filter(studio=studio, pk__in=ids))
            if len(records) != len(ids):
                messages.error(request, "Some selected instructors were not found in this studio; nothing was changed.")
                return redirect(safe_destination)
            for instructor in records:
                setattr(instructor, field, new_value)
                instructor.full_clean()
            for instructor in records:
                instructor.save(update_fields=[field])
        messages.success(request, f"Updated {len(records)} instructor records ({'status' if field == 'is_active' else 'phone'}).")
        return redirect(safe_destination)

    view_mode = resolve_list_view_mode(
        request,
        studio,
        "instructors",
        default="table",
    )

    instructors = (
        Instructor.objects
        .filter(studio=studio)
        .annotate(
            primary_class_count=Count(
                "primary_classes",
                filter=Q(
                    primary_classes__is_active=True,
                ),
                distinct=True,
            ),
            assistant_class_count=Count(
                "assistant_classes",
                filter=Q(
                    assistant_classes__is_active=True,
                ),
                distinct=True,
            ),
        )
            )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active").strip().lower()
    if status not in {"active", "inactive", "all"}:
        status = "active"

    if search:
        instructors = instructors.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    if status == "active":
        instructors = instructors.filter(is_active=True)
    elif status == "inactive":
        instructors = instructors.filter(is_active=False)

    sort_fields = {
        "instructor": ("last_name", "first_name", "id"),
        "email": ("email", "last_name", "first_name"),
        "primary_classes": ("primary_class_count", "last_name", "first_name"),
        "assistant_classes": ("assistant_class_count", "last_name", "first_name"),
        "phone": ("phone", "last_name", "first_name"),
        "status": ("is_active", "claimed_at", "activation_sent_at", "last_name", "first_name"),
    }
    sort_key, sort_direction = resolve_list_sort(
        request, studio, "instructors", sort_fields.keys(),
        default_sort="instructor", default_direction="asc",
    )
    order_fields = list(sort_fields[sort_key])
    if sort_direction == "desc":
        order_fields = [f"-{field}" for field in order_fields]
    instructors = instructors.order_by(*order_fields)
    sort_columns = {
        key: {
            "url": list_sort_url(request, key, sort_key, sort_direction),
            "active": sort_key == key,
            "direction": sort_direction if sort_key == key else "",
        }
        for key in sort_fields
    }

    page_obj, pagination_context = paginate_list(
        request,
        studio,
        "instructors",
        instructors,
        default_page_size=50,
    )
    instructors = page_obj.object_list

    return render(
        request,
        "instructors/instructor_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "instructors": instructors,
            "filters": {
                "q": search,
                "status": status,
            },
            "view_mode": view_mode,
            "sort_columns": sort_columns,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "card_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "cards",
                        "page_size": pagination_context[
                            "page_size"
                        ],
                    }
                )
            ),
            "table_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "table",
                        "page_size": pagination_context[
                            "page_size"
                        ],
                    }
                )
            ),
            **pagination_context,
        },
    )


@login_required
def instructor_detail(
    request,
    studio_slug,
    instructor_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = get_object_or_404(
        Instructor.objects.select_related("user"),
        pk=instructor_id,
        studio=studio,
    )

    primary_classes = (
        Class.objects
        .filter(
            studio=studio,
            instructor=instructor,
            is_active=True,
        )
        .select_related(
            "season",
            "class_type",
        )
        .order_by("name")
    )

    assisting_classes = (
        Class.objects
        .filter(
            studio=studio,
            assistant_instructor=instructor,
            is_active=True,
        )
        .select_related(
            "season",
            "class_type",
        )
        .order_by("name")
    )

    availability = instructor.availability.order_by(
        "day_of_week",
        "start_time",
    )

    recent_time_off_requests = list(
        instructor.time_off_requests
        .prefetch_related("dates")
        .order_by("-created_at")[:6]
    )
    pending_time_off_count = (
        instructor.time_off_requests
        .filter(
            dates__status__in=[
                TeacherTimeOffDate.Status.PENDING,
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
            ]
        )
        .distinct()
        .count()
    )

    return render(
        request,
        "instructors/instructor_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "instructor": instructor,
            "primary_classes": primary_classes,
            "assisting_classes": assisting_classes,
            "availability": availability,
            "recent_time_off_requests": recent_time_off_requests,
            "pending_time_off_count": pending_time_off_count,
        },
    )


@login_required
@transaction.atomic
def instructor_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = Instructor(studio=studio)
    form = EncoreInstructorForm(
        request.POST or None,
        instance=instructor,
    )
    availability_blocks = []

    if request.method == "POST":
        try:
            availability_blocks = _parse_availability_blocks(
                request.POST.get("availability_json", "[]")
            )
        except ValueError as exc:
            form.add_error(None, str(exc))

        if form.is_valid():
            instructor = form.save(commit=False)
            instructor.studio = studio
            instructor.full_clean()
            instructor.save()
            _save_availability_blocks(
                instructor,
                availability_blocks,
            )

            if instructor.email:
                try:
                    send_instructor_activation(
                        request=request,
                        instructor=instructor,
                    )
                except InstructorActivationError as exc:
                    messages.warning(
                        request,
                        f"Instructor created, but the activation email could not be sent: {exc}",
                    )
                else:
                    messages.success(
                        request,
                        "Instructor created and activation email sent.",
                    )
            else:
                messages.success(
                    request,
                    "Instructor created. Add an email address before sending account activation.",
                )

            return redirect(
                "instructors:instructor_detail",
                studio_slug=studio.slug,
                instructor_id=instructor.pk,
            )

    return render(
        request,
        "instructors/instructor_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Add Instructor",
            "availability_blocks": availability_blocks,
            "availability_day_choices": InstructorAvailability.DayOfWeek.choices,
        },
    )


@login_required
@transaction.atomic
def instructor_edit(
    request,
    studio_slug,
    instructor_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = get_object_or_404(
        Instructor,
        pk=instructor_id,
        studio=studio,
    )

    form = EncoreInstructorForm(
        request.POST or None,
        instance=instructor,
    )
    availability_blocks = (
        _availability_blocks(instructor)
        if request.method != "POST"
        else []
    )

    if request.method == "POST":
        try:
            availability_blocks = _parse_availability_blocks(
                request.POST.get("availability_json", "[]")
            )
        except ValueError as exc:
            form.add_error(None, str(exc))

        if form.is_valid():
            instructor = form.save(commit=False)
            instructor.full_clean()
            instructor.save()
            _save_availability_blocks(
                instructor,
                availability_blocks,
            )
            messages.success(
                request,
                "Instructor updated.",
            )
            return redirect(
                "instructors:instructor_detail",
                studio_slug=studio.slug,
                instructor_id=instructor.pk,
            )

    return render(
        request,
        "instructors/instructor_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Edit Instructor",
            "instructor": instructor,
            "availability_blocks": availability_blocks,
            "availability_day_choices": InstructorAvailability.DayOfWeek.choices,
        },
    )


def instructor_claim_profile(
    request,
    activation_token,
):
    instructor = _activation_instructor(
        activation_token
    )

    if instructor is None:
        return render(
            request,
            "instructors/instructor_claim_invalid.html",
            status=404,
        )

    if (
        instructor.claimed_at
        and instructor.user_id
    ):
        if request.user.is_authenticated:
            return redirect(
                "dashboard:teacher_dashboard",
                studio_slug=instructor.studio.slug,
            )

        return redirect(
            f"/accounts/login/?next=/dashboard/{instructor.studio.slug}/teacher/"
        )

    User = get_user_model()
    existing_user = (
        User.objects
        .filter(
            email__iexact=instructor.email,
        )
        .first()
    )

    form = InstructorClaimProfileForm(
        request.POST or None,
        instance=instructor,
        existing_user=existing_user,
    )

    if request.method == "POST" and form.is_valid():
        instructor = form.save(commit=False)
        instructor.profile_verified_at = timezone.now()
        instructor.is_active = True

        if existing_user is None:
            user = User.objects.create_user(
                username=_unique_username(
                    instructor.email
                ),
                email=instructor.email,
                first_name=instructor.first_name,
                last_name=instructor.last_name,
                password=form.cleaned_data[
                    "password1"
                ],
            )
        else:
            user = existing_user
            changed = []

            if not user.first_name:
                user.first_name = instructor.first_name
                changed.append("first_name")
            if not user.last_name:
                user.last_name = instructor.last_name
                changed.append("last_name")
            if changed:
                user.save(update_fields=changed)

        instructor.user = user
        instructor.claimed_at = timezone.now()
        instructor.full_clean()
        instructor.save()

        membership, _created = (
            StudioMembership.objects
            .get_or_create(
                studio=instructor.studio,
                user=user,
                role=StudioMembership.Role.TEACHER,
                defaults={"is_active": True},
            )
        )
        if not membership.is_active:
            membership.is_active = True
            membership.save(
                update_fields=["is_active"]
            )

        login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        request.session[
            "encore_workspace_membership_id"
        ] = membership.pk
        request.session[
            "encore_workspace_studio_slug"
        ] = instructor.studio.slug
        request.session[
            "encore_workspace_role"
        ] = "teacher"

        return redirect(
            "instructors:instructor_claim_availability",
            activation_token=instructor.activation_token,
        )

    return render(
        request,
        "instructors/instructor_claim_profile.html",
        {
            "studio": instructor.studio,
            "instructor": instructor,
            "form": form,
            "existing_user": existing_user,
        },
    )


def instructor_claim_availability(
    request,
    activation_token,
):
    instructor = _activation_instructor(
        activation_token
    )

    if (
        instructor is None
        or not instructor.claimed_at
        or not instructor.user_id
    ):
        return redirect(
            "instructors:instructor_claim_profile",
            activation_token=activation_token,
        )

    if (
        not request.user.is_authenticated
        or request.user.pk != instructor.user_id
    ):
        return redirect(
            f"/accounts/login/?next={request.path}"
        )

    availability_blocks = _availability_blocks(
        instructor
    )

    if request.method == "POST":
        try:
            availability_blocks = _parse_availability_blocks(
                request.POST.get(
                    "availability_json",
                    "[]",
                )
            )
        except ValueError as exc:
            messages.error(
                request,
                str(exc),
            )
        else:
            with transaction.atomic():
                _save_availability_blocks(
                    instructor,
                    availability_blocks,
                )
                instructor.availability_completed_at = (
                    timezone.now()
                )
                instructor.save(
                    update_fields=[
                        "availability_completed_at",
                        "updated_at",
                    ]
                )

            messages.success(
                request,
                "Your Encore instructor profile is ready.",
            )
            return redirect(
                "dashboard:teacher_dashboard",
                studio_slug=instructor.studio.slug,
            )

    return render(
        request,
        "instructors/instructor_claim_availability.html",
        {
            "studio": instructor.studio,
            "instructor": instructor,
            "availability_blocks": availability_blocks,
            "availability_day_choices": InstructorAvailability.DayOfWeek.choices,
        },
    )


@login_required
@transaction.atomic
def instructor_time_off_decision(
    request,
    studio_slug,
    instructor_id,
    request_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "instructors:instructor_detail",
            studio_slug=studio.slug,
            instructor_id=instructor_id,
        )

    time_off_request = get_object_or_404(
        TeacherTimeOffRequest.objects
        .select_related("instructor")
        .prefetch_related("dates"),
        pk=request_id,
        studio=studio,
        instructor_id=instructor_id,
    )

    action = str(
        request.POST.get("action") or ""
    ).strip().lower()
    note = str(
        request.POST.get("decision_note") or ""
    ).strip()

    if action not in {"approve", "deny"}:
        messages.error(
            request,
            "Choose Approve or Deny.",
        )
        return redirect(
            "instructors:instructor_detail",
            studio_slug=studio.slug,
            instructor_id=instructor_id,
        )

    for date_record in time_off_request.dates.all():
        if action == "approve":
            final_status = (
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED
                if affected_occurrences_for_time_off_date(
                    date_record
                )
                else TeacherTimeOffDate.Status.APPROVED
            )
        else:
            final_status = (
                TeacherTimeOffDate.Status.DENIED
            )

        date_record.status = final_status
        date_record.decision_note = note
        date_record.reviewed_by = request.user
        date_record.reviewed_at = timezone.now()
        date_record.save(
            update_fields=[
                "status",
                "decision_note",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        if action == "deny":
            date_record.class_occurrence_overrides.update(
                status=ClassOccurrenceOverride.Status.CANCELLED,
            )

    time_off_request.reviewed_by = request.user
    time_off_request.reviewed_at = timezone.now()
    time_off_request.save(
        update_fields=[
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    time_off_request.refresh_status()

    if action == "approve":
        coverage_rows = (
            approved_occurrences_needing_coverage(
                time_off_request
            )
        )
        if coverage_rows:
            messages.info(
                request,
                "Time off approved. Assign substitute coverage for the affected classes.",
            )
            return redirect(
                "scheduling:time_off_coverage",
                studio_slug=studio.slug,
                request_id=time_off_request.pk,
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
            "Time off request approved."
            if action == "approve"
            else "Time off request denied."
        ),
    )

    return redirect(
        "instructors:instructor_detail",
        studio_slug=studio.slug,
        instructor_id=instructor_id,
    )
