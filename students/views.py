import json

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.list_preferences import list_sort_url, paginate_list, resolve_list_sort
from attendance.models import AttendanceRecord
from enrollments.models import Enrollment
from studios.models import Studio
from tasks.services import visible_tasks_for_user

from .forms import EncoreStudentForm, ParentStudentProfileForm
from families.models import Guardian
from dashboard.parent_portal import parent_portal_context
from .models import Student, StaffStudentNote


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


def _student_attendance_percentage(student):
    records = AttendanceRecord.objects.filter(
        student=student,
    )

    total = records.count()

    if not total:
        return None

    attended = records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()

    return round((attended / total) * 100)


@login_required
def student_list(request, studio_slug):
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

    students = (
        Student.objects
        .filter(studio=studio)
        .select_related("family")
        .annotate(
            active_class_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
            )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    family_status = request.GET.get(
        "family_status",
        "",
    ).strip()

    if search:
        students = students.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(family__family_name__icontains=search)
        )

    if status == "active":
        students = students.filter(is_active=True)
    elif status == "inactive":
        students = students.filter(is_active=False)
    elif status == "blocked":
        students = students.filter(
            enrollment_blocked=True
        )

    if family_status == "attached":
        students = students.filter(
            family__isnull=False
        )
    elif family_status == "standalone":
        students = students.filter(
            family__isnull=True
        )

    sort_fields = {
        "student": ("last_name", "first_name", "id"),
        "age": ("birthday", "last_name", "first_name"),
        "family": ("family__family_name", "last_name", "first_name"),
        "classes": ("active_class_count", "last_name", "first_name"),
        "status": ("is_active", "enrollment_blocked", "last_name", "first_name"),
    }
    sort_key, sort_direction = resolve_list_sort(
        request, studio, "students", sort_fields.keys(),
        default_sort="student", default_direction="asc",
    )
    if sort_key == "age":
        # Younger students have later birthdays.
        if sort_direction == "asc":
            students = students.order_by(
                "-birthday",
                "last_name",
                "first_name",
            )
        else:
            students = students.order_by(
                "birthday",
                "last_name",
                "first_name",
            )
    else:
        order_fields = list(sort_fields[sort_key])
        if sort_direction == "desc":
            order_fields = [
                f"-{field}"
                for field in order_fields
            ]
        students = students.order_by(*order_fields)
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
        "students",
        students,
        default_page_size=50,
    )
    students = page_obj.object_list

    return render(
        request,
        "students/student_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "students": students,
            "sort_columns": sort_columns,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "filters": {
                "q": search,
                "status": status,
                "family_status": family_status,
            },
            **pagination_context,
        },
    )


@login_required
def student_detail(request, studio_slug, student_id):
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

    student = get_object_or_404(
        Student.objects.select_related(
            "family",
            "user",
        ),
        pk=student_id,
        studio=studio,
    )

    # Separate completed seasons from ongoing/upcoming seasons, regardless of
    # whether a particular enrollment has been marked active or completed.
    today = timezone.localdate()
    enrollments = list(
        Enrollment.objects.filter(student=student)
        .select_related("class_instance", "class_instance__season", "class_instance__instructor")
        .order_by("-class_instance__season__start_date", "class_instance__name", "pk")
    )
    current_enrollments = []
    past_enrollments = []
    for enrollment in enrollments:
        season = enrollment.class_instance.season
        if season and season.end_date and season.end_date < today:
            past_enrollments.append(enrollment)
        else:
            current_enrollments.append(enrollment)

    recent_attendance = (
        AttendanceRecord.objects
        .filter(student=student)
        .select_related(
            "session",
            "session__class_instance",
        )
        .order_by(
            "-session__session_date"
        )[:10]
    )

    student_tasks = (
        visible_tasks_for_user(
            request.user,
            studio,
            "administrator",
        )
        .filter(
            student=student,
        )
        .exclude(
            completions__user=request.user,
        )
        .distinct()[:10]
    )

    profile_note = StaffStudentNote.objects.filter(studio=studio, student=student, class_instance__isnull=True).first()

    return render(
        request,
        "students/student_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "student": student,
            "profile_note": profile_note,
            "profile_note_version": profile_note.updated_at.isoformat() if profile_note else "",
            "enrollments": enrollments,
            "current_enrollments": current_enrollments,
            "past_enrollments": past_enrollments,
            "recent_attendance": recent_attendance,
            "attendance_percentage": (
                _student_attendance_percentage(student)
            ),
            "student_tasks": student_tasks,
        },
    )


