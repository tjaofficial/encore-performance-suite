from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from attendance.models import AttendanceRecord
from enrollments.models import Enrollment
from studios.models import Studio
from tasks.services import visible_tasks_for_user

from .forms import EncoreStudentForm
from .models import Student


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
        .order_by("last_name", "first_name")
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

    return render(
        request,
        "students/student_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "students": students,
            "filters": {
                "q": search,
                "status": status,
                "family_status": family_status,
            },
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

    enrollments = (
        Enrollment.objects
        .filter(student=student)
        .select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
        )
        .order_by(
            "class_instance__name",
        )
    )

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

    return render(
        request,
        "students/student_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "student": student,
            "enrollments": enrollments,
            "recent_attendance": recent_attendance,
            "attendance_percentage": (
                _student_attendance_percentage(student)
            ),
            "student_tasks": student_tasks,
        },
    )


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
