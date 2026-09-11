from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from families.models import Guardian
from instructors.models import Instructor
from studios.models import Studio

from .forms import ClassResourceForm
from .models import ClassResource


def _teacher(user, studio):
    return Instructor.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()


def _workspace_role(request, studio):
    """
    Use the workspace explicitly chosen on login/switch rather than
    inferring a role from every membership the account owns.
    """
    selected_role = request.session.get(
        "encore_workspace_role"
    )

    selected_studio = request.session.get(
        "encore_workspace_studio_slug"
    )

    if selected_studio != studio.slug:
        return None

    if (
        request.user.is_superuser
        and selected_role == "administrator"
    ):
        return "administrator"

    if selected_role not in {
        "administrator",
        "teacher",
        "family",
        "student",
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=selected_role,
        is_active=True,
    ).exists():
        return selected_role

    return None


def _family_resource_queryset(user, studio):
    """
    Use the same Guardian relationship already used by the Family
    dashboard. The previous version guessed at a reverse relation
    named guardian_profiles, which is why valid family resources
    could come back empty.
    """
    family_ids = list(
        Guardian.objects
        .filter(
            family__studio=studio,
            user=user,
            is_active=True,
        )
        .values_list(
            "family_id",
            flat=True,
        )
    )

    if not family_ids:
        return ClassResource.objects.none()

    return (
        ClassResource.objects
        .filter(
            studio=studio,
            is_active=True,
            visibility=ClassResource.Visibility.ENROLLED,
            class_instance__is_active=True,
            class_instance__enrollments__student__family_id__in=family_ids,
            class_instance__enrollments__student__is_active=True,
            class_instance__enrollments__status="active",
        )
        .distinct()
    )


def _student_resource_queryset(user, studio):
    return (
        ClassResource.objects
        .filter(
            studio=studio,
            is_active=True,
            visibility=ClassResource.Visibility.ENROLLED,
            class_instance__is_active=True,
            class_instance__enrollments__student__user=user,
            class_instance__enrollments__student__is_active=True,
            class_instance__enrollments__status="active",
        )
        .distinct()
    )


@login_required
def resource_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _workspace_role(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = _teacher(
        request.user,
        studio,
    )

    if role == "administrator":
        resources = ClassResource.objects.filter(
            studio=studio,
        )

    elif role == "teacher":
        if instructor is None:
            return render(
                request,
                "dashboard/access_denied.html",
                {"studio": studio},
                status=403,
            )

        resources = (
            ClassResource.objects
            .filter(studio=studio)
            .filter(
                Q(class_instance__instructor=instructor)
                | Q(
                    class_instance__assistant_instructor=instructor
                )
            )
            .distinct()
        )

    elif role == "family":
        resources = _family_resource_queryset(
            request.user,
            studio,
        )

    else:
        resources = _student_resource_queryset(
            request.user,
            studio,
        )

    resources = (
        resources
        .select_related(
            "class_instance",
            "class_instance__season",
            "uploaded_by",
        )
        .order_by(
            "class_instance__name",
            "sort_order",
            "-created_at",
        )
    )

    search = request.GET.get(
        "q",
        "",
    ).strip()

    resource_type = request.GET.get(
        "type",
        "",
    ).strip()

    class_id = request.GET.get(
        "class",
        "",
    ).strip()

    if search:
        resources = resources.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(
                class_instance__name__icontains=search
            )
        )

    if resource_type:
        resources = resources.filter(
            resource_type=resource_type,
        )

    if class_id:
        resources = resources.filter(
            class_instance_id=class_id,
        )

    # Evaluate once so the same filtered result drives both the class
    # dropdown and the grouped resource cards.
    resource_list = list(resources)

    accessible_classes = []
    seen_classes = set()

    for resource in resource_list:
        class_instance = resource.class_instance

        if class_instance.id in seen_classes:
            continue

        seen_classes.add(
            class_instance.id
        )

        accessible_classes.append(
            {
                "class_instance_id": class_instance.id,
                "class_instance__name": class_instance.name,
                "class_instance__class_id": class_instance.class_id,
            }
        )

    grouped = {}

    for resource in resource_list:
        grouped.setdefault(
            resource.class_instance,
            [],
        ).append(resource)

    return render(
        request,
        "resources/resource_list.html",
        {
            "studio": studio,
            "role": role,
            "resource_groups": grouped.items(),
            "resource_types": ClassResource.ResourceType.choices,
            "accessible_classes": accessible_classes,
            "filters": {
                "q": search,
                "type": resource_type,
                "class": class_id,
            },
            "can_manage": role in [
                "administrator",
                "teacher",
            ],
        },
    )


@login_required
def resource_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _workspace_role(
        request,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = _teacher(
        request.user,
        studio,
    )

    teacher_mode = (
        role == "teacher"
    )

    if teacher_mode and instructor is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method == "POST":
        form = ClassResourceForm(
            request.POST,
            request.FILES,
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
        )

        if form.is_valid():
            resource = form.save(
                commit=False
            )

            resource.studio = studio

            if instructor is not None:
                resource.uploaded_by = instructor

            resource.full_clean()
            resource.save()

            messages.success(
                request,
                "Class resource added.",
            )

            return redirect(
                "resources:resource_list",
                studio_slug=studio.slug,
            )
    else:
        form = ClassResourceForm(
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
            initial={
                "visibility": (
                    ClassResource.Visibility.ENROLLED
                ),
                "is_active": True,
            },
        )

    return render(
        request,
        "resources/resource_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Add Class Resource",
        },
    )


@login_required
def resource_edit(
    request,
    studio_slug,
    resource_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _workspace_role(
        request,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    resource = get_object_or_404(
        ClassResource,
        pk=resource_id,
        studio=studio,
    )

    instructor = _teacher(
        request.user,
        studio,
    )

    teacher_mode = (
        role == "teacher"
    )

    if teacher_mode:
        if instructor is None:
            return render(
                request,
                "dashboard/access_denied.html",
                {"studio": studio},
                status=403,
            )

        allowed = (
            resource.class_instance.instructor_id
            == instructor.id
            or
            resource.class_instance.assistant_instructor_id
            == instructor.id
        )

        if not allowed:
            return render(
                request,
                "dashboard/access_denied.html",
                {"studio": studio},
                status=403,
            )

    if request.method == "POST":
        form = ClassResourceForm(
            request.POST,
            request.FILES,
            instance=resource,
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
        )

        if form.is_valid():
            resource = form.save(
                commit=False
            )

            resource.full_clean()
            resource.save()

            messages.success(
                request,
                "Class resource updated.",
            )

            return redirect(
                "resources:resource_list",
                studio_slug=studio.slug,
            )
    else:
        form = ClassResourceForm(
            instance=resource,
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
        )

    return render(
        request,
        "resources/resource_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Edit Class Resource",
        },
    )
