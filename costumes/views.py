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
from dashboard.parent_portal import parent_portal_context
from studios.models import (
    Studio,
    StudioMembership,
)

from .forms import (
    CostumeForm,
    CostumeLinkFormSet,
    VendorForm,
    VendorSizeChartForm,
    VendorSizeEntryFormSet,
)
from .models import (
    Costume,
    CostumeImage,
    StudentCostumeAssignment,
    StudentMeasurementSet,
    Vendor,
    VendorSizeChart,
)
from .services import (
    can_manage_class,
    cancel_measurement_draft,
    chart_size_for_field,
    create_costume_announcement,
    create_costume_student_task,
    current_completed_measurement,
    current_draft_measurement,
    family_student_ids,
    get_or_create_measurement_draft,
    measurement_state,
    measurement_from_display,
    measurement_to_display,
    recommend_size_for_chart,
    start_new_measurement_set,
    vendor_measurement_conversions,
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

MEASUREMENT_LABELS = {
    "bust": "Chest",
    "waist": "Waist",
    "hips": "Hips",
    "girth": "Girth",
    "inseam": "Inseam",
    "outseam": "Outseam",
    "height": "Height",
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

    settings_obj = getattr(studio, "settings", None)
    unit = getattr(settings_obj, "measurement_unit", "in")
    unit_label = "cm" if unit == "cm" else "in."

    vendors = Vendor.objects.filter(studio=studio, is_active=True).order_by("name")
    selected_vendor = None
    vendor_id = str(request.GET.get("vendor", "") or "").strip()
    if vendor_id.isdigit():
        selected_vendor = vendors.filter(pk=int(vendor_id)).first()

    rows = []
    numeric_fields = ("bust", "waist", "hips", "girth", "inseam", "outseam", "height")
    text_fields = ("clothing_size", "shoe_size", "other_size_info", "notes")

    for student in active_students:
        draft = current_draft_measurement(student)
        current = current_completed_measurement(student)
        state = measurement_state(student)
        edit_set = draft if draft is not None else current

        edit_values = {}
        for field_name in numeric_fields:
            value = getattr(edit_set, field_name, None) if edit_set else None
            display = measurement_to_display(value, unit)
            edit_values[field_name] = "" if display is None else f"{display:g}"
        for field_name in text_fields:
            edit_values[field_name] = getattr(edit_set, field_name, "") if edit_set else ""

        current_values = {}
        for field_name in numeric_fields:
            value = getattr(current, field_name, None) if current else None
            display = measurement_to_display(value, unit)
            current_values[field_name] = None if display is None else f"{display:g}"
        for field_name in ("clothing_size", "shoe_size"):
            current_values[field_name] = getattr(current, field_name, "") if current else ""

        conversions = []
        conversion_source = draft or current
        if selected_vendor and conversion_source:
            for item in vendor_measurement_conversions(selected_vendor, conversion_source):
                display = measurement_to_display(item["value"], unit)
                conversions.append({
                    "field": item["field"],
                    "label": MEASUREMENT_LABELS.get(
                        item["field"],
                        item["field"].title(),
                    ),
                    "value": f"{display:g}" if display is not None else "",
                    "charts": item["charts"],
                })

        rows.append({
            "student": student, "draft": draft, "current": current,
            "edit_set": edit_set, "edit_values": edit_values,
            "current_values": current_values, "state": state,
            "conversions": conversions,
        })

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
            "vendors": vendors,
            "selected_vendor": selected_vendor,
            "measurement_unit": unit,
            "measurement_unit_label": unit_label,
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

    settings_obj = getattr(studio, "settings", None)
    unit = getattr(settings_obj, "measurement_unit", "in")

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
                display_value = Decimal(raw_value)
                value = Decimal(str(measurement_from_display(float(display_value), unit)))
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

    vendor = None
    vendor_id = str(request.POST.get("vendor_id", "") or "").strip()
    if vendor_id.isdigit():
        vendor = Vendor.objects.filter(pk=int(vendor_id), studio=studio, is_active=True).first()
    conversions = []
    if vendor:
        for item in vendor_measurement_conversions(vendor, measurement_set):
            display = measurement_to_display(item["value"], unit)
            conversions.append({
                "field": item["field"],
                "label": MEASUREMENT_LABELS.get(
                    item["field"],
                    item["field"].title(),
                ),
                "value": f"{display:g}" if display is not None else "",
                "charts": item["charts"],
            })
    return JsonResponse({
        "ok": True,
        "measurement_set_id": measurement_set.pk,
        "saved_at": timezone.now().isoformat(),
        "conversions": conversions,
    })


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

    unit = getattr(
        getattr(studio, "settings", None),
        "measurement_unit",
        "in",
    )

    values = {}
    for field_name in MEASUREMENT_FIELDS:
        value = getattr(measurement_set, field_name)
        if MEASUREMENT_FIELDS[field_name] == "decimal":
            value = measurement_to_display(value, unit)
        values[field_name] = "" if value is None else str(value)

    vendor = None
    vendor_id = str(request.POST.get("vendor_id", "") or "").strip()
    if vendor_id.isdigit():
        vendor = Vendor.objects.filter(
            pk=int(vendor_id),
            studio=studio,
            is_active=True,
        ).first()

    conversions = []
    if vendor:
        for item in vendor_measurement_conversions(vendor, measurement_set):
            display = measurement_to_display(item["value"], unit)
            conversions.append(
                {
                    "field": item["field"],
                    "label": MEASUREMENT_LABELS.get(
                        item["field"],
                        item["field"].title(),
                    ),
                    "value": f"{display:g}" if display is not None else "",
                    "charts": item["charts"],
                }
            )

    return JsonResponse(
        {
            "ok": True,
            "completed_at": measurement_set.measured_at.isoformat(),
            "values": values,
            "conversions": conversions,
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

    unit = getattr(getattr(studio, "settings", None), "measurement_unit", "in")
    values = {}
    for field_name in MEASUREMENT_FIELDS:
        value = getattr(measurement_set, field_name)
        if MEASUREMENT_FIELDS[field_name] == "decimal":
            value = measurement_to_display(value, unit)
        values[field_name] = "" if value is None else str(value)
    return JsonResponse({"ok": True, "measurement_set_id": measurement_set.pk, "values": values})


@login_required
def measurement_cancel(
    request, studio_slug, class_id, student_id,
):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    class_instance = _class_for_staff(request, studio, class_id)
    if class_instance is None:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)
    student = get_object_or_404(Student, pk=student_id, studio=studio, is_active=True)
    current = cancel_measurement_draft(student, studio)
    unit = getattr(getattr(studio, "settings", None), "measurement_unit", "in")
    values = {}
    if current:
        for field_name in MEASUREMENT_FIELDS:
            value = getattr(current, field_name)
            if MEASUREMENT_FIELDS[field_name] == "decimal":
                value = measurement_to_display(value, unit)
            values[field_name] = "" if value is None else str(value)
    return JsonResponse({
        "ok": True,
        "has_current": bool(current),
        "values": values,
        "state": measurement_state(student),
    })


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

    requested_dance_id = str(
        request.GET.get("dance", "") or ""
    ).strip()

    initial = {}
    if requested_dance_id.isdigit():
        requested_dance = ChoreographyPlan.objects.filter(
            pk=int(requested_dance_id),
            studio=studio,
            class_instance=class_instance,
        ).first()
        if requested_dance is not None:
            initial["dance"] = requested_dance

    form = CostumeForm(
        request.POST or None,
        request.FILES or None,
        studio=studio,
        class_instance=class_instance,
        initial=initial,
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
            "vendors": Vendor.objects.filter(studio=studio, is_active=True).order_by("name"),
        },
    )


@login_required
def costume_edit(request, studio_slug, class_id, costume_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    class_instance = _class_for_staff(request, studio, class_id)
    if class_instance is None:
        return _access_denied(request, studio)
    costume = get_object_or_404(Costume, pk=costume_id, studio=studio, dance__class_instance=class_instance)
    role = workspace_role(request, studio)
    form = CostumeForm(request.POST or None, request.FILES or None, instance=costume, studio=studio, class_instance=class_instance)
    link_formset = CostumeLinkFormSet(request.POST or None, instance=costume, prefix="links")
    if request.method == "POST" and form.is_valid() and link_formset.is_valid():
        costume = form.save()
        link_formset.save()
        _save_uploaded_images(request, costume)
        sync_costume_assignments(costume)
        messages.success(request, f"{costume.name} was updated.")
        return redirect("costumes:costume_detail", studio_slug=studio.slug, class_id=class_instance.pk, costume_id=costume.pk)
    return render(request, "costumes/costume_form.html", {
        "studio": studio, "class_instance": class_instance, "role": role,
        "form": form, "link_formset": link_formset, "costume": costume, "is_edit": True,
        "vendors": Vendor.objects.filter(studio=studio, is_active=True).order_by("name"),
    })


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
            "dance", "vendor", "vendor_size_chart",
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
    ready = assignments.filter(status=StudentCostumeAssignment.Status.READY).count()
    assignment_rows = []
    for assignment in assignments:
        measurement_set = assignment.measurement_set_used or current_completed_measurement(assignment.student)
        recommended = recommend_size_for_chart(costume.vendor_size_chart, measurement_set)
        assignment_rows.append({"assignment": assignment, "recommended_size": recommended})

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
            "assignment_rows": assignment_rows,
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

    selected_student_id = str(
        request.GET.get("student", "") or ""
    ).strip()

    selected_class_id = str(
        request.GET.get("class", "") or ""
    ).strip()

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
            "costume__vendor",
            "costume__vendor_size_chart",
            "measurement_set_used",
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

    if selected_student_id.isdigit():
        assignments = assignments.filter(
            student_id=int(selected_student_id)
        )

    if selected_class_id.isdigit():
        assignments = assignments.filter(
            costume__dance__class_instance_id=int(
                selected_class_id
            )
        )

    assignment_rows = []
    for assignment in assignments:
        measurement_set = (
            assignment.measurement_set_used
            or current_completed_measurement(assignment.student)
        )
        recommended = recommend_size_for_chart(
            assignment.costume.vendor_size_chart,
            measurement_set,
        )
        assignment_rows.append({
            "assignment": assignment,
            "recommended_size": recommended,
            "display_size": assignment.costume_size or recommended or "",
        })

    context = {
        "studio": studio,
        "role": role,
        "assignments": assignments,
        "assignment_rows": assignment_rows,
        "selected_class_id": selected_class_id,
    }

    template_name = "costumes/my_costumes.html"

    if role == StudioMembership.Role.FAMILY:
        selected_student = None
        if selected_student_id.isdigit():
            selected_student = Student.objects.filter(
                pk=int(selected_student_id),
                studio=studio,
                pk__in=student_ids,
                is_active=True,
            ).first()

        context.update(
            parent_portal_context(
                request,
                studio,
                selected_student=selected_student,
                section="costumes",
            )
        )
        template_name = "costumes/parent_costumes.html"

    return render(
        request,
        template_name,
        context,
    )



def _admin_role(request, studio):
    role = workspace_role(request, studio)
    return role if role == StudioMembership.Role.ADMINISTRATOR else None


@login_required
def vendor_list(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    vendors = Vendor.objects.filter(studio=studio).prefetch_related("size_charts").order_by("name")
    return render(request, "costumes/vendor_list.html", {"studio": studio, "role": "administrator", "vendors": vendors, "settings_section": "vendors"})


@login_required
def vendor_create(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    form = VendorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        vendor = form.save(commit=False); vendor.studio = studio; vendor.save()
        messages.success(request, "Vendor created.")
        return redirect("costumes:vendor_detail", studio_slug=studio.slug, vendor_id=vendor.pk)
    return render(request, "costumes/vendor_form.html", {"studio": studio, "role": "administrator", "form": form, "page_title": "Add Vendor", "settings_section": "vendors"})


@login_required
def vendor_edit(request, studio_slug, vendor_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    vendor = get_object_or_404(Vendor, pk=vendor_id, studio=studio)
    form = VendorForm(request.POST or None, instance=vendor)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Vendor updated.")
        return redirect("costumes:vendor_detail", studio_slug=studio.slug, vendor_id=vendor.pk)
    return render(request, "costumes/vendor_form.html", {"studio": studio, "role": "administrator", "form": form, "vendor": vendor, "page_title": "Edit Vendor", "settings_section": "vendors"})



@login_required
def vendor_delete(request, studio_slug, vendor_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)

    vendor = get_object_or_404(Vendor, pk=vendor_id, studio=studio)

    if request.method != "POST":
        return redirect(
            "costumes:vendor_detail",
            studio_slug=studio.slug,
            vendor_id=vendor.pk,
        )

    vendor_name = vendor.name
    linked_costumes = vendor.costumes.count()
    chart_count = vendor.size_charts.count()
    vendor.delete()

    details = []
    if chart_count:
        details.append(
            f'{chart_count} size chart{" was" if chart_count == 1 else "s were"} also removed'
        )
    if linked_costumes:
        details.append(
            f'{linked_costumes} linked costume{" was" if linked_costumes == 1 else "s were"} kept with vendor and size chart cleared'
        )

    message = f"{vendor_name} was deleted."
    if details:
        message += " " + "; ".join(details) + "."

    messages.success(request, message)

    return redirect(
        "costumes:vendor_list",
        studio_slug=studio.slug,
    )

@login_required
def vendor_detail(request, studio_slug, vendor_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    vendor = get_object_or_404(Vendor.objects.prefetch_related("size_charts__entries"), pk=vendor_id, studio=studio)
    return render(request, "costumes/vendor_detail.html", {"studio": studio, "role": "administrator", "vendor": vendor, "settings_section": "vendors"})


@login_required
def vendor_chart_create(request, studio_slug, vendor_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    vendor = get_object_or_404(Vendor, pk=vendor_id, studio=studio)
    chart = VendorSizeChart(vendor=vendor)
    form = VendorSizeChartForm(request.POST or None, instance=chart)
    formset = VendorSizeEntryFormSet(request.POST or None, instance=chart, prefix="entries", form_kwargs={"studio": studio})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        chart = form.save(commit=False); chart.vendor = vendor; chart.save(); formset.instance = chart; formset.save()
        messages.success(request, "Size chart created.")
        return redirect("costumes:vendor_detail", studio_slug=studio.slug, vendor_id=vendor.pk)
    return render(request, "costumes/vendor_chart_form.html", {"studio": studio, "role": "administrator", "vendor": vendor, "chart": chart, "form": form, "formset": formset, "page_title": "Add Size Chart", "measurement_unit": getattr(studio.settings, "measurement_unit", "in"), "settings_section": "vendors"})


@login_required
def vendor_chart_edit(request, studio_slug, vendor_id, chart_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)
    vendor = get_object_or_404(Vendor, pk=vendor_id, studio=studio)
    chart = get_object_or_404(VendorSizeChart, pk=chart_id, vendor=vendor)
    form = VendorSizeChartForm(request.POST or None, instance=chart)
    formset = VendorSizeEntryFormSet(request.POST or None, instance=chart, prefix="entries", form_kwargs={"studio": studio})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save(); formset.save(); messages.success(request, "Size chart updated.")
        return redirect("costumes:vendor_detail", studio_slug=studio.slug, vendor_id=vendor.pk)
    return render(request, "costumes/vendor_chart_form.html", {"studio": studio, "role": "administrator", "vendor": vendor, "chart": chart, "form": form, "formset": formset, "page_title": "Edit Size Chart", "measurement_unit": getattr(studio.settings, "measurement_unit", "in"), "settings_section": "vendors"})


@login_required
def vendor_chart_delete(request, studio_slug, vendor_id, chart_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _admin_role(request, studio) is None:
        return _access_denied(request, studio)

    vendor = get_object_or_404(Vendor, pk=vendor_id, studio=studio)
    chart = get_object_or_404(VendorSizeChart, pk=chart_id, vendor=vendor)

    if request.method != "POST":
        return redirect(
            "costumes:vendor_detail",
            studio_slug=studio.slug,
            vendor_id=vendor.pk,
        )

    chart_name = chart.name
    linked_costumes = chart.costumes.count()
    chart.delete()

    if linked_costumes:
        messages.success(
            request,
            f'{chart_name} was removed. {linked_costumes} linked costume'
            f'{" was" if linked_costumes == 1 else "s were"} kept, with the size chart cleared.',
        )
    else:
        messages.success(request, f"{chart_name} was removed.")

    return redirect(
        "costumes:vendor_detail",
        studio_slug=studio.slug,
        vendor_id=vendor.pk,
    )
