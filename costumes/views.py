from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone

from classes.models import Class
from performance.models import ChoreographyPlan
from students.models import Student
from studios.models import (
    Studio,
    StudioMembership,
)

from .forms import (
    CostumeForm,
    CostumeLinkFormSet,
)
from .models import (
    Costume,
    CostumeImage,
    StudentCostumeAssignment,
    StudentMeasurementSet,
)
from .services import (
    can_manage_class,
    create_costume_announcement,
    create_costume_student_task,
    current_completed_measurement,
    current_draft_measurement,
    family_student_ids,
    get_or_create_measurement_draft,
    measurement_state,
    start_new_measurement_set,
    sync_costume_assignments,
    workspace_role,
)


MEASUREMENT_FIELDS = {
    "bust": "decimal",
    "waist": "decimal",
    "hips": "decimal",
    "girth": "decimal",
    "inseam": "decimal",
    "outseam": "decimal",
    "height": "decimal",
    "clothing_size": "text",
    "shoe_size": "text",
    "other_size_info": "text",
    "notes": "text",
}


def _access_denied(
    request,
    studio,
):
    return render(
        request,
        "dashboard/access_denied.html",
        {
            "studio": studio,
        },
        status=403,
    )


def _class_for_staff(
    request,
    studio,
    class_id,
):
    class_instance = get_object_or_404(
        Class.objects.select_related(
            "instructor",
            "instructor__user",
            "assistant_instructor",
            "assistant_instructor__user",
        ),
        pk=class_id,
        studio=studio,
    )

    if not can_manage_class(
        request,
        studio,
        class_instance,
    ):
        return None

    return class_instance


@login_required
def measurement_roster(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return _access_denied(
            request,
            studio,
        )

    active_students = (
        Student.objects
        .filter(
            studio=studio,
            is_active=True,
            enrollments__class_instance=class_instance,
            enrollments__status="active",
        )
        .distinct()
        .order_by(
            "last_name",
            "first_name",
        )
    )

    rows = []

    for student in active_students:
        draft = current_draft_measurement(
            student
        )

        current = current_completed_measurement(
            student
        )

        state = measurement_state(
            student
        )

        edit_set = (
            draft
            if draft is not None
            else current
        )

        rows.append(
            {
                "student": student,
                "draft": draft,
                "current": current,
                "edit_set": edit_set,
                "state": state,
            }
        )

    counts = {
        "total": len(rows),
        "complete": sum(
            row["state"] == "complete"
            for row in rows
        ),
        "in_progress": sum(
            row["state"] == "in_progress"
            for row in rows
        ),
        "not_started": sum(
            row["state"] == "not_started"
            for row in rows
        ),
        "needs_remeasurement": sum(
            row["state"]
            == "needs_remeasurement"
            for row in rows
        ),
    }

    return render(
        request,
        "costumes/measurement_roster.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "role": workspace_role(
                request,
                studio,
            ),
            "measurement_rows": rows,
            "counts": counts,
            "measurement_fields": (
                MEASUREMENT_FIELDS.keys()
            ),
        },
    )


@login_required
def measurement_autosave(
    request,
    studio_slug,
    class_id,
    student_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    student = get_object_or_404(
        Student,
        pk=student_id,
        studio=studio,
        is_active=True,
        enrollments__class_instance=class_instance,
        enrollments__status="active",
    )

    field_name = (
        request.POST.get(
            "field",
            "",
        )
        .strip()
    )

    raw_value = (
        request.POST.get(
            "value",
            "",
        )
        .strip()
    )

    field_type = MEASUREMENT_FIELDS.get(
        field_name
    )

    if field_type is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Unknown measurement field.",
            },
            status=400,
        )

    measurement_set = (
        get_or_create_measurement_draft(
            student,
            studio,
            request.user,
        )
    )

    if field_type == "decimal":
        if raw_value == "":
            value = None
        else:
            try:
                value = Decimal(
                    raw_value
                )
            except InvalidOperation:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Enter a valid number.",
                    },
                    status=400,
                )
    else:
        value = raw_value

    setattr(
        measurement_set,
        field_name,
        value,
    )

    measurement_set.measured_by = (
        request.user
    )

    measurement_set.save(
        update_fields=[
            field_name,
            "measured_by",
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
            "measurement_set_id": (
                measurement_set.pk
            ),
            "saved_at": timezone.now().isoformat(),
        }
    )


