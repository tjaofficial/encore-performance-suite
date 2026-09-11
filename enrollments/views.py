from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from classes.models import Class, Season
from students.models import Student
from studios.models import Studio

from .forms import EncoreEnrollmentForm
from .models import Enrollment


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


@login_required
def enrollment_list(request, studio_slug):
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

    enrollments = (
        Enrollment.objects
        .filter(
            class_instance__studio=studio,
            student__studio=studio,
        )
        .select_related(
            "student",
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
        )
        .order_by(
            "-created_at",
        )
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    season_id = request.GET.get("season", "").strip()
    class_id = request.GET.get("class", "").strip()
    source = request.GET.get("source", "").strip()

    if search:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(class_instance__class_id__icontains=search)
            | Q(class_instance__name__icontains=search)
        )

    if status:
        enrollments = enrollments.filter(
            status=status
        )

    if season_id:
        enrollments = enrollments.filter(
            class_instance__season_id=season_id
        )

    if class_id:
        enrollments = enrollments.filter(
            class_instance_id=class_id
        )

    if source:
        enrollments = enrollments.filter(
            source=source
        )

    seasons = Season.objects.filter(
        studio=studio,
    ).order_by("-start_date", "name")

    classes = Class.objects.filter(
        studio=studio,
    ).order_by("name")

    return render(
        request,
        "enrollments/enrollment_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "enrollments": enrollments,
            "seasons": seasons,
            "classes": classes,
            "status_choices": Enrollment.Status.choices,
            "source_choices": Enrollment.Source.choices,
            "filters": {
                "q": search,
                "status": status,
                "season": season_id,
                "class": class_id,
                "source": source,
            },
        },
    )


@login_required
def enrollment_detail(
    request,
    studio_slug,
    enrollment_id,
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

    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student",
            "student__family",
            "class_instance",
            "class_instance__season",
            "class_instance__class_type",
            "class_instance__instructor",
        ),
        pk=enrollment_id,
        class_instance__studio=studio,
        student__studio=studio,
    )

    return render(
        request,
        "enrollments/enrollment_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "enrollment": enrollment,
        },
    )


@login_required
def enrollment_create(request, studio_slug):
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

    initial = {}

    student_id = request.GET.get("student")
    class_id = request.GET.get("class")

    if student_id:
        initial["student"] = student_id

    if class_id:
        initial["class_instance"] = class_id

    if request.method == "POST":
        form = EncoreEnrollmentForm(
            request.POST,
            studio=studio,
        )

        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.full_clean()
            enrollment.save()

            messages.success(
                request,
                "Enrollment was created.",
            )

            return redirect(
                "enrollments:enrollment_detail",
                studio_slug=studio.slug,
                enrollment_id=enrollment.pk,
            )
    else:
        form = EncoreEnrollmentForm(
            studio=studio,
            initial=initial,
        )

    return render(
        request,
        "enrollments/enrollment_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "enrollment": None,
            "page_title": "Add Enrollment",
        },
    )


@login_required
def enrollment_edit(
    request,
    studio_slug,
    enrollment_id,
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

    enrollment = get_object_or_404(
        Enrollment,
        pk=enrollment_id,
        class_instance__studio=studio,
        student__studio=studio,
    )

    if request.method == "POST":
        form = EncoreEnrollmentForm(
            request.POST,
            instance=enrollment,
            studio=studio,
        )

        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.full_clean()
            enrollment.save()

            messages.success(
                request,
                "Enrollment was updated.",
            )

            return redirect(
                "enrollments:enrollment_detail",
                studio_slug=studio.slug,
                enrollment_id=enrollment.pk,
            )
    else:
        form = EncoreEnrollmentForm(
            instance=enrollment,
            studio=studio,
        )

    return render(
        request,
        "enrollments/enrollment_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "enrollment": enrollment,
            "page_title": "Edit Enrollment",
        },
    )
