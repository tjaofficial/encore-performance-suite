from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.list_preferences import list_sort_url, paginate_list, resolve_list_sort
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
            )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    season_id = request.GET.get("season", "current").strip()
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

    # Default to active and upcoming seasons, not historical imports.
    # "all" is an explicit opt-out; numeric values select one season.
    if season_id == "current" or season_id == "":
        season_id = "current"
        enrollments = enrollments.filter(
            class_instance__season__end_date__gte=timezone.localdate()
        )
    elif season_id != "all":
        if season_id.isdigit():
            enrollments = enrollments.filter(
                class_instance__season_id=int(season_id)
            )
        else:
            season_id = "current"
            enrollments = enrollments.filter(
                class_instance__season__end_date__gte=timezone.localdate()
            )

    if class_id:
        enrollments = enrollments.filter(
            class_instance_id=class_id
        )

    if source:
        enrollments = enrollments.filter(
            source=source
        )

    enrollments = enrollments.annotate(
        effective_tuition=Coalesce(
            "tuition_override",
            "class_instance__tuition_amount",
            output_field=DecimalField(
                max_digits=10,
                decimal_places=2,
            ),
        )
    )

    sort_fields = {
        "student": ("student__last_name", "student__first_name", "id"),
        "class": ("class_instance__name", "class_instance__class_id", "id"),
        "season": ("class_instance__season__name", "student__last_name", "student__first_name"),
        "status": ("status", "student__last_name", "student__first_name"),
        "source": ("source", "student__last_name", "student__first_name"),
        "tuition": ("effective_tuition", "student__last_name", "student__first_name"),
    }
    sort_key, sort_direction = resolve_list_sort(
        request, studio, "enrollments", sort_fields.keys(),
        default_sort="student", default_direction="asc",
    )
    order_fields = list(sort_fields[sort_key])
    if sort_direction == "desc":
        order_fields = [f"-{field}" for field in order_fields]
    enrollments = enrollments.order_by(*order_fields)
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
        "enrollments",
        enrollments,
        default_page_size=50,
    )
    enrollments = page_obj.object_list

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
            "sort_columns": sort_columns,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "filters": {
                "q": search,
                "status": status,
                "season": season_id,
                "class": class_id,
                "source": source,
            },
            **pagination_context,
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
