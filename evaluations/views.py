from django.contrib import messages
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from instructors.models import Instructor
from studios.models import Studio

from .forms import CriterionResponseForm, StudentEvaluationForm
from .models import (
    EvaluationRating,
    EvaluationTemplate,
    StudentEvaluation,
)


def _admin_access(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


def _teacher_for(user, studio):
    return Instructor.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()


def _can_manage(user, studio):
    return _admin_access(user, studio) or _teacher_for(user, studio) is not None


def _can_view_evaluation(user, evaluation):
    studio = evaluation.studio

    if _admin_access(user, studio):
        return True

    instructor = _teacher_for(user, studio)

    if instructor and (
        evaluation.instructor_id == instructor.id
        or evaluation.class_instance.instructor_id == instructor.id
        or evaluation.class_instance.assistant_instructor_id == instructor.id
    ):
        return True

    guardian = (
        user.guardian_profiles
        .filter(
            family=evaluation.student.family,
            is_active=True,
        )
        .first()
        if hasattr(user, "guardian_profiles")
        else None
    )

    if guardian and evaluation.status == StudentEvaluation.Status.PUBLISHED:
        return True

    if (
        evaluation.student.user_id == user.id
        and evaluation.status == StudentEvaluation.Status.PUBLISHED
    ):
        return True

    return False


@login_required
def evaluation_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    admin = _admin_access(request.user, studio)
    instructor = _teacher_for(request.user, studio)

    if not admin and instructor is None:
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
            "encore_evaluation_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_evaluation_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

    evaluations = (
        StudentEvaluation.objects
        .filter(studio=studio)
        .select_related(
            "student",
            "class_instance",
            "instructor",
            "template",
        )
        .order_by("-evaluation_date")
    )

    if instructor and not admin:
        evaluations = evaluations.filter(
            Q(instructor=instructor)
            | Q(class_instance__instructor=instructor)
            | Q(class_instance__assistant_instructor=instructor)
        ).distinct()

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        evaluations = evaluations.filter(
            Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(class_instance__name__icontains=search)
        )

    if status:
        evaluations = evaluations.filter(status=status)

    return render(
        request,
        "evaluations/evaluation_list.html",
        {
            "studio": studio,
            "role": "administrator" if admin else "teacher",
            "evaluations": evaluations,
            "status_choices": StudentEvaluation.Status.choices,
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
@transaction.atomic
def evaluation_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    admin = _admin_access(request.user, studio)
    instructor = _teacher_for(request.user, studio)

    if not admin and instructor is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    teacher_mode = instructor is not None and not admin

    if request.method == "POST":
        form = StudentEvaluationForm(
            request.POST,
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
        )

        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.studio = studio

            if teacher_mode:
                evaluation.instructor = instructor

            evaluation.full_clean()
            evaluation.save()

            for criterion in evaluation.template.criteria.all():
                EvaluationRating.objects.get_or_create(
                    evaluation=evaluation,
                    criterion=criterion,
                )

            return redirect(
                "evaluations:evaluation_edit",
                studio_slug=studio.slug,
                evaluation_id=evaluation.pk,
            )
    else:
        form = StudentEvaluationForm(
            studio=studio,
            instructor=instructor,
            teacher_mode=teacher_mode,
            initial={
                "evaluation_date": timezone.localdate(),
                "status": StudentEvaluation.Status.DRAFT,
            },
        )

    return render(
        request,
        "evaluations/evaluation_create.html",
        {
            "studio": studio,
            "role": "administrator" if admin else "teacher",
            "form": form,
        },
    )


@login_required
@transaction.atomic
def evaluation_edit(
    request,
    studio_slug,
    evaluation_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    evaluation = get_object_or_404(
        StudentEvaluation.objects.select_related(
            "student",
            "class_instance",
            "instructor",
            "template",
        ),
        pk=evaluation_id,
        studio=studio,
    )

    admin = _admin_access(request.user, studio)
    instructor = _teacher_for(request.user, studio)

    if not admin and (
        instructor is None
        or (
            evaluation.instructor_id != instructor.id
            and evaluation.class_instance.instructor_id != instructor.id
            and evaluation.class_instance.assistant_instructor_id != instructor.id
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    criteria = list(
        evaluation.template.criteria.all()
    )

    existing = {
        row.criterion_id: row
        for row in evaluation.ratings.all()
    }

    response_forms = []

    if request.method == "POST":
        all_valid = True

        for criterion in criteria:
            row = existing.get(criterion.id)

            prefix = f"criterion_{criterion.id}"

            criterion_form = CriterionResponseForm(
                request.POST,
                criterion=criterion,
                prefix=prefix,
                initial={
                    "rating": row.rating if row else "",
                    "comments": row.comments if row else "",
                },
            )

            response_forms.append(
                (criterion, criterion_form)
            )

            if not criterion_form.is_valid():
                all_valid = False

        overall_notes = request.POST.get(
            "overall_notes",
            "",
        )

        goals = request.POST.get(
            "goals",
            "",
        )

        action = request.POST.get(
            "action",
            "save",
        )

        if all_valid:
            for criterion, criterion_form in response_forms:
                rating_row, _ = EvaluationRating.objects.get_or_create(
                    evaluation=evaluation,
                    criterion=criterion,
                )

                rating_row.rating = criterion_form.cleaned_data[
                    "rating"
                ]

                rating_row.comments = criterion_form.cleaned_data[
                    "comments"
                ]

                rating_row.full_clean()
                rating_row.save()

            evaluation.overall_notes = overall_notes
            evaluation.goals = goals

            if action == "publish":
                evaluation.status = StudentEvaluation.Status.PUBLISHED

                if evaluation.published_at is None:
                    evaluation.published_at = timezone.now()
            else:
                evaluation.status = StudentEvaluation.Status.DRAFT

            evaluation.full_clean()
            evaluation.save()

            messages.success(
                request,
                (
                    "Evaluation published."
                    if action == "publish"
                    else "Evaluation draft saved."
                ),
            )

            return redirect(
                "evaluations:evaluation_detail",
                studio_slug=studio.slug,
                evaluation_id=evaluation.pk,
            )
    else:
        for criterion in criteria:
            row = existing.get(criterion.id)

            criterion_form = CriterionResponseForm(
                criterion=criterion,
                prefix=f"criterion_{criterion.id}",
                initial={
                    "rating": row.rating if row else "",
                    "comments": row.comments if row else "",
                },
            )

            response_forms.append(
                (criterion, criterion_form)
            )

    return render(
        request,
        "evaluations/evaluation_edit.html",
        {
            "studio": studio,
            "role": "administrator" if admin else "teacher",
            "evaluation": evaluation,
            "response_forms": response_forms,
        },
    )


@login_required
def evaluation_detail(
    request,
    studio_slug,
    evaluation_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    evaluation = get_object_or_404(
        StudentEvaluation.objects
        .select_related(
            "student",
            "class_instance",
            "instructor",
            "template",
        )
        .prefetch_related(
            "ratings__criterion",
        ),
        pk=evaluation_id,
        studio=studio,
    )

    if not _can_view_evaluation(
        request.user,
        evaluation,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    admin = _admin_access(request.user, studio)
    instructor = _teacher_for(request.user, studio)

    if admin:
        role = "administrator"
    elif instructor:
        role = "teacher"
    elif evaluation.student.user_id == request.user.id:
        role = "student"
    else:
        role = "family"

    return render(
        request,
        "evaluations/evaluation_detail.html",
        {
            "studio": studio,
            "role": role,
            "evaluation": evaluation,
        },
    )