@login_required
def measurement_complete(
    request,
    studio_slug,
    class_id,
    student_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    student = get_object_or_404(
        Student,
        pk=student_id,
        studio=studio,
        is_active=True,
    )

    measurement_set = (
        get_or_create_measurement_draft(
            student,
            studio,
            request.user,
        )
    )

    if not measurement_set.has_measurements:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Enter at least one measurement "
                    "before marking complete."
                ),
            },
            status=400,
        )

    measurement_set.mark_complete(
        request.user
    )

    StudentCostumeAssignment.objects.filter(
        student=student,
        is_active=True,
        status__in=[
            StudentCostumeAssignment.Status.NOT_STARTED,
            StudentCostumeAssignment.Status.MEASUREMENTS_READY,
        ],
    ).update(
        measurement_set_used=measurement_set,
        shoe_size=measurement_set.shoe_size,
        status=StudentCostumeAssignment.Status.MEASUREMENTS_READY,
    )

    return JsonResponse(
        {
            "ok": True,
            "completed_at": (
                measurement_set.measured_at.isoformat()
            ),
        }
    )


@login_required
def measurement_start_new(
    request,
    studio_slug,
    class_id,
    student_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    student = get_object_or_404(
        Student,
        pk=student_id,
        studio=studio,
        is_active=True,
    )

    measurement_set = (
        start_new_measurement_set(
            student,
            studio,
            request.user,
        )
    )

    return JsonResponse(
        {
            "ok": True,
            "measurement_set_id": (
                measurement_set.pk
            ),
        }
    )


@login_required
def costume_list(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return _access_denied(
            request,
            studio,
        )

    view_mode = request.GET.get(
        "view",
        "cards",
    )

    if view_mode not in {
        "cards",
        "list",
    }:
        view_mode = "cards"

    search = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    dance_id = (
        request.GET.get(
            "dance",
            "",
        )
        .strip()
    )

    costumes = (
        Costume.objects
        .filter(
            studio=studio,
            dance__class_instance=class_instance,
            is_active=True,
        )
        .select_related(
            "dance",
            "dance__class_instance",
        )
        .prefetch_related(
            "images",
            "purchase_links",
            "student_assignments",
        )
        .annotate(
            assignment_count=Count(
                "student_assignments",
                filter=Q(
                    student_assignments__is_active=True,
                ),
                distinct=True,
            ),
            ready_count=Count(
                "student_assignments",
                filter=Q(
                    student_assignments__is_active=True,
                    student_assignments__status=(
                        StudentCostumeAssignment.Status.READY
                    ),
                ),
                distinct=True,
            ),
        )
    )

    if search:
        costumes = costumes.filter(
            Q(
                name__icontains=search
            )
            | Q(
                dance__title__icontains=search
            )
            | Q(
                student_notes__icontains=search
            )
        )

    if dance_id.isdigit():
        costumes = costumes.filter(
            dance_id=int(
                dance_id
            )
        )

    dances = (
        ChoreographyPlan.objects
        .filter(
            studio=studio,
            class_instance=class_instance,
        )
        .order_by(
            "title",
        )
    )

    return render(
        request,
        "costumes/costume_list.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "role": workspace_role(
                request,
                studio,
            ),
            "costumes": costumes,
            "dances": dances,
            "view_mode": view_mode,
            "filters": {
                "q": search,
                "dance": dance_id,
            },
        },
    )


def _save_uploaded_images(
    request,
    costume,
):
    upload_map = {
        "front_images": (
            CostumeImage.ImageType.FRONT
        ),
        "back_images": (
            CostumeImage.ImageType.BACK
        ),
        "shoe_images": (
            CostumeImage.ImageType.SHOES
        ),
        "accessory_images": (
            CostumeImage.ImageType.ACCESSORY
        ),
        "other_images": (
            CostumeImage.ImageType.OTHER
        ),
    }

    for field_name, image_type in upload_map.items():
        files = request.FILES.getlist(
            field_name
        )

        for order, image_file in enumerate(
            files
        ):
            CostumeImage.objects.create(
                costume=costume,
                image_type=image_type,
                image=image_file,
                sort_order=order,
            )