@login_required
@require_POST
def student_profile_staff_notes_save(request, studio_slug, student_id):
    """Save the same private student-wide note shown on Class Student Detail."""
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return JsonResponse({"error": "Administrator access required"}, status=403)
    student = get_object_or_404(Student, pk=student_id, studio=studio)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    content = payload.get("text")
    if not isinstance(content, str) or len(content) > 10000:
        return JsonResponse({"error": "Notes must be text under 10,000 characters"}, status=400)
    with transaction.atomic():
        note, created = StaffStudentNote.objects.select_for_update().get_or_create(
            studio=studio, student=student, class_instance=None,
            defaults={"updated_by": request.user},
        )
        expected = payload.get("version", "")
        if not created and expected != note.updated_at.isoformat():
            return JsonResponse({"error": "This note changed in another session. Refresh to see the latest version."}, status=409)
        note.text = content
        note.updated_by = request.user
        note.save(update_fields=["text", "updated_by", "updated_at"])
    return JsonResponse({"saved": True, "version": note.updated_at.isoformat()})


@login_required
def student_create(request, studio_slug):
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

    student = Student(studio=studio)

    if request.method == "POST":
        form = EncoreStudentForm(
            request.POST,
            instance=student,
            studio=studio,
        )

        if form.is_valid():
            student = form.save(commit=False)
            student.studio = studio
            student.full_clean()
            student.save()
            form.save_m2m()

            messages.success(
                request,
                (
                    f"{student.first_name} "
                    f"{student.last_name} was created."
                ),
            )

            return redirect(
                "students:student_detail",
                studio_slug=studio.slug,
                student_id=student.pk,
            )
    else:
        form = EncoreStudentForm(
            instance=student,
            studio=studio,
        )

    return render(
        request,
        "students/student_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "student": None,
            "page_title": "Add Student",
        },
    )


@login_required
def student_edit(
    request,
    studio_slug,
    student_id,
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

    student = get_object_or_404(
        Student,
        pk=student_id,
        studio=studio,
    )

    if request.method == "POST":
        form = EncoreStudentForm(
            request.POST,
            instance=student,
            studio=studio,
        )

        if form.is_valid():
            student = form.save(commit=False)
            student.full_clean()
            student.save()
            form.save_m2m()

            messages.success(
                request,
                (
                    f"{student.first_name} "
                    f"{student.last_name} was updated."
                ),
            )

            return redirect(
                "students:student_detail",
                studio_slug=studio.slug,
                student_id=student.pk,
            )
    else:
        form = EncoreStudentForm(
            instance=student,
            studio=studio,
        )

    return render(
        request,
        "students/student_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "student": student,
            "page_title": "Edit Student",
        },
    )


def _family_guardian_for_student(request, studio):
    return (
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


@login_required
def family_student_detail(
    request,
    studio_slug,
    student_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _family_guardian_for_student(
        request,
        studio,
    )

    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    student = get_object_or_404(
        Student.objects.select_related(
            "family",
            "user",
        ),
        pk=student_id,
        studio=studio,
        family=guardian.family,
    )

    enrollments = (
        Enrollment.objects
        .filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        )
        .select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
            "class_instance__level",
        )
        .order_by("class_instance__name")
    )

    recent_attendance = (
        AttendanceRecord.objects
        .filter(student=student)
        .select_related(
            "session",
            "session__class_instance",
        )
        .order_by("-session__session_date")[:8]
    )

    latest_measurements = (
        student.measurement_sets
        .filter(is_complete=True)
        .order_by("-measured_at", "-updated_at")
        .first()
    )

    context = {
        "studio": studio,
        "role": "family",
        "student": student,
        "enrollments": enrollments,
        "recent_attendance": recent_attendance,
        "attendance_percentage": (
            _student_attendance_percentage(student)
        ),
        "latest_measurements": latest_measurements,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            selected_student=student,
            section="dashboard",
        )
    )

    return render(
        request,
        "students/parent_student_detail.html",
        context,
    )


@login_required
def family_student_edit(
    request,
    studio_slug,
    student_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _family_guardian_for_student(
        request,
        studio,
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
    )

    form = ParentStudentProfileForm(
        request.POST or None,
        instance=student,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            f"{student.first_name}'s profile was updated.",
        )
        return redirect(
            "students:family_student_detail",
            studio_slug=studio.slug,
            student_id=student.pk,
        )

    context = {
        "studio": studio,
        "role": "family",
        "student": student,
        "form": form,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            selected_student=student,
            section="dashboard",
        )
    )

    return render(
        request,
        "students/parent_student_form.html",
        context,
    )
