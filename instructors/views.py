from django.contrib import messages
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from classes.models import Class
from studios.models import Studio

from .forms import (
    EncoreInstructorForm,
    InstructorAvailabilityFormSet,
)
from .models import Instructor


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


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

    requested_view = request.GET.get(
        "view",
        "",
    ).strip()

    if requested_view in {
        "cards",
        "table",
    }:
        view_mode = requested_view
        request.session[
            "encore_instructor_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_instructor_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

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
        .order_by("last_name", "first_name")
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

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
            "card_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "cards",
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
                    }
                )
            ),
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

    if request.method == "POST":
        form = EncoreInstructorForm(
            request.POST,
            instance=instructor,
        )

        formset = InstructorAvailabilityFormSet(
            request.POST,
            instance=instructor,
        )

        if form.is_valid() and formset.is_valid():
            instructor = form.save(commit=False)
            instructor.studio = studio
            instructor.full_clean()
            instructor.save()

            formset.instance = instructor
            availability_rows = formset.save(
                commit=False
            )

            for deleted in formset.deleted_objects:
                deleted.delete()

            for availability in availability_rows:
                availability.instructor = instructor
                availability.full_clean()
                availability.save()

            messages.success(
                request,
                f"{instructor.full_name} was created.",
            )

            return redirect(
                "instructors:instructor_detail",
                studio_slug=studio.slug,
                instructor_id=instructor.pk,
            )
    else:
        form = EncoreInstructorForm(
            instance=instructor,
        )

        formset = InstructorAvailabilityFormSet(
            instance=instructor,
        )

    return render(
        request,
        "instructors/instructor_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "instructor": None,
            "page_title": "Add Instructor",
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

    if request.method == "POST":
        form = EncoreInstructorForm(
            request.POST,
            instance=instructor,
        )

        formset = InstructorAvailabilityFormSet(
            request.POST,
            instance=instructor,
        )

        if form.is_valid() and formset.is_valid():
            instructor = form.save(commit=False)
            instructor.full_clean()
            instructor.save()

            availability_rows = formset.save(
                commit=False
            )

            for deleted in formset.deleted_objects:
                deleted.delete()

            for availability in availability_rows:
                availability.instructor = instructor
                availability.full_clean()
                availability.save()

            messages.success(
                request,
                f"{instructor.full_name} was updated.",
            )

            return redirect(
                "instructors:instructor_detail",
                studio_slug=studio.slug,
                instructor_id=instructor.pk,
            )
    else:
        form = EncoreInstructorForm(
            instance=instructor,
        )

        formset = InstructorAvailabilityFormSet(
            instance=instructor,
        )

    return render(
        request,
        "instructors/instructor_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "instructor": instructor,
            "page_title": "Edit Instructor",
        },
    )