@login_required
def costume_create(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return _access_denied(
            request,
            studio,
        )

    role = workspace_role(
        request,
        studio,
    )

    form = CostumeForm(
        request.POST or None,
        request.FILES or None,
        studio=studio,
        class_instance=class_instance,
    )

    costume = Costume(
        studio=studio,
        created_by=request.user,
    )

    link_formset = CostumeLinkFormSet(
        request.POST or None,
        instance=costume,
        prefix="links",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and link_formset.is_valid()
    ):
        costume = form.save(
            commit=False
        )

        costume.studio = studio
        costume.created_by = (
            request.user
        )

        costume.full_clean()
        costume.save()

        link_formset.instance = costume
        link_formset.save()

        _save_uploaded_images(
            request,
            costume,
        )

        sync_costume_assignments(
            costume
        )

        if form.cleaned_data.get(
            "create_student_task"
        ):
            create_costume_student_task(
                costume,
                creator=request.user,
                role=role,
                due_date=(
                    form.cleaned_data.get(
                        "task_due_date"
                    )
                ),
            )

        if form.cleaned_data.get(
            "send_notification"
        ):
            create_costume_announcement(
                costume,
                creator=request.user,
            )

        messages.success(
            request,
            (
                f"{costume.name} was created "
                "and assigned to the class roster."
            ),
        )

        return redirect(
            "costumes:costume_detail",
            studio_slug=studio.slug,
            class_id=class_instance.pk,
            costume_id=costume.pk,
        )

    return render(
        request,
        "costumes/costume_form.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "role": role,
            "form": form,
            "link_formset": link_formset,
        },
    )


@login_required
def costume_detail(
    request,
    studio_slug,
    class_id,
    costume_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return _access_denied(
            request,
            studio,
        )

    costume = get_object_or_404(
        Costume.objects
        .select_related(
            "dance",
        )
        .prefetch_related(
            "images",
            "purchase_links",
            "student_assignments__student",
            "student_assignments__measurement_set_used",
        ),
        pk=costume_id,
        studio=studio,
        dance__class_instance=class_instance,
    )

    assignments = (
        costume.student_assignments
        .filter(
            is_active=True,
        )
        .select_related(
            "student",
            "measurement_set_used",
        )
        .order_by(
            "student__last_name",
            "student__first_name",
        )
    )

    total = assignments.count()
    ready = assignments.filter(
        status=StudentCostumeAssignment.Status.READY,
    ).count()

    return render(
        request,
        "costumes/costume_detail.html",
        {
            "studio": studio,
            "class_instance": class_instance,
            "role": workspace_role(
                request,
                studio,
            ),
            "costume": costume,
            "assignments": assignments,
            "assignment_status_choices": (
                StudentCostumeAssignment.Status.choices
            ),
            "total_assignments": total,
            "ready_assignments": ready,
        },
    )


@login_required
def costume_assignment_update(
    request,
    studio_slug,
    class_id,
    costume_id,
    assignment_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = _class_for_staff(
        request,
        studio,
        class_id,
    )

    if class_instance is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    assignment = get_object_or_404(
        StudentCostumeAssignment,
        pk=assignment_id,
        costume_id=costume_id,
        costume__studio=studio,
        costume__dance__class_instance=class_instance,
    )

    allowed_fields = {
        "status",
        "costume_size",
        "shoe_size",
        "student_notes",
        "internal_notes",
    }

    field_name = request.POST.get(
        "field",
        "",
    )

    value = request.POST.get(
        "value",
        "",
    )

    if field_name not in allowed_fields:
        return JsonResponse(
            {
                "ok": False,
                "error": "Unknown field.",
            },
            status=400,
        )

    if field_name == "status":
        valid_statuses = {
            choice[0]
            for choice
            in StudentCostumeAssignment.Status.choices
        }

        if value not in valid_statuses:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Invalid status.",
                },
                status=400,
            )

    setattr(
        assignment,
        field_name,
        value,
    )

    assignment.save(
        update_fields=[
            field_name,
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
        }
    )


@login_required
def my_costumes(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = workspace_role(
        request,
        studio,
    )

    if role == StudioMembership.Role.STUDENT:
        student = getattr(
            request.user,
            "student_profile",
            None,
        )

        student_ids = (
            [student.pk]
            if student
            and student.studio_id
            == studio.pk
            else []
        )

    elif role == StudioMembership.Role.FAMILY:
        student_ids = family_student_ids(
            request.user,
            studio,
        )

    else:
        return _access_denied(
            request,
            studio,
        )

    assignments = (
        StudentCostumeAssignment.objects
        .filter(
            student_id__in=student_ids,
            is_active=True,
            costume__is_active=True,
        )
        .select_related(
            "student",
            "costume",
            "costume__dance",
            "costume__dance__class_instance",
        )
        .prefetch_related(
            "costume__images",
            "costume__purchase_links",
        )
        .order_by(
            "student__first_name",
            "costume__dance__title",
        )
    )

    return render(
        request,
        "costumes/my_costumes.html",
        {
            "studio": studio,
            "role": role,
            "assignments": assignments,
        },
    )
