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
from django.utils.http import url_has_allowed_host_and_scheme

from enrollments.models import Enrollment
from students.models import Student
from studios.models import (
    Studio,
    StudioMembership,
)

from .forms import (
    TaskForm,
    TaskTemplateForm,
    TaskTemplateItemFormSet,
    TaskTemplateTriggerForm,
    TaskTemplateTriggerFormSet,
)
from .models import (
    Task,
    TaskTemplate,
    TaskTemplateTrigger,
)
from .services import (
    approve_task,
    complete_or_reopen_for_user,
    deny_task,
    run_task_template,
    selected_workspace_role,
    synchronize_task_assignments,
    task_assignment_for_user,
    visible_tasks_for_user,
)


def _access_denied(
    request,
    studio,
):
    return render(
        request,
        "dashboard/access_denied.html",
        {"studio": studio},
        status=403,
    )


def _safe_next(
    request,
    fallback,
):
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
    )

    if (
        next_url
        and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={
                request.get_host()
            },
            require_https=request.is_secure(),
        )
    ):
        return next_url

    return fallback


@login_required
def task_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role is None:
        return _access_denied(
            request,
            studio,
        )

    tab = request.GET.get(
        "tab",
        "mine",
    )

    show_completed = (
        request.GET.get(
            "completed"
        )
        == "1"
    )

    base = Task.objects.filter(
        studio=studio,
        is_active=True,
    )

    if tab == "created":
        tasks = base.filter(
            created_by=request.user,
        )

    elif (
        tab == "assigned"
        and role
        == StudioMembership.Role.ADMINISTRATOR
    ):
        tasks = (
            base.filter(
                created_by=request.user,
            )
            .exclude(
                audience_type=Task.AudienceType.SELF,
            )
        )

    elif (
        tab == "requests"
        and role
        == StudioMembership.Role.ADMINISTRATOR
    ):
        tasks = base.filter(
            approval_status=Task.ApprovalStatus.PENDING,
        )

    elif tab == "class":
        tasks = (
            visible_tasks_for_user(
                request.user,
                studio,
                role,
            )
            .filter(
                context_type=Task.ContextType.CLASS,
            )
        )

    else:
        tasks = visible_tasks_for_user(
            request.user,
            studio,
            role,
        )

    rows = []

    for task in tasks.distinct():
        assignment = (
            task_assignment_for_user(
                task,
                request.user,
                role,
            )
        )

        if show_completed:
            if not (
                assignment
                and assignment.completed_at
            ):
                continue
        else:
            if (
                assignment
                and assignment.completed_at
            ):
                continue

        rows.append(
            {
                "task": task,
                "assignment": assignment,
                "can_complete": (
                    assignment is not None
                ),
                "assignment_count": (
                    task.assignments.count()
                ),
                "completed_count": (
                    task.assignments
                    .filter(
                        completed_at__isnull=False,
                    )
                    .count()
                ),
            }
        )

    return render(
        request,
        "tasks/task_list.html",
        {
            "studio": studio,
            "role": role,
            "task_rows": rows,
            "show_completed": show_completed,
            "active_tab": tab,
        },
    )


@login_required
def task_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return _access_denied(
            request,
            studio,
        )

    initial = {}

    class_id = request.GET.get(
        "class"
    )

    student_id = request.GET.get(
        "student"
    )

    if (
        class_id
        and class_id.isdigit()
    ):
        initial[
            "class_instance"
        ] = class_id

        initial[
            "context_type"
        ] = Task.ContextType.CLASS

    if (
        student_id
        and student_id.isdigit()
    ):
        initial[
            "student"
        ] = student_id

    form = TaskForm(
        request.POST or None,
        studio=studio,
        user=request.user,
        role=role,
        initial=initial,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        task = form.save(
            commit=False
        )

        task.studio = studio
        task.created_by = (
            request.user
        )

        task.full_clean()
        task.save()

        synchronize_task_assignments(
            task,
            creator=request.user,
            role=role,
            selected_teachers=(
                form.cleaned_data.get(
                    "selected_teachers"
                )
            ),
            selected_students=(
                form.cleaned_data.get(
                    "selected_students"
                )
            ),
        )

        if (
            task.approval_status
            == Task.ApprovalStatus.PENDING
        ):
            messages.success(
                request,
                "Task request sent to the administrator for approval.",
            )
        else:
            messages.success(
                request,
                "Task created.",
            )

        return redirect(
            _safe_next(
                request,
                f"/tasks/{studio.slug}/",
            )
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Add Task",
        },
    )


@login_required
def task_edit(
    request,
    studio_slug,
    task_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role is None:
        return _access_denied(
            request,
            studio,
        )

    task = get_object_or_404(
        Task,
        pk=task_id,
        studio=studio,
    )

    if not (
        role
        == StudioMembership.Role.ADMINISTRATOR
        or task.created_by_id
        == request.user.id
    ):
        return _access_denied(
            request,
            studio,
        )

    form = TaskForm(
        request.POST or None,
        instance=task,
        studio=studio,
        user=request.user,
        role=role,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        task = form.save()

        synchronize_task_assignments(
            task,
            creator=(
                task.created_by
                or request.user
            ),
            role=role,
            selected_teachers=(
                form.cleaned_data.get(
                    "selected_teachers"
                )
            ),
            selected_students=(
                form.cleaned_data.get(
                    "selected_students"
                )
            ),
        )

        messages.success(
            request,
            "Task updated.",
        )

        return redirect(
            _safe_next(
                request,
                f"/tasks/{studio.slug}/",
            )
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "task": task,
            "page_title": "Edit Task",
        },
    )


@login_required
def task_delete(
    request,
    studio_slug,
    task_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    task = get_object_or_404(
        Task,
        pk=task_id,
        studio=studio,
    )

    if not (
        role
        == StudioMembership.Role.ADMINISTRATOR
        or task.created_by_id
        == request.user.id
    ):
        return _access_denied(
            request,
            studio,
        )

    if request.method == "POST":
        task.delete()

        messages.success(
            request,
            "Task deleted.",
        )

    return redirect(
        _safe_next(
            request,
            f"/tasks/{studio.slug}/",
        )
    )


@login_required
def task_quick_add(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return _access_denied(
            request,
            studio,
        )

    if request.method == "POST":
        title = (
            request.POST.get(
                "title",
                "",
            )
            .strip()
        )

        if title:
            task = Task.objects.create(
                studio=studio,
                title=title[:255],
                created_by=request.user,
                context_type=Task.ContextType.PERSONAL,
                audience_type=Task.AudienceType.SELF,
            )

            synchronize_task_assignments(
                task,
                creator=request.user,
                role=role,
            )

    return redirect(
        _safe_next(
            request,
            f"/tasks/{studio.slug}/",
        )
    )


@login_required
def task_toggle_complete(
    request,
    studio_slug,
    task_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role is None:
        return _access_denied(
            request,
            studio,
        )

    task = get_object_or_404(
        visible_tasks_for_user(
            request.user,
            studio,
            role,
        ),
        pk=task_id,
    )

    if request.method == "POST":
        complete_or_reopen_for_user(
            task,
            request.user,
            role,
        )

    return redirect(
        _safe_next(
            request,
            f"/tasks/{studio.slug}/",
        )
    )


@login_required
def task_approval(
    request,
    studio_slug,
    task_id,
    decision,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if (
        role
        != StudioMembership.Role.ADMINISTRATOR
    ):
        return _access_denied(
            request,
            studio,
        )

    task = get_object_or_404(
        Task,
        pk=task_id,
        studio=studio,
        approval_status=Task.ApprovalStatus.PENDING,
    )

    if request.method == "POST":
        note = (
            request.POST.get(
                "note",
                "",
            )
            .strip()
        )

        if decision == "approve":
            approve_task(
                task,
                request.user,
                note,
            )

            messages.success(
                request,
                "Task request approved.",
            )

        elif decision == "deny":
            deny_task(
                task,
                request.user,
                note,
            )

            messages.success(
                request,
                "Task request denied.",
            )

    return redirect(
        "tasks:task_list",
        studio_slug=studio.slug,
    )


@login_required
def class_roster_options(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return JsonResponse(
            {"results": []},
            status=403,
        )

    class_id = request.GET.get(
        "class_id",
        "",
    )

    students = Student.objects.none()

    if class_id.isdigit():
        students = Student.objects.filter(
            studio=studio,
            is_active=True,
            enrollments__class_instance_id=int(
                class_id
            ),
            enrollments__status=Enrollment.Status.ACTIVE,
        ).distinct()

        if (
            role
            == StudioMembership.Role.TEACHER
        ):
            students = students.filter(
                Q(
                    enrollments__class_instance__instructor__user=request.user
                )
                | Q(
                    enrollments__class_instance__assistant_instructor__user=request.user
                )
            ).distinct()

    return JsonResponse(
        {
            "results": [
                {
                    "id": student.pk,
                    "label": str(
                        student
                    ),
                }
                for student
                in students.order_by(
                    "last_name",
                    "first_name",
                )
            ]
        }
    )


def _visible_templates(
    user,
    studio,
):
    return TaskTemplate.objects.filter(
        studio=studio,
    ).filter(
        Q(created_by=user)
        | Q(
            visibility=TaskTemplate.Visibility.STUDIO
        )
    ).distinct()


@login_required
def template_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return _access_denied(
            request,
            studio,
        )

    templates = (
        _visible_templates(
            request.user,
            studio,
        )
        .select_related(
            "created_by",
        )
        .annotate(
            item_count=Count(
                "items",
                distinct=True,
            ),
            trigger_count=Count(
                "triggers",
                distinct=True,
            ),
        )
    )

    return render(
        request,
        "tasks/template_list.html",
        {
            "studio": studio,
            "role": role,
            "templates": templates,
        },
    )


@login_required
def template_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return _access_denied(
            request,
            studio,
        )

    template = TaskTemplate(
        studio=studio,
        created_by=request.user,
    )

    form = TaskTemplateForm(
        request.POST or None,
        instance=template,
    )

    item_formset = TaskTemplateItemFormSet(
        request.POST or None,
        instance=template,
        prefix="items",
    )

    trigger_formset = TaskTemplateTriggerFormSet(
        request.POST or None,
        instance=template,
        prefix="triggers",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and item_formset.is_valid()
        and trigger_formset.is_valid()
    ):
        template = form.save(
            commit=False
        )
        template.studio = studio
        template.created_by = request.user
        template.save()

        item_formset.instance = template
        item_formset.save()

        trigger_formset.instance = template
        trigger_formset.save()

        if not template.triggers.exists():
            TaskTemplateTrigger.objects.create(
                template=template,
                trigger_type=TaskTemplateTrigger.TriggerType.MANUAL,
                is_enabled=True,
            )

        messages.success(
            request,
            "Task template created.",
        )

        return redirect(
            "tasks:template_detail",
            studio_slug=studio.slug,
            template_id=template.pk,
        )

    return render(
        request,
        "tasks/template_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "item_formset": item_formset,
            "trigger_formset": trigger_formset,
            "page_title": "Create Task Template",
        },
    )


@login_required
def template_detail(
    request,
    studio_slug,
    template_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    template = get_object_or_404(
        _visible_templates(
            request.user,
            studio,
        )
        .select_related(
            "created_by",
        )
        .prefetch_related(
            "items",
            "triggers",
        ),
        pk=template_id,
    )

    can_manage = (
        role
        == StudioMembership.Role.ADMINISTRATOR
        or template.created_by_id
        == request.user.id
    )

    return render(
        request,
        "tasks/template_detail.html",
        {
            "studio": studio,
            "role": role,
            "template": template,
            "can_manage": can_manage,
            "recent_runs": template.runs.all()[:10],
        },
    )


@login_required
def template_edit(
    request,
    studio_slug,
    template_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    template = get_object_or_404(
        TaskTemplate,
        pk=template_id,
        studio=studio,
    )

    if not (
        role == StudioMembership.Role.ADMINISTRATOR
        or template.created_by_id == request.user.id
    ):
        return _access_denied(
            request,
            studio,
        )

    form = TaskTemplateForm(
        request.POST or None,
        instance=template,
    )

    item_formset = TaskTemplateItemFormSet(
        request.POST or None,
        instance=template,
        prefix="items",
    )

    trigger_formset = TaskTemplateTriggerFormSet(
        request.POST or None,
        instance=template,
        prefix="triggers",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and item_formset.is_valid()
        and trigger_formset.is_valid()
    ):
        form.save()
        item_formset.save()
        trigger_formset.save()

        if not template.triggers.exists():
            TaskTemplateTrigger.objects.create(
                template=template,
                trigger_type=TaskTemplateTrigger.TriggerType.MANUAL,
                is_enabled=True,
            )

        messages.success(
            request,
            "Task template updated.",
        )

        return redirect(
            "tasks:template_detail",
            studio_slug=studio.slug,
            template_id=template.pk,
        )

    return render(
        request,
        "tasks/template_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "item_formset": item_formset,
            "trigger_formset": trigger_formset,
            "template": template,
            "page_title": "Edit Task Template",
        },
    )


@login_required
def template_trigger_add(
    request,
    studio_slug,
    template_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    template = get_object_or_404(
        TaskTemplate,
        pk=template_id,
        studio=studio,
    )

    if not (
        role
        == StudioMembership.Role.ADMINISTRATOR
        or template.created_by_id
        == request.user.id
    ):
        return _access_denied(
            request,
            studio,
        )

    trigger = TaskTemplateTrigger(
        template=template,
    )

    form = TaskTemplateTriggerForm(
        request.POST or None,
        instance=trigger,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        trigger = form.save(
            commit=False
        )
        trigger.template = template
        trigger.save()

        messages.success(
            request,
            "Template trigger added.",
        )

        return redirect(
            "tasks:template_detail",
            studio_slug=studio.slug,
            template_id=template.pk,
        )

    return render(
        request,
        "tasks/template_trigger_form.html",
        {
            "studio": studio,
            "role": role,
            "template": template,
            "form": form,
        },
    )


@login_required
def template_run(
    request,
    studio_slug,
    template_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = selected_workspace_role(
        request,
        studio,
    )

    template = get_object_or_404(
        _visible_templates(
            request.user,
            studio,
        ),
        pk=template_id,
    )

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return _access_denied(
            request,
            studio,
        )

    if request.method == "POST":
        class_id = request.POST.get(
            "class_id",
            "",
        )

        class_instance = None

        if class_id.isdigit():
            class_instance = (
                studio.classes
                .filter(
                    pk=int(
                        class_id
                    ),
                )
                .first()
            )

        run = run_task_template(
            template,
            started_by=request.user,
            class_instance=class_instance,
            occurrence_key=(
                f"manual-"
                f"{request.user.pk}-"
                f"{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
            ),
        )

        messages.success(
            request,
            (
                f"Template created "
                f"{run.tasks_created_count} task(s)."
            ),
        )

    return redirect(
        "tasks:template_detail",
        studio_slug=studio.slug,
        template_id=template.pk,
    )
