import json
import re
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from classes.models import Class, Season
from enrollments.models import Enrollment
from instructors.models import Instructor
from resources.models import ClassResource
from studios.models import Studio

from .forms import (
    ChoreographyPlanForm,
    FormationForm,
    LightingCueForm,
    PerformancePrepItemForm,
)
from .models import (
    ChoreographyPlan,
    DrawingBoard,
    Formation,
    FormationTransition,
    DrawingBoardLightingCue,
    DrawingBoardLightingFixture,
    StageLightingTemplate,
    LightingCue,
    PerformancePrepItem,
)


def _workspace_role(request, studio):
    role = request.session.get(
        "encore_workspace_role"
    )

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    if studio_slug != studio.slug:
        return None

    if (
        request.user.is_superuser
        and role == "administrator"
    ):
        return "administrator"

    if role not in {
        "administrator",
        "teacher",
        "family",
        "student",
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=role,
        is_active=True,
    ).exists():
        return role

    return None


def _teacher(request, studio):
    return Instructor.objects.filter(
        studio=studio,
        user=request.user,
        is_active=True,
    ).first()


def _require_staff(request, studio):
    role = _workspace_role(
        request,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return None, None

    instructor = _teacher(
        request,
        studio,
    )

    if (
        role == "teacher"
        and instructor is None
    ):
        return None, None

    return role, instructor


def _teacher_can_access_plan(
    instructor,
    plan,
):
    return (
        plan.class_instance.instructor_id
        == instructor.id
        or
        plan.class_instance.assistant_instructor_id
        == instructor.id
    )


@login_required
def plan_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    plans = (
        ChoreographyPlan.objects
        .filter(studio=studio)
        .select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
        )
        .annotate(
            formation_count=Count(
                "formations",
                distinct=True,
            ),
            lighting_count=Count(
                "lighting_cues",
                distinct=True,
            ),
            prep_count=Count(
                "prep_items",
                distinct=True,
            ),
        )
    )

    if role == "teacher":
        plans = plans.filter(
            Q(
                class_instance__instructor=instructor
            )
            | Q(
                class_instance__assistant_instructor=instructor
            )
        ).distinct()

    # An explicit class filter wins; otherwise use the studio's current season.
    today = timezone.localdate()
    current_season = Season.objects.filter(studio=studio, start_date__lte=today, end_date__gte=today).order_by('-start_date').first()
    selected_class = request.GET.get('class', '').strip()
    selected_season = request.GET.get('season', '').strip()
    selected_teacher = request.GET.get('teacher', '').strip()
    selected_dance = request.GET.get('dance', '').strip()
    # A class-specific entry defaults to that class; filters remain changeable.
    if selected_class.isdigit():
        plans = plans.filter(class_instance_id=int(selected_class))
    if selected_season.isdigit():
        plans = plans.filter(class_instance__season_id=int(selected_season))
    elif selected_season != 'all' and not selected_class and current_season:
        plans = plans.filter(class_instance__season=current_season)
    if selected_teacher.isdigit():
        plans = plans.filter(Q(class_instance__instructor_id=int(selected_teacher)) | Q(class_instance__assistant_instructor_id=int(selected_teacher)))
    if selected_dance.isdigit():
        plans = plans.filter(pk=int(selected_dance))
    search = request.GET.get('q', '').strip()

    if search:
        plans = plans.filter(
            Q(title__icontains=search)
            | Q(song_title__icontains=search)
            | Q(
                class_instance__name__icontains=search
            )
        )

    return render(
        request,
        "performance/plan_list.html",
        {
            "studio": studio,
            "role": role,
            "plans": plans,
            "search": search,
            "seasons": Season.objects.filter(studio=studio).order_by('-start_date'),
            "classes_filter": Class.objects.filter(studio=studio, pk__in=ChoreographyPlan.objects.filter(studio=studio).values('class_instance_id')).order_by('name') if role == 'administrator' else Class.objects.filter(studio=studio).filter(Q(instructor=instructor) | Q(assistant_instructor=instructor)).distinct().order_by('name'),
            "teachers_filter": Instructor.objects.filter(studio=studio).order_by('first_name', 'last_name') if role == 'administrator' else [],
            "dances_filter": ChoreographyPlan.objects.filter(studio=studio).filter(Q(class_instance__instructor=instructor) | Q(class_instance__assistant_instructor=instructor)).order_by('title') if role == 'teacher' else ChoreographyPlan.objects.filter(studio=studio).order_by('title'),
            "selected_class": selected_class,
            "selected_season": selected_season or ('current' if current_season else 'all'),
            "selected_teacher": selected_teacher,
            "selected_dance": selected_dance,
            "current_season": current_season,
        },
    )


@login_required
def plan_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    teacher_mode = role == "teacher"
    requested_class = (request.GET.get("class") or request.POST.get("class_context") or "").strip()
    locked_class = None
    if requested_class.isdigit():
        allowed_classes = Class.objects.filter(studio=studio, is_active=True)
        if teacher_mode:
            allowed_classes = allowed_classes.filter(
                Q(instructor=instructor) | Q(assistant_instructor=instructor)
            )
        locked_class = get_object_or_404(allowed_classes, pk=int(requested_class))

    form = ChoreographyPlanForm(
        request.POST or None,
        studio=studio,
        instructor=instructor,
        teacher_mode=teacher_mode,
    )

    if locked_class is not None:
        form.initial["class_instance"] = locked_class.pk
        form.fields["class_instance"].initial = locked_class
        form.fields["class_instance"].disabled = True
        form.fields["class_instance"].widget.attrs["aria-label"] = "Class (locked)"
        if not form.is_bound:
            form.initial["class_instance"] = locked_class.pk

    if request.method == "POST" and form.is_valid():
        plan = form.save(
            commit=False
        )

        plan.studio = studio

        if instructor is not None:
            plan.created_by = instructor
            plan.updated_by = instructor

        plan.full_clean()
        plan.save()

        messages.success(
            request,
            "Performance plan created.",
        )

        return redirect(
            "performance:plan_detail",
            studio_slug=studio.slug,
            plan_id=plan.pk,
        )

    return render(
        request,
        "performance/plan_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Create Dance",
            "locked_class": locked_class,
        },
    )


@login_required
def plan_detail(
    request,
    studio_slug,
    plan_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
            "class_instance__assistant_instructor",
        ),
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(
            instructor,
            plan,
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    formations = plan.formations.all()
    lighting_cues = plan.lighting_cues.all()
    prep_items = plan.prep_items.all()
    costumes = (
        plan.costumes
        .filter(is_active=True)
        .select_related(
            "vendor",
            "vendor_size_chart",
        )
        .prefetch_related("images")
        .order_by("name")
    )

    # This hub summarizes the resources already connected to this dance.
    # The current plan detail is staff-only; publishing to families needs
    # an explicit approval and access-control pass.
    dance_boards = (
        plan.drawing_boards
        .prefetch_related("formations")
        .order_by("-updated_at")
    )
    from resources.models import ClassResource
    dance_videos = list(
        ClassResource.objects.filter(
            studio=studio, dance=plan, class_instance=plan.class_instance,
            resource_type=ClassResource.ResourceType.VIDEO, is_active=True,
        ).order_by("sort_order", "created_at")
    )
    from urllib.parse import urlparse, parse_qs
    for video in dance_videos:
        parsed = urlparse(video.external_url or "")
        hostname = (parsed.hostname or "").lower()
        video_id = ""
        if hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif hostname in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/").split("/")[0]
        elif hostname in {"youtube.com", "www.youtube.com"} and parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/")[2]
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
            video.embed_url = f"https://www.youtube.com/embed/{video_id}"
            video.thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        else:
            video.embed_url = ""
            video.thumbnail_url = ""

    music_submissions = ClassResource.objects.filter(
        studio=studio, dance=plan, resource_type=ClassResource.ResourceType.MUSIC
    ).select_related("uploaded_by", "reviewed_by").order_by("-created_at")
    featured_board = dance_boards.first()
    board_formation_count = (
        featured_board.formations.count()
        if featured_board is not None else 0
    )

    complete_count = prep_items.filter(
        is_complete=True,
    ).count()

    total_count = prep_items.count()

    progress_percent = (
        round(
            (
                complete_count
                / total_count
            )
            * 100
        )
        if total_count
        else 0
    )

    return_to = request.GET.get("return", "")
    allowed_prefix = reverse('performance:plan_list', kwargs={'studio_slug':studio.slug})
    if not (return_to.startswith(allowed_prefix) and url_has_allowed_host_and_scheme(return_to, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        return_to = allowed_prefix

    return render(
        request,
        "performance/plan_detail.html",
        {
            "return_to": return_to,
            "studio": studio,
            "role": role,
            "plan": plan,
            "formations": formations,
            "lighting_cues": lighting_cues,
            "prep_items": prep_items,
            "costumes": costumes,
            "note_fields": [("choreography_notes", "Choreography Notes", "Steps, movement and timing", plan.choreography_notes), ("teacher_notes", "Internal Notes", "Private to studio staff", plan.teacher_notes), ("performance_notes", "Performance Notes", "Show and stage instructions", plan.performance_notes)],
            "dance_videos": dance_videos,
            "other_resources": ClassResource.objects.filter(studio=studio, dance=plan, is_active=True, resource_type__in=["other", "document"]).order_by("sort_order", "title"),
            "music_submissions": music_submissions,
            "featured_board": featured_board,
            "board_formation_count": board_formation_count,
            "prep_complete_count": complete_count,
            "prep_total_count": total_count,
            "prep_progress_percent": progress_percent,
        },
    )


@login_required
def dance_notes_autosave(request, studio_slug, plan_id):
    """Update a single dance note with studio and assigned-teacher permissions."""
    from django.views.decorators.http import require_POST
    from django.utils import timezone
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role, instructor = _require_staff(request, studio)
    plan = get_object_or_404(ChoreographyPlan, pk=plan_id, studio=studio)
    if role not in ("administrator", "teacher") or (role == "teacher" and not _teacher_can_access_plan(instructor, plan)):
        return JsonResponse({"error": "Permission denied"}, status=403)
    field = request.POST.get("field", "")
    if field not in {"choreography_notes", "teacher_notes", "performance_notes"}:
        return JsonResponse({"error": "Invalid note field"}, status=400)
    content = request.POST.get("content", "")
    if len(content) > 30000:
        return JsonResponse({"error": "Note is too long"}, status=400)
    # The client supplies the version it edited to avoid overwriting another editor.
    expected = request.POST.get("original", "")
    with transaction.atomic():
        current = ChoreographyPlan.objects.select_for_update().get(pk=plan.pk, studio=studio)
        if getattr(current, field) != expected:
            return JsonResponse({"error": "This note changed elsewhere. Copy your text and refresh before saving."}, status=409)
        setattr(current, field, content)
        current.save(update_fields=[field, "updated_at"])
    return JsonResponse({"saved": True, "content": content})


@login_required
def plan_edit(
    request,
    studio_slug,
    plan_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    plan = get_object_or_404(
        ChoreographyPlan,
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(
            instructor,
            plan,
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = ChoreographyPlanForm(
        request.POST or None,
        instance=plan,
        studio=studio,
        instructor=instructor,
        teacher_mode=(
            role == "teacher"
        ),
    )

    if request.method == "POST" and form.is_valid():
        plan = form.save(
            commit=False
        )

        if instructor is not None:
            plan.updated_by = instructor

        plan.full_clean()
        plan.save()

        messages.success(
            request,
            "Performance plan updated.",
        )

        return redirect(
            "performance:plan_detail",
            studio_slug=studio.slug,
            plan_id=plan.pk,
        )

    return render(
        request,
        "performance/plan_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Edit Dance Details",
        },
    )


def _child_form_view(
    request,
    studio_slug,
    plan_id,
    *,
    model,
    form_class,
    page_title,
    success_message,
    child_id=None,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance"
        ),
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(
            instructor,
            plan,
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instance = None

    if child_id is not None:
        instance = get_object_or_404(
            model,
            pk=child_id,
            plan=plan,
        )

    form = form_class(
        request.POST or None,
        instance=instance,
    )

    if request.method == "POST" and form.is_valid():
        child = form.save(
            commit=False
        )

        child.plan = plan
        child.full_clean()
        child.save()

        messages.success(
            request,
            success_message,
        )

        return redirect(
            "performance:plan_detail",
            studio_slug=studio.slug,
            plan_id=plan.pk,
        )

    return render(
        request,
        "performance/child_form.html",
        {
            "studio": studio,
            "role": role,
            "plan": plan,
            "form": form,
            "page_title": page_title,
        },
    )


@login_required
def formation_add(
    request,
    studio_slug,
    plan_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=Formation,
        form_class=FormationForm,
        page_title="Add Formation",
        success_message="Formation added.",
    )


@login_required
def formation_edit(
    request,
    studio_slug,
    plan_id,
    formation_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=Formation,
        form_class=FormationForm,
        page_title="Edit Formation",
        success_message="Formation updated.",
        child_id=formation_id,
    )


@login_required
def lighting_add(
    request,
    studio_slug,
    plan_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=LightingCue,
        form_class=LightingCueForm,
        page_title="Add Lighting Cue",
        success_message="Lighting cue added.",
    )


@login_required
def lighting_edit(
    request,
    studio_slug,
    plan_id,
    cue_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=LightingCue,
        form_class=LightingCueForm,
        page_title="Edit Lighting Cue",
        success_message="Lighting cue updated.",
        child_id=cue_id,
    )


@login_required
def prep_add(
    request,
    studio_slug,
    plan_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=PerformancePrepItem,
        form_class=PerformancePrepItemForm,
        page_title="Add Prep Item",
        success_message="Prep item added.",
    )


@login_required
def prep_edit(
    request,
    studio_slug,
    plan_id,
    prep_id,
):
    return _child_form_view(
        request,
        studio_slug,
        plan_id,
        model=PerformancePrepItem,
        form_class=PerformancePrepItemForm,
        page_title="Edit Prep Item",
        success_message="Prep item updated.",
        child_id=prep_id,
    )




def _teacher_can_access_class(instructor, class_instance):
    return (
        class_instance.instructor_id == instructor.id
        or class_instance.assistant_instructor_id == instructor.id
    )


def _board_access(request, studio, board):
    role, instructor = _require_staff(request, studio)
    if role is None:
        return None, None
    if role == "teacher" and not _teacher_can_access_class(instructor, board.class_instance):
        return None, None
    return role, instructor


def _board_students(board):
    return [
        {
            "id": e.student.id,
            "name": f"{e.student.first_name} {e.student.last_name}",
            "initials": f"{e.student.first_name[:1]}{e.student.last_name[:1]}".upper(),
        }
        for e in Enrollment.objects.filter(
            class_instance=board.class_instance,
            status=Enrollment.Status.ACTIVE,
            student__is_active=True,
        ).select_related("student").order_by("student__last_name", "student__first_name")
    ]


def _default_positions(count):
    if count <= 0:
        return []
    columns = min(8, max(4, count))
    rows = (count + columns - 1) // columns
    result=[]
    for index in range(count):
        row=index//columns; col=index%columns
        row_count=min(columns,count-row*columns)
        x=((col+1)/(row_count+1))*100
        y=66 if rows==1 else 72-((row/max(rows-1,1))*34)
        result.append({"marker":index+1,"x":round(x,3),"y":round(y,3)})
    return result


def _ensure_board_defaults(board):
    if not board.formations.exists():
        Formation.objects.create(
            board=board,
            plan=board.performance_plan,
            name="Formation 1",
            sequence_order=1,
            time_seconds=0,
            positions=[],
        )


def _adopt_legacy_formations(board):
    if not board.performance_plan_id or board.formations.exists():
        return
    for formation in Formation.objects.filter(
        plan=board.performance_plan,
        board__isnull=True,
    ).order_by("time_seconds","sequence_order","id"):
        formation.board=board
        formation.save(update_fields=["board","updated_at"])


@login_required
def drawing_board_for_plan(request, studio_slug, plan_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    role, instructor = _require_staff(request, studio)

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance",
            "music_resource",
        ),
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(instructor, plan)
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    board = (
        DrawingBoard.objects
        .filter(
            studio=studio,
            class_instance=plan.class_instance,
            performance_plan=plan,
        )
        .order_by("-updated_at", "-id")
        .first()
    )

    if board is None:
        board = DrawingBoard.objects.create(
            studio=studio,
            class_instance=plan.class_instance,
            performance_plan=plan,
            title=(
                f"{plan.title} Drawing Board"
                if plan.title
                else f"{plan.class_instance.name} Drawing Board"
            ),
            song_duration_seconds=(
                plan.music_resource.duration_seconds
                if (
                    plan.music_resource_id
                    and plan.music_resource.duration_seconds
                )
                else None
            ),
            created_by=instructor,
            updated_by=instructor,
        )

    _adopt_legacy_formations(board)
    _ensure_board_defaults(board)

    target = reverse(
        "performance:drawing_board_detail",
        kwargs={
            "studio_slug": studio.slug,
            "board_id": board.id,
        },
    )

    requested_formation = request.GET.get("formation", "").strip()
    if requested_formation:
        try:
            formation_id = int(requested_formation)
        except (TypeError, ValueError):
            formation_id = None

        if formation_id and board.formations.filter(pk=formation_id).exists():
            target = f"{target}?formation={formation_id}"

    return redirect(target)


@login_required
def drawing_board_for_class(request, studio_slug, class_id):
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    role,instructor=_require_staff(request,studio)
    if role is None:
        return render(request,"dashboard/access_denied.html",{"studio":studio},status=403)
    class_instance=get_object_or_404(Class,pk=class_id,studio=studio,is_active=True)
    if role=="teacher" and not _teacher_can_access_class(instructor,class_instance):
        return render(request,"dashboard/access_denied.html",{"studio":studio},status=403)
    board=DrawingBoard.objects.filter(
        studio=studio,
        class_instance=class_instance,
    ).order_by(
        "-updated_at",
        "-id",
    ).first()

    if board is None:
        board=DrawingBoard.objects.create(
            studio=studio,
            class_instance=class_instance,
            title=f"{class_instance.name} Drawing Board",
            created_by=instructor,
            updated_by=instructor,
        )

    _adopt_legacy_formations(board)
    _ensure_board_defaults(board)
    return redirect("performance:drawing_board_detail",studio_slug=studio.slug,board_id=board.id)


@login_required
def drawing_board_detail(request, studio_slug, board_id):
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    board=get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__class_type",
            "performance_plan",
            "performance_plan__music_resource",
        ),
        pk=board_id,studio=studio,
    )
    role,instructor=_board_access(request,studio,board)
    if role is None:
        return render(request,"dashboard/access_denied.html",{"studio":studio},status=403)
    _adopt_legacy_formations(board)
    _ensure_board_defaults(board)
    students=_board_students(board)
    active_ids={s["id"] for s in students}
    existing={}
    for item in board.marker_assignments or []:
        if not isinstance(item,dict): continue
        try: n=int(item.get("marker"))
        except (TypeError,ValueError): continue
        sid=item.get("student_id")
        try: sid=int(sid) if sid is not None else None
        except (TypeError,ValueError): sid=None
        if sid not in active_ids: sid=None
        existing[n]={"marker":n,"student_id":sid,"shape":item.get("shape") or "circle","color":item.get("color") or "#2E3CF1"}
    assignments=[existing.get(n,{"marker":n,"student_id":None,"shape":"circle","color":"#2E3CF1"}) for n in range(1,len(students)+1)]
    # IMPORTANT: Rendering the active roster must not destroy historical marker
    # assignments for a student who was withdrawn. Filter only the payload.
    # The pre-withdrawal snapshot is retained separately for audit/reference.
    rows=[]
    for formation in board.formations.order_by("sequence_order","id"):
        positions=[]
        for item in formation.positions or []:
            if not isinstance(item,dict) or "marker" not in item: continue
            try: positions.append({"marker":int(item["marker"]),"x":float(item["x"]),"y":float(item["y"])})
            except (TypeError,ValueError,KeyError): pass
        if not positions: positions=_default_positions(len(students))
        rows.append({
            "id": formation.id,
            "name": formation.name,
            "sequence_order": formation.sequence_order,
            "time_seconds": formation.time_seconds,
            "hold_duration_seconds": formation.hold_duration_seconds,
            "positions": positions,
        })
    dances = list(
        ChoreographyPlan.objects
        .filter(
            studio=studio,
            class_instance=board.class_instance,
        )
        .select_related(
            "music_resource",
        )
        .order_by(
            "title",
            "id",
        )
    )

    songs = list(
        ClassResource.objects
        .filter(
            studio=studio,
            class_instance=board.class_instance,
            resource_type=ClassResource.ResourceType.MUSIC,
            is_active=True,
            approval_status=ClassResource.ApprovalStatus.APPROVED,
        )
        .order_by(
            "title",
            "-created_at",
        )
    )

    dance_rows = [
        {
            "id": dance.id,
            "title": (
                dance.title
                or f"Dance {dance.id}"
            ),
            "song_id": dance.music_resource_id,
            "song_title": (
                dance.music_resource.title
                if dance.music_resource_id
                else ""
            ),
            "song_duration_seconds": (
                dance.music_resource.duration_seconds
                if (
                    dance.music_resource_id
                    and dance.music_resource.duration_seconds
                )
                else 0
            ),
        }
        for dance in dances
    ]

    song_rows = [
        {
            "id": song.id,
            "title": song.title,
            "artist": song.artist,
            "duration_seconds": (
                song.duration_seconds
                or 0
            ),
            "playback_url": (
                song.file.url
                if song.file
                else song.external_url
            ),
            "playback_source": (
                "file"
                if song.file
                else "external"
            ),
        }
        for song in songs
    ]

    formation_ids = [row["id"] for row in rows]

    transition_records = {
        (item.from_formation_id, item.to_formation_id): item
        for item in FormationTransition.objects.filter(
            board=board,
            from_formation_id__in=formation_ids,
            to_formation_id__in=formation_ids,
        )
    }

    transition_rows = []
    for index in range(max(0, len(rows) - 1)):
        from_row = rows[index]
        to_row = rows[index + 1]
        item = transition_records.get((from_row["id"], to_row["id"]))
        transition_rows.append({
            "id": item.id if item else None,
            "from_formation_id": from_row["id"],
            "to_formation_id": to_row["id"],
            "duration_seconds": (
                item.duration_seconds
                if item
                else 3
            ),
            "movements": item.movements if item else [],
        })

    lighting_fixtures = list(
        DrawingBoardLightingFixture.objects
        .filter(board=board)
        .order_by("fixture_number", "id")
    )

    fixture_rows = [
        {
            "id": fixture.id,
            "fixture_number": fixture.fixture_number,
            "label": fixture.label or f"Fixture {fixture.fixture_number}",
            "fixture_type": fixture.fixture_type,
            "fixture_type_label": fixture.get_fixture_type_display(),
            "x": float(fixture.x),
            "y": float(fixture.y),
            "notes": fixture.notes,
        }
        for fixture in lighting_fixtures
    ]

    lighting_cues = list(
        DrawingBoardLightingCue.objects
        .filter(
            board=board,
        )
        .order_by(
            "time_seconds",
            "cue_number",
            "id",
        )
    )

    if not lighting_cues:
        lighting_cues = [
            DrawingBoardLightingCue.objects.create(
                board=board,
                cue_number=1,
                name="Cue 1",
                time_seconds=0,
                fade_seconds=1,
                focus_areas=[],
                created_by=instructor,
                updated_by=instructor,
            )
        ]

    lighting_rows = [
        {
            "id": cue.id,
            "cue_number": cue.cue_number,
            "name": (
                cue.name
                or f"Cue {cue.cue_number}"
            ),
            "time_seconds": cue.time_seconds,
            "fade_seconds": float(
                cue.fade_seconds
                or 0
            ),
            "is_blackout": cue.is_blackout,
            "notes": cue.notes,
            "focus_areas": cue.focus_areas or [],
            "follow_spots": cue.follow_spots or [],
            "fixture_states": cue.fixture_states or [],
        }
        for cue in lighting_cues
    ]

    payload={
        "students":students,
        "assignments":assignments,
        "formations":rows,
        "active_formation_id":(
            next(
                (
                    row["id"]
                    for row in rows
                    if str(row["id"]) == str(request.GET.get("formation", ""))
                ),
                rows[0]["id"] if rows else None,
            )
        ),
        "show_offstage_wings":board.show_offstage_wings,
        "apron_stage_grid": board.apron_stage_grid,
        "stage_drawings": board.stage_drawings or [],
        "song_duration_seconds":board.song_duration_seconds or 0,
        "board_title": board.title,
        "selected_dance_id": board.performance_plan_id,
        "selected_song_id": (
            board.performance_plan.music_resource_id
            if (
                board.performance_plan_id
                and board.performance_plan.music_resource_id
            )
            else None
        ),
        "dances": dance_rows,
        "songs": song_rows,
        "transitions": transition_rows,
        "lighting_cues": lighting_rows,
        "lighting_fixtures": fixture_rows,
        "active_lighting_cue_id": (
            lighting_rows[0]["id"]
            if lighting_rows
            else None
        ),
    }
    accessible_copy_classes = Class.objects.filter(
        studio=studio,
        is_active=True,
    ).exclude(pk=board.class_instance_id)

    if role == "teacher":
        accessible_copy_classes = accessible_copy_classes.filter(
            Q(instructor=instructor)
            | Q(assistant_instructor=instructor)
        ).distinct()

    related_copy_classes = list(
        accessible_copy_classes.filter(
            season_id=board.class_instance.season_id,
            class_type_id=board.class_instance.class_type_id,
            instructor_id=board.class_instance.instructor_id,
            name__iexact=board.class_instance.name,
        )
        .select_related("season", "instructor", "class_type", "default_location")
        .order_by("name", "class_id")
    )

    related_ids = [item.id for item in related_copy_classes]

    other_copy_classes = list(
        accessible_copy_classes.exclude(id__in=related_ids)
        .select_related("season", "instructor", "class_type", "default_location")
        .order_by("-season__start_date", "name", "class_id")[:100]
    )

    return render(request,"performance/formation_board.html",{
        "studio":studio,
        "role":role,
        "board":board,
        "plan":board.performance_plan,
        "board_payload":payload,
        "venue_templates": StageLightingTemplate.objects.filter(studio=studio),
        "related_copy_classes": related_copy_classes,
        "other_copy_classes": other_copy_classes,
    })


@login_required
@transaction.atomic
def drawing_board_copy_to_class(request, studio_slug, board_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    source_board = get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__class_type",
            "class_instance__instructor",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        source_board,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "performance:drawing_board_detail",
            studio_slug=studio.slug,
            board_id=source_board.id,
        )

    destination_id = request.POST.get(
        "destination_class",
        "",
    ).strip()

    new_title = request.POST.get(
        "new_title",
        "",
    ).strip()

    if not destination_id:
        messages.error(
            request,
            "Choose a destination class.",
        )
        return redirect(
            "performance:drawing_board_detail",
            studio_slug=studio.slug,
            board_id=source_board.id,
        )

    destination_queryset = Class.objects.filter(
        studio=studio,
        is_active=True,
    ).exclude(pk=source_board.class_instance_id)

    if role == "teacher":
        destination_queryset = destination_queryset.filter(
            Q(instructor=instructor)
            | Q(assistant_instructor=instructor)
        ).distinct()

    destination_class = get_object_or_404(
        destination_queryset,
        pk=destination_id,
    )

    if not new_title:
        messages.error(
            request,
            "Enter a name for the copied Drawing Board.",
        )
        return redirect(
            "performance:drawing_board_detail",
            studio_slug=studio.slug,
            board_id=source_board.id,
        )

    source_title = (
        source_board.title
        or f"{source_board.class_instance.name} Drawing Board"
    )

    if new_title.casefold() == source_title.casefold():
        messages.error(
            request,
            "The copied Drawing Board must have a different name.",
        )
        return redirect(
            "performance:drawing_board_detail",
            studio_slug=studio.slug,
            board_id=source_board.id,
        )

    copied_assignments = []

    for item in source_board.marker_assignments or []:
        if not isinstance(item, dict):
            continue

        try:
            marker_number = int(item.get("marker"))
        except (TypeError, ValueError):
            continue

        copied_assignments.append(
            {
                "marker": marker_number,
                "student_id": None,
                "shape": item.get("shape") or "circle",
                "color": item.get("color") or "#2E3CF1",
            }
        )

    copied_board = DrawingBoard.objects.create(
        studio=studio,
        class_instance=destination_class,
        performance_plan=None,
        title=new_title[:200],
        song_duration_seconds=source_board.song_duration_seconds,
        marker_assignments=copied_assignments,
        stage_drawings=deepcopy(source_board.stage_drawings or []),
        show_offstage_wings=source_board.show_offstage_wings,
        apron_stage_grid=source_board.apron_stage_grid,
        created_by=instructor,
        updated_by=instructor,
    )

    formation_map = {}

    source_formations = list(
        source_board.formations.order_by(
            "sequence_order",
            "id",
        )
    )

    for source_formation in source_formations:
        copied_formation = Formation.objects.create(
            board=copied_board,
            plan=None,
            name=source_formation.name,
            section_label=source_formation.section_label,
            sequence_order=source_formation.sequence_order,
            time_seconds=source_formation.time_seconds,
            hold_duration_seconds=source_formation.hold_duration_seconds,
            notes=source_formation.notes,
            positions=deepcopy(source_formation.positions or []),
        )

        formation_map[source_formation.id] = copied_formation

    for source_transition in source_board.formation_transitions.select_related(
        "from_formation",
        "to_formation",
    ).all():
        copied_from = formation_map.get(source_transition.from_formation_id)
        copied_to = formation_map.get(source_transition.to_formation_id)

        if not copied_from or not copied_to:
            continue

        FormationTransition.objects.create(
            board=copied_board,
            from_formation=copied_from,
            to_formation=copied_to,
            movements=deepcopy(source_transition.movements or []),
            duration_seconds=source_transition.duration_seconds,
        )

    for source_fixture in source_board.lighting_fixtures.all():
        DrawingBoardLightingFixture.objects.create(
            board=copied_board,
            fixture_number=source_fixture.fixture_number,
            label=source_fixture.label,
            fixture_type=source_fixture.fixture_type,
            x=source_fixture.x,
            y=source_fixture.y,
            notes=source_fixture.notes,
            created_by=instructor,
            updated_by=instructor,
        )

    for source_cue in source_board.lighting_cues.all():
        DrawingBoardLightingCue.objects.create(
            board=copied_board,
            cue_number=source_cue.cue_number,
            name=source_cue.name,
            time_seconds=source_cue.time_seconds,
            fade_seconds=source_cue.fade_seconds,
            is_blackout=source_cue.is_blackout,
            focus_areas=deepcopy(source_cue.focus_areas or []),
            follow_spots=deepcopy(source_cue.follow_spots or []),
            fixture_states=deepcopy(source_cue.fixture_states or []),
            notes=source_cue.notes,
            created_by=instructor,
            updated_by=instructor,
        )

    messages.success(
        request,
        (
            f'Drawing Board copied to "{destination_class.name}". '
            "Student assignments were cleared."
        ),
    )

    return redirect(
        "performance:drawing_board_detail",
        studio_slug=studio.slug,
        board_id=copied_board.id,
    )


@login_required
@transaction.atomic
def drawing_board_detail_save(request, studio_slug, board_id):
    if request.method!="POST": return JsonResponse({"ok":False,"error":"POST required."},status=405)
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    board=get_object_or_404(DrawingBoard.objects.select_for_update().select_related("class_instance"),pk=board_id,studio=studio)
    role,instructor=_board_access(request,studio,board)
    if role is None: return JsonResponse({"ok":False,"error":"Access denied."},status=403)
    try: payload=json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError: return JsonResponse({"ok":False,"error":"Invalid JSON."},status=400)
    students=_board_students(board); marker_count=len(students); active_ids={s["id"] for s in students}
    # Detect a class roster change while an instructor had this board open.
    # Never overwrite an up-to-date board from a stale browser session.
    supplied_roster = payload.get("active_roster_ids")
    if supplied_roster is not None:
        if not isinstance(supplied_roster, list):
            return JsonResponse({"ok": False, "error": "Invalid Drawing Board roster."}, status=400)
        try:
            submitted_roster_ids = {int(student_id) for student_id in supplied_roster}
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Invalid Drawing Board roster."}, status=400)
        if submitted_roster_ids != active_ids or len(supplied_roster) != len(active_ids):
            return JsonResponse({
                "ok": False,
                "roster_changed": True,
                "error": "The class roster changed while this Drawing Board was open. Refresh the page before making further edits; your changes have not been saved.",
            }, status=409)
    submitted=payload.get("assignments",[]); assignments=[]; used=set()
    for n in range(1,marker_count+1):
        item=next((x for x in submitted if isinstance(x,dict) and int(x.get("marker",0) or 0)==n),{})
        sid=item.get("student_id")
        try: sid=int(sid) if sid is not None else None
        except (TypeError,ValueError): sid=None
        if sid not in active_ids or sid in used: sid=None
        if sid is not None: used.add(sid)
        shape=item.get("shape","circle")
        if shape not in {"circle","square","diamond","triangle"}: shape="circle"
        color=str(item.get("color","#2E3CF1")).upper()
        if not re.fullmatch(r"#[0-9A-F]{6}",color): color="#2E3CF1"
        assignments.append({"marker":n,"student_id":sid,"shape":shape,"color":color})
    board.marker_assignments=assignments
    board.show_offstage_wings=bool(payload.get("show_offstage_wings",False))
    board.apron_stage_grid=bool(payload.get("apron_stage_grid",False))

    drawing_payload = payload.get(
        "stage_drawings",
        [],
    )

    if not isinstance(
        drawing_payload,
        list,
    ):
        drawing_payload = []

    clean_drawings = []
    allowed_draw_types = {
        "square",
        "rectangle",
        "circle",
        "half_circle",
        "oval",
        "triangle",
        "line",
        "text",
    }

    for index, drawing in enumerate(
        drawing_payload[:150],
        start=1,
    ):
        if not isinstance(
            drawing,
            dict,
        ):
            continue

        drawing_type = str(
            drawing.get(
                "type",
                "",
            )
        )

        if drawing_type not in allowed_draw_types:
            continue

        def clamp_number(
            value,
            low,
            high,
            default,
        ):
            try:
                value = float(value)
            except (
                TypeError,
                ValueError,
            ):
                value = default

            return round(
                max(
                    low,
                    min(
                        high,
                        value,
                    ),
                ),
                3,
            )

        def safe_color(
            value,
            default,
        ):
            value = str(
                value
                or default
            ).strip().upper()

            if not re.fullmatch(
                r"#[0-9A-F]{6}",
                value,
            ):
                return default

            return value

        row = {
            "id": str(
                drawing.get(
                    "id",
                    f"drawing-{index}",
                )
            )[:80],
            "type": drawing_type,
        }

        if drawing_type == "line":
            row.update(
                {
                    "x1": clamp_number(
                        drawing.get("x1"),
                        0,
                        100,
                        30,
                    ),
                    "y1": clamp_number(
                        drawing.get("y1"),
                        0,
                        100,
                        50,
                    ),
                    "x2": clamp_number(
                        drawing.get("x2"),
                        0,
                        100,
                        70,
                    ),
                    "y2": clamp_number(
                        drawing.get("y2"),
                        0,
                        100,
                        50,
                    ),
                    "cx": clamp_number(
                        drawing.get("cx"),
                        0,
                        100,
                        50,
                    ),
                    "cy": clamp_number(
                        drawing.get("cy"),
                        0,
                        100,
                        50,
                    ),
                    "stroke_enabled": bool(
                        drawing.get(
                            "stroke_enabled",
                            True,
                        )
                    ),
                    "stroke_color": safe_color(
                        drawing.get(
                            "stroke_color"
                        ),
                        "#00024E",
                    ),
                    "stroke_width": clamp_number(
                        drawing.get(
                            "stroke_width"
                        ),
                        .5,
                        10,
                        2,
                    ),
                }
            )
        elif drawing_type == "text":
            font_family = str(
                drawing.get(
                    "font_family",
                    "Arial, sans-serif",
                )
            ).strip()[:120]

            if not font_family:
                font_family = "Arial, sans-serif"

            align = str(
                drawing.get(
                    "align",
                    "left",
                )
            )

            if align not in {
                "left",
                "center",
                "right",
            }:
                align = "left"

            row.update(
                {
                    "x": clamp_number(
                        drawing.get("x"),
                        0,
                        100,
                        50,
                    ),
                    "y": clamp_number(
                        drawing.get("y"),
                        0,
                        100,
                        50,
                    ),
                    "width": clamp_number(
                        drawing.get("width"),
                        4,
                        100,
                        25,
                    ),
                    "height": clamp_number(
                        drawing.get("height"),
                        3,
                        100,
                        10,
                    ),
                    "text": str(
                        drawing.get(
                            "text",
                            "Text",
                        )
                    )[:500],
                    "font_family": font_family,
                    "font_size": int(
                        clamp_number(
                            drawing.get(
                                "font_size"
                            ),
                            10,
                            72,
                            24,
                        )
                    ),
                    "bold": bool(
                        drawing.get(
                            "bold",
                            False,
                        )
                    ),
                    "italic": bool(
                        drawing.get(
                            "italic",
                            False,
                        )
                    ),
                    "underline": bool(
                        drawing.get(
                            "underline",
                            False,
                        )
                    ),
                    "align": align,
                    "color": safe_color(
                        drawing.get(
                            "color"
                        ),
                        "#00024E",
                    ),
                }
            )
        else:
            row.update(
                {
                    "x": clamp_number(
                        drawing.get("x"),
                        0,
                        100,
                        35,
                    ),
                    "y": clamp_number(
                        drawing.get("y"),
                        0,
                        100,
                        35,
                    ),
                    "width": clamp_number(
                        drawing.get("width"),
                        2,
                        100,
                        20,
                    ),
                    "height": clamp_number(
                        drawing.get("height"),
                        2,
                        100,
                        20,
                    ),
                    "fill_enabled": bool(
                        drawing.get(
                            "fill_enabled",
                            True,
                        )
                    ),
                    "fill_color": safe_color(
                        drawing.get(
                            "fill_color"
                        ),
                        "#DCE6FF",
                    ),
                    "stroke_enabled": bool(
                        drawing.get(
                            "stroke_enabled",
                            True,
                        )
                    ),
                    "stroke_color": safe_color(
                        drawing.get(
                            "stroke_color"
                        ),
                        "#00024E",
                    ),
                    "stroke_width": clamp_number(
                        drawing.get(
                            "stroke_width"
                        ),
                        .5,
                        8,
                        2,
                    ),
                }
            )

        clean_drawings.append(
            row
        )

    board.stage_drawings = clean_drawings
    board.title=str(payload.get("title",board.title)).strip()[:200]
    try: duration=int(payload.get("song_duration_seconds",0) or 0)
    except (TypeError,ValueError): duration=0
    board.song_duration_seconds=max(0,duration) or None
    if instructor is not None: board.updated_by=instructor
    board.full_clean(); board.save()
    by_id={f.id:f for f in board.formations.select_for_update().all()}
    for row in payload.get("formations",[]):
        if not isinstance(row,dict): continue
        try: fid=int(row.get("id"))
        except (TypeError,ValueError): continue
        f=by_id.get(fid)
        if f is None: continue
        clean=[]; seen=set()
        for pos in row.get("positions",[]):
            if not isinstance(pos,dict): continue
            try: n=int(pos.get("marker")); x=float(pos.get("x")); y=float(pos.get("y"))
            except (TypeError,ValueError): continue
            if n<1 or n>marker_count or n in seen: continue
            seen.add(n); clean.append({"marker":n,"x":round(max(0,min(100,x)),3),"y":round(max(0,min(100,y)),3)})
        f.positions = clean

        formation_name = str(
            row.get(
                "name",
                f.name,
            )
        ).strip()[:120]

        if formation_name:
            f.name = formation_name

        try:
            hold_duration = int(
                row.get(
                    "hold_duration_seconds",
                    f.hold_duration_seconds,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            hold_duration = f.hold_duration_seconds

        f.hold_duration_seconds = max(
            0,
            min(
                3600,
                hold_duration,
            ),
        )

        f.save(
            update_fields=[
                "name",
                "positions",
                "hold_duration_seconds",
                "updated_at",
            ]
        )
    ordered_formations = list(
        board.formations.select_for_update().order_by(
            "sequence_order",
            "id",
        )
    )
    valid_pairs = {
        (ordered_formations[index].id, ordered_formations[index + 1].id)
        for index in range(max(0, len(ordered_formations) - 1))
    }
    allowed_path_types = {
        "straight",
        "curve",
        "angled",
        "custom",
    }
    submitted_transitions = payload.get("transitions", [])
    if not isinstance(submitted_transitions, list):
        submitted_transitions = []

    for transition_row in submitted_transitions:
        if not isinstance(transition_row, dict):
            continue
        try:
            from_id = int(transition_row.get("from_formation_id"))
            to_id = int(transition_row.get("to_formation_id"))
        except (TypeError, ValueError):
            continue
        pair = (from_id, to_id)
        if pair not in valid_pairs:
            continue

        clean_movements = []
        seen_markers = set()
        movements = transition_row.get("movements", [])
        if not isinstance(movements, list):
            movements = []

        for movement in movements:
            if not isinstance(movement, dict):
                continue
            try:
                marker_number = int(movement.get("marker"))
            except (TypeError, ValueError):
                continue
            if (
                marker_number < 1
                or marker_number > marker_count
                or marker_number in seen_markers
            ):
                continue
            path_type = str(movement.get("path_type", "straight"))
            if path_type not in allowed_path_types:
                path_type = "straight"
            clean_points = []
            points = movement.get("points", [])
            if isinstance(points, list):
                for point in points[:300]:
                    if not isinstance(point, dict):
                        continue
                    try:
                        x = float(point.get("x"))
                        y = float(point.get("y"))
                    except (TypeError, ValueError):
                        continue
                    clean_points.append({
                        "x": round(max(0.0, min(100.0, x)), 3),
                        "y": round(max(0.0, min(100.0, y)), 3),
                    })

            try:
                control_point_count = int(
                    movement.get("control_point_count", len(clean_points) or 1)
                )
            except (TypeError, ValueError):
                control_point_count = 1
            control_point_count = max(1, min(8, control_point_count))

            clean_movements.append({
                "marker": marker_number,
                "path_type": path_type,
                "points": clean_points,
                "control_point_count": control_point_count,
            })
            seen_markers.add(marker_number)

        try:
            transition_duration = int(
                transition_row.get(
                    "duration_seconds",
                    3,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            transition_duration = 3

        transition_duration = max(
            1,
            min(
                600,
                transition_duration,
            ),
        )

        FormationTransition.objects.update_or_create(
            board=board,
            from_formation_id=from_id,
            to_formation_id=to_id,
            defaults={
                "movements": clean_movements,
                "duration_seconds": transition_duration,
            },
        )

    for transition in FormationTransition.objects.filter(board=board):
        if (
            transition.from_formation_id,
            transition.to_formation_id,
        ) not in valid_pairs:
            transition.delete()

    fixture_payload = payload.get(
        "lighting_fixtures",
        [],
    )

    if not isinstance(fixture_payload, list):
        fixture_payload = []

    fixtures_by_id = {
        fixture.id: fixture
        for fixture in DrawingBoardLightingFixture.objects
        .select_for_update()
        .filter(board=board)
    }

    allowed_fixture_types = {
        choice[0]
        for choice in DrawingBoardLightingFixture.FixtureType.choices
    }

    for fixture_row in fixture_payload:
        if not isinstance(fixture_row, dict):
            continue

        try:
            fixture_id = int(fixture_row.get("id"))
        except (TypeError, ValueError):
            continue

        fixture = fixtures_by_id.get(fixture_id)
        if fixture is None:
            continue

        fixture_type = str(
            fixture_row.get("fixture_type", fixture.fixture_type)
        )
        if fixture_type not in allowed_fixture_types:
            fixture_type = fixture.fixture_type

        fixture.fixture_type = fixture_type
        fixture.label = str(
            fixture_row.get("label", fixture.label)
        ).strip()[:100]

        try:
            fixture_x = float(fixture_row.get("x", fixture.x))
            fixture_y = float(fixture_row.get("y", fixture.y))
        except (TypeError, ValueError):
            fixture_x = float(fixture.x)
            fixture_y = float(fixture.y)

        fixture.x = round(max(0, min(100, fixture_x)), 3)
        fixture.y = round(max(0, min(100, fixture_y)), 3)
        fixture.notes = str(
            fixture_row.get("notes", fixture.notes)
        ).strip()

        if instructor is not None:
            fixture.updated_by = instructor

        fixture.save()

    lighting_payload = payload.get(
        "lighting_cues",
        [],
    )

    if not isinstance(
        lighting_payload,
        list,
    ):
        lighting_payload = []

    lighting_by_id = {
        cue.id: cue
        for cue in DrawingBoardLightingCue.objects
        .select_for_update()
        .filter(
            board=board,
        )
    }

    for cue_row in lighting_payload:
        if not isinstance(
            cue_row,
            dict,
        ):
            continue

        try:
            cue_id = int(
                cue_row.get(
                    "id"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        cue = lighting_by_id.get(
            cue_id
        )

        if cue is None:
            continue

        cue.name = str(
            cue_row.get(
                "name",
                cue.name,
            )
        ).strip()[:150]

        try:
            cue_time = int(
                cue_row.get(
                    "time_seconds",
                    cue.time_seconds,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            cue_time = cue.time_seconds

        cue.time_seconds = max(
            0,
            min(
                24 * 60 * 60,
                cue_time,
            ),
        )

        try:
            fade_seconds = float(
                cue_row.get(
                    "fade_seconds",
                    cue.fade_seconds,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            fade_seconds = float(
                cue.fade_seconds
                or 0
            )

        cue.fade_seconds = max(
            0,
            min(
                120,
                fade_seconds,
            ),
        )

        cue.is_blackout = bool(
            cue_row.get(
                "is_blackout",
                False,
            )
        )

        cue.notes = str(
            cue_row.get(
                "notes",
                "",
            )
        ).strip()

        clean_focus_areas = []
        focus_areas = cue_row.get(
            "focus_areas",
            [],
        )

        if not isinstance(
            focus_areas,
            list,
        ):
            focus_areas = []

        used_labels = set()

        for index, area in enumerate(
            focus_areas[:26],
            start=1,
        ):
            if not isinstance(
                area,
                dict,
            ):
                continue

            label = str(
                area.get(
                    "label",
                    "",
                )
            ).strip().upper()[:2]

            if (
                not label
                or label in used_labels
            ):
                label = chr(
                    64 + index
                )

            used_labels.add(
                label
            )

            try:
                x = float(
                    area.get(
                        "x",
                        50,
                    )
                )
                y = float(
                    area.get(
                        "y",
                        50,
                    )
                )
                width = float(
                    area.get(
                        "width",
                        24,
                    )
                )
                height = float(
                    area.get(
                        "height",
                        width,
                    )
                )
                intensity = int(
                    area.get(
                        "intensity",
                        70,
                    )
                )
                softness = int(
                    area.get(
                        "softness",
                        70,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            color = str(
                area.get(
                    "color",
                    "#FFFFFF",
                )
            ).strip().upper()

            if not re.fullmatch(
                r"#[0-9A-F]{6}",
                color,
            ):
                color = "#FFFFFF"

            shape = str(
                area.get(
                    "shape",
                    "circle",
                )
            )

            if shape not in {
                "circle",
                "ellipse",
            }:
                shape = "circle"

            clean_focus_areas.append(
                {
                    "id": str(
                        area.get(
                            "id",
                            f"focus-{cue.id}-{index}",
                        )
                    )[:80],
                    "label": label,
                    "x": round(
                        max(
                            0,
                            min(
                                100,
                                x,
                            ),
                        ),
                        3,
                    ),
                    "y": round(
                        max(
                            0,
                            min(
                                100,
                                y,
                            ),
                        ),
                        3,
                    ),
                    "width": round(
                        max(
                            4,
                            min(
                                100,
                                width,
                            ),
                        ),
                        3,
                    ),
                    "height": round(
                        max(
                            4,
                            min(
                                100,
                                height,
                            ),
                        ),
                        3,
                    ),
                    "color": color,
                    "intensity": max(
                        0,
                        min(
                            100,
                            intensity,
                        ),
                    ),
                    "softness": max(
                        0,
                        min(
                            100,
                            softness,
                        ),
                    ),
                    "shape": shape,
                }
            )

        clean_follow_spots = []
        follow_spots = cue_row.get(
            "follow_spots",
            [],
        )

        if not isinstance(
            follow_spots,
            list,
        ):
            follow_spots = []

        for index, spot in enumerate(
            follow_spots[:8],
            start=1,
        ):
            if not isinstance(
                spot,
                dict,
            ):
                continue

            target_type = str(
                spot.get(
                    "target_type",
                    "marker",
                )
            )

            if target_type not in {
                "marker",
                "position",
            }:
                target_type = "marker"

            try:
                marker = int(
                    spot.get(
                        "marker",
                        1,
                    )
                    or 1
                )
            except (
                TypeError,
                ValueError,
            ):
                marker = 1

            marker = max(
                1,
                min(
                    marker_count,
                    marker,
                ),
            )

            try:
                x = float(
                    spot.get(
                        "x",
                        50,
                    )
                )
                y = float(
                    spot.get(
                        "y",
                        50,
                    )
                )
                size = float(
                    spot.get(
                        "size",
                        18,
                    )
                )
                intensity = int(
                    spot.get(
                        "intensity",
                        80,
                    )
                )
                softness = int(
                    spot.get(
                        "softness",
                        55,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            color = str(
                spot.get(
                    "color",
                    "#FFFFFF",
                )
            ).strip().upper()

            if not re.fullmatch(
                r"#[0-9A-F]{6}",
                color,
            ):
                color = "#FFFFFF"

            clean_follow_spots.append(
                {
                    "id": str(
                        spot.get(
                            "id",
                            f"follow-{cue.id}-{index}",
                        )
                    )[:80],
                    "label": str(
                        spot.get(
                            "label",
                            f"Follow Spot {index}",
                        )
                    ).strip()[:80],
                    "target_type": target_type,
                    "marker": marker,
                    "x": round(
                        max(
                            0,
                            min(
                                100,
                                x,
                            ),
                        ),
                        3,
                    ),
                    "y": round(
                        max(
                            0,
                            min(
                                100,
                                y,
                            ),
                        ),
                        3,
                    ),
                    "size": round(
                        max(
                            4,
                            min(
                                60,
                                size,
                            ),
                        ),
                        3,
                    ),
                    "color": color,
                    "intensity": max(
                        0,
                        min(
                            100,
                            intensity,
                        ),
                    ),
                    "softness": max(
                        0,
                        min(
                            100,
                            softness,
                        ),
                    ),
                }
            )

        clean_fixture_states = []
        fixture_states = cue_row.get(
            "fixture_states",
            [],
        )

        if not isinstance(fixture_states, list):
            fixture_states = []

        valid_fixture_ids = set(fixtures_by_id.keys())
        seen_fixture_ids = set()

        for state in fixture_states:
            if not isinstance(state, dict):
                continue

            try:
                fixture_id = int(state.get("fixture_id"))
            except (TypeError, ValueError):
                continue

            if (
                fixture_id not in valid_fixture_ids
                or fixture_id in seen_fixture_ids
            ):
                continue

            try:
                intensity = int(state.get("intensity", 0) or 0)
                angle_degrees = float(state.get("angle_degrees", 90) or 90)
                beam_size = float(state.get("beam_size", 18) or 18)
            except (TypeError, ValueError):
                continue

            color = str(state.get("color", "#FFFFFF")).strip().upper()
            if not re.fullmatch(r"#[0-9A-F]{6}", color):
                color = "#FFFFFF"

            clean_fixture_states.append(
                {
                    "fixture_id": fixture_id,
                    "is_on": bool(state.get("is_on", False)),
                    "intensity": max(0, min(100, intensity)),
                    "color": color,
                    "angle_degrees": round(angle_degrees % 360, 2),
                    "beam_size": round(max(4, min(60, beam_size)), 2),
                }
            )
            seen_fixture_ids.add(fixture_id)

        cue.focus_areas = (
            []
            if cue.is_blackout
            else clean_focus_areas
        )

        cue.fixture_states = (
            []
            if cue.is_blackout
            else clean_fixture_states
        )

        cue.follow_spots = (
            []
            if cue.is_blackout
            else clean_follow_spots
        )

        if instructor is not None:
            cue.updated_by = (
                instructor
            )

        cue.save()

    return JsonResponse({"ok":True})


@login_required
@transaction.atomic
def drawing_board_detail_formation_add(request, studio_slug, board_id):
    if request.method!="POST": return JsonResponse({"ok":False,"error":"POST required."},status=405)
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    board=get_object_or_404(DrawingBoard.objects.select_related("class_instance","performance_plan"),pk=board_id,studio=studio)
    role,instructor=_board_access(request,studio,board)
    if role is None: return JsonResponse({"ok":False,"error":"Access denied."},status=403)
    try: payload=json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError: return JsonResponse({"ok":False,"error":"Invalid JSON."},status=400)
    try:
        hold_duration = max(
            0,
            min(
                3600,
                int(
                    payload.get(
                        "hold_duration_seconds",
                        8,
                    )
                    or 0
                ),
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Enter a valid formation length.",
            },
            status=400,
        )

    last_legacy_time = (
        board.formations
        .order_by(
            "-time_seconds",
            "-id",
        )
        .values_list(
            "time_seconds",
            flat=True,
        )
        .first()
        or 0
    )

    t = last_legacy_time + 1
    next_number=board.formations.count()+1
    name=str(payload.get("name","")).strip() or f"Formation {next_number}"
    source=None
    if payload.get("copy_from"):
        try: source=board.formations.filter(pk=int(payload["copy_from"])).first()
        except (TypeError,ValueError): source=None
    f = Formation.objects.create(
        board=board,
        plan=board.performance_plan,
        name=name[:150],
        sequence_order=next_number,
        time_seconds=t,
        hold_duration_seconds=hold_duration,
        positions=(
            list(source.positions or [])
            if source
            else []
        ),
    )

    return JsonResponse(
        {
            "ok": True,
            "formation": {
                "id": f.id,
                "name": f.name,
                "time_seconds": f.time_seconds,
                "hold_duration_seconds": f.hold_duration_seconds,
                "positions": f.positions or [],
            },
        }
    )


@login_required
@transaction.atomic
def drawing_board_formation_delete(request, studio_slug, board_id, formation_id):
    if request.method!="POST": return JsonResponse({"ok":False,"error":"POST required."},status=405)
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    board=get_object_or_404(DrawingBoard.objects.select_related("class_instance"),pk=board_id,studio=studio)
    role,instructor=_board_access(request,studio,board)
    if role is None: return JsonResponse({"ok":False,"error":"Access denied."},status=403)
    if board.formations.count()<=1:
        return JsonResponse({"ok":False,"error":"A Drawing Board must have at least one formation."},status=400)
    f=get_object_or_404(Formation,pk=formation_id,board=board); f.delete()
    for i,item in enumerate(board.formations.order_by("sequence_order","id"),start=1):
        if item.sequence_order!=i:
            item.sequence_order=i; item.save(update_fields=["sequence_order"])
    return JsonResponse({"ok":True})


@login_required
@transaction.atomic
def drawing_board_lighting_fixture_add(
    request,
    studio_slug,
    board_id,
):
    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "POST required."},
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    board = get_object_or_404(
        DrawingBoard.objects.select_related("class_instance"),
        pk=board_id,
        studio=studio,
    )
    role, instructor = _board_access(request, studio, board)

    if role is None:
        return JsonResponse(
            {"ok": False, "error": "Access denied."},
            status=403,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse(
            {"ok": False, "error": "Invalid JSON."},
            status=400,
        )

    fixture_type = str(
        payload.get(
            "fixture_type",
            DrawingBoardLightingFixture.FixtureType.PAR,
        )
    )
    allowed_types = {
        choice[0]
        for choice in DrawingBoardLightingFixture.FixtureType.choices
    }

    if fixture_type not in allowed_types:
        return JsonResponse(
            {"ok": False, "error": "Invalid fixture type."},
            status=400,
        )

    try:
        x = float(payload.get("x", 50))
        y = float(payload.get("y", 10))
    except (TypeError, ValueError):
        x = 50
        y = 10

    next_number = (
        DrawingBoardLightingFixture.objects
        .filter(board=board)
        .order_by("-fixture_number")
        .values_list("fixture_number", flat=True)
        .first()
        or 0
    ) + 1

    fixture = DrawingBoardLightingFixture.objects.create(
        board=board,
        fixture_number=next_number,
        label=(
            str(payload.get("label", "")).strip()[:100]
            or f"Fixture {next_number}"
        ),
        fixture_type=fixture_type,
        x=max(0, min(100, x)),
        y=max(0, min(100, y)),
        created_by=instructor,
        updated_by=instructor,
    )

    return JsonResponse(
        {
            "ok": True,
            "fixture": {
                "id": fixture.id,
                "fixture_number": fixture.fixture_number,
                "label": fixture.label,
                "fixture_type": fixture.fixture_type,
                "fixture_type_label": fixture.get_fixture_type_display(),
                "x": float(fixture.x),
                "y": float(fixture.y),
                "notes": fixture.notes,
            },
        }
    )


@login_required
@transaction.atomic
def drawing_board_lighting_fixture_delete(
    request,
    studio_slug,
    board_id,
    fixture_id,
):
    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "POST required."},
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    board = get_object_or_404(
        DrawingBoard,
        pk=board_id,
        studio=studio,
    )
    role, instructor = _board_access(request, studio, board)

    if role is None:
        return JsonResponse(
            {"ok": False, "error": "Access denied."},
            status=403,
        )

    fixture = get_object_or_404(
        DrawingBoardLightingFixture,
        pk=fixture_id,
        board=board,
    )
    fixture.delete()

    remaining = list(
        board.lighting_fixtures.order_by("fixture_number", "id")
    )
    for index, item in enumerate(remaining, start=1):
        if item.fixture_number != index:
            item.fixture_number = index
            item.save(update_fields=["fixture_number"])

    for cue in board.lighting_cues.all():
        clean_states = []
        for state in cue.fixture_states or []:
            if not isinstance(state, dict):
                continue
            try:
                state_fixture_id = int(state.get("fixture_id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if state_fixture_id != fixture_id:
                clean_states.append(state)

        if clean_states != (cue.fixture_states or []):
            cue.fixture_states = clean_states
            cue.save(update_fields=["fixture_states", "updated_at"])

    return JsonResponse({"ok": True})


@login_required
@transaction.atomic
def drawing_board_lighting_cue_add(
    request,
    studio_slug,
    board_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    board = get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        board,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    try:
        payload = json.loads(
            request.body.decode(
                "utf-8"
            )
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    next_number = (
        DrawingBoardLightingCue.objects
        .filter(
            board=board,
        )
        .order_by(
            "-cue_number",
        )
        .values_list(
            "cue_number",
            flat=True,
        )
        .first()
        or 0
    ) + 1

    try:
        time_seconds = max(
            0,
            int(
                payload.get(
                    "time_seconds",
                    0,
                )
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        time_seconds = 0

    try:
        fade_seconds = max(
            0,
            min(
                120,
                float(
                    payload.get(
                        "fade_seconds",
                        1,
                    )
                    or 0
                ),
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        fade_seconds = 1

    cue = DrawingBoardLightingCue.objects.create(
        board=board,
        cue_number=next_number,
        name=(
            str(
                payload.get(
                    "name",
                    "",
                )
            ).strip()[:150]
            or f"Cue {next_number}"
        ),
        time_seconds=time_seconds,
        fade_seconds=fade_seconds,
        is_blackout=bool(
            payload.get(
                "is_blackout",
                False,
            )
        ),
        focus_areas=[],
        created_by=instructor,
        updated_by=instructor,
    )

    return JsonResponse(
        {
            "ok": True,
            "cue": {
                "id": cue.id,
                "cue_number": cue.cue_number,
                "name": cue.name,
                "time_seconds": cue.time_seconds,
                "fade_seconds": float(
                    cue.fade_seconds
                ),
                "is_blackout": cue.is_blackout,
                "notes": cue.notes,
                "focus_areas": [],
                "follow_spots": [],
                "fixture_states": [],
            },
        }
    )


@login_required
@transaction.atomic
def drawing_board_lighting_cue_delete(
    request,
    studio_slug,
    board_id,
    cue_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    board = get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        board,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    if board.lighting_cues.count() <= 1:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "A Drawing Board must keep at least one lighting cue."
                ),
            },
            status=400,
        )

    cue = get_object_or_404(
        DrawingBoardLightingCue,
        pk=cue_id,
        board=board,
    )

    cue.delete()

    remaining = list(
        board.lighting_cues
        .order_by(
            "time_seconds",
            "cue_number",
            "id",
        )
    )

    for index, item in enumerate(
        remaining,
        start=1,
    ):
        if item.cue_number != index:
            item.cue_number = index
            item.save(
                update_fields=[
                    "cue_number",
                ]
            )

    return JsonResponse(
        {
            "ok": True,
        }
    )


@login_required
@transaction.atomic
def drawing_board_information_save(
    request,
    studio_slug,
    board_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    board = get_object_or_404(
        DrawingBoard.objects.select_for_update()
        .select_related(
            "class_instance",
            "performance_plan",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        board,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    try:
        payload = json.loads(
            request.body.decode(
                "utf-8"
            )
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    title = str(
        payload.get(
            "title",
            board.title,
        )
    ).strip()

    board.title = (
        title[:200]
        or f"{board.class_instance.name} Drawing Board"
    )

    dance_id = payload.get(
        "dance_id"
    )

    if dance_id in {
        "",
        None,
        "none",
    }:
        board.performance_plan = None
        dance = None
    else:
        try:
            dance_id = int(
                dance_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Invalid Dance.",
                },
                status=400,
            )

        dance = get_object_or_404(
            ChoreographyPlan,
            pk=dance_id,
            studio=studio,
            class_instance=board.class_instance,
        )

        if (
            role == "teacher"
            and not _teacher_can_access_plan(
                instructor,
                dance,
            )
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Access denied.",
                },
                status=403,
            )

        board.performance_plan = dance

    try:
        duration = int(
            payload.get(
                "song_duration_seconds",
                0,
            )
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        duration = 0

    selected_song_id = payload.get(
        "song_id"
    )

    if dance is not None:
        if selected_song_id in {
            "",
            None,
            "none",
        }:
            dance.music_resource = None
        else:
            try:
                selected_song_id = int(
                    selected_song_id
                )
            except (
                TypeError,
                ValueError,
            ):
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Invalid song.",
                    },
                    status=400,
                )

            song = get_object_or_404(
                ClassResource,
                pk=selected_song_id,
                studio=studio,
                class_instance=board.class_instance,
                resource_type=ClassResource.ResourceType.MUSIC,
                is_active=True,
                approval_status=ClassResource.ApprovalStatus.APPROVED,
            )

            dance.music_resource = song

            if song.duration_seconds:
                duration = (
                    song.duration_seconds
                )

        if instructor is not None:
            dance.updated_by = (
                instructor
            )

        dance.full_clean()
        dance.save()

    board.song_duration_seconds = (
        max(
            0,
            duration,
        )
        or None
    )

    if instructor is not None:
        board.updated_by = (
            instructor
        )

    board.full_clean()
    board.save()

    return JsonResponse(
        {
            "ok": True,
            "board": {
                "id": board.id,
                "title": board.title,
                "dance_id": (
                    board.performance_plan_id
                ),
                "song_id": (
                    board.performance_plan.music_resource_id
                    if (
                        board.performance_plan_id
                        and board.performance_plan.music_resource_id
                    )
                    else None
                ),
                "song_duration_seconds": (
                    board.song_duration_seconds
                    or 0
                ),
            },
        }
    )


@login_required
@transaction.atomic
def drawing_board_dance_add(
    request,
    studio_slug,
    board_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    board = get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        board,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    try:
        payload = json.loads(
            request.body.decode(
                "utf-8"
            )
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    title = str(
        payload.get(
            "title",
            "",
        )
    ).strip()

    if not title:
        return JsonResponse(
            {
                "ok": False,
                "error": "Dance name is required.",
            },
            status=400,
        )

    dance = ChoreographyPlan(
        studio=studio,
        class_instance=board.class_instance,
        title=title[:200],
        song_title=str(
            payload.get(
                "song_title",
                "",
            )
        ).strip()[:200],
        artist=str(
            payload.get(
                "artist",
                "",
            )
        ).strip()[:200],
        choreography_notes=str(
            payload.get(
                "choreography_notes",
                "",
            )
        ).strip(),
        teacher_notes=str(
            payload.get(
                "teacher_notes",
                "",
            )
        ).strip(),
        performance_notes=str(
            payload.get(
                "performance_notes",
                "",
            )
        ).strip(),
        created_by=instructor,
        updated_by=instructor,
    )

    dance.full_clean()
    dance.save()

    board.performance_plan = dance
    board.updated_by = instructor
    board.save(
        update_fields=[
            "performance_plan",
            "updated_by",
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
            "dance": {
                "id": dance.id,
                "title": dance.title,
                "song_id": None,
                "song_title": "",
                "song_duration_seconds": 0,
            },
        }
    )


@login_required
@transaction.atomic
def drawing_board_song_add(
    request,
    studio_slug,
    board_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    board = get_object_or_404(
        DrawingBoard.objects.select_related(
            "class_instance",
            "performance_plan",
        ),
        pk=board_id,
        studio=studio,
    )

    role, instructor = _board_access(
        request,
        studio,
        board,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    if board.performance_plan_id is None:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Select or create a Dance before adding a song."
                ),
            },
            status=400,
        )

    title = str(
        request.POST.get(
            "title",
            "",
        )
    ).strip()

    if not title:
        return JsonResponse(
            {
                "ok": False,
                "error": "Song title is required.",
            },
            status=400,
        )

    uploaded_file = request.FILES.get(
        "file"
    )

    external_url = str(
        request.POST.get(
            "external_url",
            "",
        )
    ).strip()

    if not uploaded_file and not external_url:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Upload a song file or enter an external URL."
                ),
            },
            status=400,
        )

    if uploaded_file and external_url:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Use a file or an external URL, not both."
                ),
            },
            status=400,
        )

    try:
        minutes = max(
            0,
            int(
                request.POST.get(
                    "duration_minutes",
                    0,
                )
                or 0
            ),
        )
        seconds = max(
            0,
            min(
                59,
                int(
                    request.POST.get(
                        "duration_seconds",
                        0,
                    )
                    or 0
                ),
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        minutes = 0
        seconds = 0

    duration_seconds = (
        (minutes * 60)
        + seconds
    )

    song = ClassResource(
        studio=studio,
        class_instance=board.class_instance,
        uploaded_by=instructor,
        resource_type=ClassResource.ResourceType.MUSIC,
        title=title[:200],
        artist=str(
            request.POST.get(
                "artist",
                "",
            )
        ).strip()[:200],
        description=str(
            request.POST.get(
                "description",
                "",
            )
        ).strip(),
        file=uploaded_file,
        external_url=external_url,
        duration_seconds=(
            duration_seconds
            or None
        ),
        visibility=ClassResource.Visibility.STAFF if role == "teacher" else ClassResource.Visibility.ENROLLED,
        is_active=True,
        dance=board.performance_plan,
        approval_status=(ClassResource.ApprovalStatus.PENDING if role == "teacher" else ClassResource.ApprovalStatus.APPROVED),
    )

    song.full_clean()
    song.save()
    if role == "teacher":
        from resources.music_reviews import notify_music_submitted
        transaction.on_commit(lambda pk=song.pk: notify_music_submitted(pk))
        return JsonResponse({"ok": True, "pending_approval": True, "message": "Music submitted for administrator approval."})

    dance = board.performance_plan
    dance.music_resource = song

    if not dance.song_title:
        dance.song_title = song.title

    if (
        not dance.artist
        and song.artist
    ):
        dance.artist = song.artist

    if instructor is not None:
        dance.updated_by = instructor

    dance.full_clean()
    dance.save()

    if song.duration_seconds:
        board.song_duration_seconds = (
            song.duration_seconds
        )

    if instructor is not None:
        board.updated_by = instructor

    board.save()

    return JsonResponse(
        {
            "ok": True,
            "song": {
                "id": song.id,
                "title": song.title,
                "artist": song.artist,
                "duration_seconds": (
                    song.duration_seconds
                    or 0
                ),
                "playback_url": (
                    song.file.url
                    if song.file
                    else song.external_url
                ),
                "playback_source": (
                    "file"
                    if song.file
                    else "external"
                ),
            },
            "dance_id": dance.id,
        }
    )


def _drawing_board_plan(request, studio_slug, plan_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role, instructor = _require_staff(request, studio)
    if role is None:
        return studio, None, None, None
    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance", "class_instance__season", "class_instance__class_type"
        ),
        pk=plan_id,
        studio=studio,
    )
    if role == "teacher" and not _teacher_can_access_plan(instructor, plan):
        return studio, None, None, None
    return studio, role, instructor, plan


def _board_students(plan):
    enrollments = (
        Enrollment.objects.filter(
            class_instance=plan.class_instance,
            status=Enrollment.Status.ACTIVE,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    return [
        {
            "id": e.student.id,
            "name": f"{e.student.first_name} {e.student.last_name}",
            "initials": f"{e.student.first_name[:1]}{e.student.last_name[:1]}".upper(),
        }
        for e in enrollments
    ]


def _marker_count(plan, students):
    count = len(students)
    for item in plan.marker_assignments or []:
        if isinstance(item, dict):
            try:
                count = max(count, int(item.get("marker", 0)))
            except (TypeError, ValueError):
                pass
    for formation in plan.formations.all():
        for item in formation.positions or []:
            if isinstance(item, dict):
                try:
                    count = max(count, int(item.get("marker", 0)))
                except (TypeError, ValueError):
                    pass
    return count


def _default_marker_positions(marker_count):
    if marker_count <= 0:
        return []
    columns = min(8, max(4, marker_count))
    rows = (marker_count + columns - 1) // columns
    positions = []
    for index in range(marker_count):
        row = index // columns
        column = index % columns
        row_count = min(columns, marker_count - (row * columns))
        x = ((column + 1) / (row_count + 1)) * 100
        y = 66 if rows == 1 else 72 - ((row / max(rows - 1, 1)) * 34)
        positions.append({"marker": index + 1, "x": round(x, 3), "y": round(y, 3)})
    return positions


def _normalize_marker_assignments(assignments, active_student_ids, marker_count):
    if not isinstance(assignments, list):
        assignments = []
    allowed_shapes = {"circle", "square", "diamond", "triangle"}
    seen_markers = set()
    seen_students = set()
    clean = []
    for item in assignments:
        if not isinstance(item, dict):
            continue
        try:
            marker_number = int(item.get("marker"))
        except (TypeError, ValueError):
            continue
        if marker_number < 1 or marker_number > marker_count or marker_number in seen_markers:
            continue
        student_id = item.get("student_id")
        if student_id in {"", None}:
            student_id = None
        else:
            try:
                student_id = int(student_id)
            except (TypeError, ValueError):
                student_id = None
            if student_id not in active_student_ids or student_id in seen_students:
                student_id = None
        shape = str(item.get("shape", "circle"))
        if shape not in allowed_shapes:
            shape = "circle"
        color = str(item.get("color", "#2E3CF1")).strip()
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            color = "#2E3CF1"
        clean.append({
            "marker": marker_number,
            "student_id": student_id,
            "shape": shape,
            "color": color.upper(),
        })
        seen_markers.add(marker_number)
        if student_id is not None:
            seen_students.add(student_id)
    for marker_number in range(1, marker_count + 1):
        if marker_number not in seen_markers:
            clean.append({
                "marker": marker_number,
                "student_id": None,
                "shape": "circle",
                "color": "#2E3CF1",
            })
    clean.sort(key=lambda item: item["marker"])
    return clean


def _normalize_marker_positions(positions, marker_count):
    if not isinstance(positions, list):
        return []
    clean = []
    seen = set()
    for item in positions:
        if not isinstance(item, dict):
            continue
        try:
            marker_number = int(item.get("marker"))
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            continue
        if marker_number < 1 or marker_number > marker_count or marker_number in seen:
            continue
        clean.append({
            "marker": marker_number,
            "x": round(max(0.0, min(100.0, x)), 3),
            "y": round(max(0.0, min(100.0, y)), 3),
        })
        seen.add(marker_number)
    return clean


@login_required
def drawing_board(request, studio_slug, plan_id):
    return drawing_board_for_plan(
        request,
        studio_slug,
        plan_id,
    )


@login_required
@transaction.atomic
def drawing_board_save(request, studio_slug, plan_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    studio, role, instructor, plan = _drawing_board_plan(request, studio_slug, plan_id)
    if role is None or plan is None:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)
    students = _board_students(plan)
    try:
        requested_count = int(payload.get("marker_count", len(students)) or 0)
    except (TypeError, ValueError):
        requested_count = len(students)
    marker_count = max(len(students), requested_count)
    active_student_ids = {student["id"] for student in students}
    plan.marker_assignments = _normalize_marker_assignments(
        payload.get("assignments", []), active_student_ids, marker_count
    )
    plan.show_offstage_wings = bool(payload.get("show_offstage_wings", False))
    title = str(payload.get("title", plan.title)).strip()[:200]
    plan.title = title
    try:
        duration = int(payload.get("song_duration_seconds", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    plan.song_duration_seconds = max(0, duration) or None
    if instructor is not None:
        plan.updated_by = instructor
    plan.full_clean()
    plan.save()
    formations_payload = payload.get("formations", [])
    if not isinstance(formations_payload, list):
        formations_payload = []
    valid = {
        f.id: f for f in Formation.objects.select_for_update().filter(plan=plan)
    }
    saved = 0
    for item in formations_payload:
        if not isinstance(item, dict):
            continue
        try:
            formation_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        formation = valid.get(formation_id)
        if formation is None:
            continue
        formation.positions = _normalize_marker_positions(
            item.get("positions", []), marker_count
        )
        formation.save(update_fields=["positions", "updated_at"])
        saved += 1
    return JsonResponse({"ok": True, "saved_formations": saved})


@login_required
@transaction.atomic
def drawing_board_formation_add(request, studio_slug, plan_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    studio, role, instructor, plan = _drawing_board_plan(request, studio_slug, plan_id)
    if role is None or plan is None:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)
    try:
        time_seconds = max(0, int(payload.get("time_seconds", 0)))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Enter a valid formation time."}, status=400)
    if plan.song_duration_seconds is not None and time_seconds > plan.song_duration_seconds:
        return JsonResponse({
            "ok": False,
            "error": "Formation time cannot be after the end of the song.",
        }, status=400)
    if plan.formations.filter(time_seconds=time_seconds).exists():
        return JsonResponse({
            "ok": False,
            "error": "A formation already exists at that song time.",
        }, status=400)
    name = str(payload.get("name", "")).strip()[:150]
    if not name:
        name = f"Formation {plan.formations.count() + 1}"
    positions = []
    source_id = payload.get("copy_from")
    if source_id:
        try:
            source = plan.formations.filter(pk=int(source_id)).first()
        except (TypeError, ValueError):
            source = None
        if source is not None:
            positions = source.positions or []
    formation = Formation.objects.create(
        plan=plan,
        name=name,
        sequence_order=plan.formations.count() + 1,
        time_seconds=time_seconds,
        positions=positions,
    )
    return JsonResponse({
        "ok": True,
        "formation": {
            "id": formation.id,
            "name": formation.name,
            "section_label": formation.section_label,
            "time_seconds": formation.time_seconds,
            "time_display": formation.time_display,
            "positions": formation.positions or [],
        },
    })


@login_required
def formation_board(request, studio_slug, plan_id, formation_id):
    studio, role, instructor, plan = _drawing_board_plan(request, studio_slug, plan_id)
    if role is None or plan is None:
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    get_object_or_404(Formation, pk=formation_id, plan=plan)
    url = reverse(
        "performance:drawing_board",
        kwargs={"studio_slug": studio.slug, "plan_id": plan.id},
    )
    return redirect(f"{url}?formation={formation_id}")


@login_required
@transaction.atomic
def formation_board_save(
    request,
    studio_slug,
    plan_id,
    formation_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "POST required.",
            },
            status=405,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
        request,
        studio,
    )

    if role is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance"
        ),
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(
            instructor,
            plan,
        )
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Access denied.",
            },
            status=403,
        )

    formation = get_object_or_404(
        Formation.objects.select_for_update(),
        pk=formation_id,
        plan=plan,
    )

    try:
        payload = json.loads(
            request.body.decode("utf-8")
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    positions = payload.get(
        "positions",
        [],
    )

    if not isinstance(
        positions,
        list,
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Positions must be a list.",
            },
            status=400,
        )

    active_student_ids = set(
        Enrollment.objects
        .filter(
            class_instance=plan.class_instance,
            status=Enrollment.Status.ACTIVE,
            student__is_active=True,
        )
        .values_list(
            "student_id",
            flat=True,
        )
    )

    clean_positions = []

    for item in positions:
        if not isinstance(item, dict):
            continue

        try:
            student_id = int(
                item.get("student_id")
            )

            x = float(
                item.get("x")
            )

            y = float(
                item.get("y")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if student_id not in active_student_ids:
            continue

        x = max(
            0.0,
            min(100.0, x),
        )

        y = max(
            0.0,
            min(100.0, y),
        )

        clean_positions.append(
            {
                "student_id": student_id,
                "x": round(x, 3),
                "y": round(y, 3),
            }
        )

    formation.positions = clean_positions
    formation.save(
        update_fields=[
            "positions",
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
            "saved": len(
                clean_positions
            ),
        }
    )


@login_required
@transaction.atomic
def formation_duplicate(
    request,
    studio_slug,
    plan_id,
    formation_id,
):
    if request.method != "POST":
        return redirect(
            "performance:plan_detail",
            studio_slug=studio_slug,
            plan_id=plan_id,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_staff(
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

    plan = get_object_or_404(
        ChoreographyPlan.objects.select_related(
            "class_instance"
        ),
        pk=plan_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_access_plan(
            instructor,
            plan,
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    formation = get_object_or_404(
        Formation,
        pk=formation_id,
        plan=plan,
    )

    next_order = (
        plan.formations
        .order_by(
            "-sequence_order",
            "-id",
        )
        .values_list(
            "sequence_order",
            flat=True,
        )
        .first()
        or 0
    ) + 1

    duplicate = Formation.objects.create(
        plan=plan,
        name=f"{formation.name} Copy",
        section_label=formation.section_label,
        sequence_order=next_order,
        notes=formation.notes,
        positions=formation.positions,
    )

    messages.success(
        request,
        "Formation duplicated.",
    )

    return redirect(
        "performance:formation_board",
        studio_slug=studio.slug,
        plan_id=plan.pk,
        formation_id=duplicate.pk,
    )


@login_required
def dance_choreography_viewer(request, studio_slug, plan_id):
    """Read-only choreography presentation with independent role and enrollment checks."""
    from django.http import Http404
    from django.urls import reverse
    from families.models import Guardian
    from students.models import Student
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _workspace_role(request, studio)
    dance = get_object_or_404(ChoreographyPlan.objects.select_related('class_instance','music_resource'), studio=studio, pk=plan_id)
    eligible_ids = set(Enrollment.objects.filter(class_instance=dance.class_instance, status=Enrollment.Status.ACTIVE, student__is_active=True).values_list('student_id', flat=True))
    own_ids = set()
    if role == 'administrator':
        pass
    elif role == 'teacher':
        instructor = _teacher(request, studio)
        if not instructor or not _teacher_can_access_plan(instructor,dance):
            raise Http404()
    elif role == 'family':
        family_ids = Guardian.objects.filter(family__studio=studio, user=request.user, is_active=True).values_list('family_id',flat=True)
        own_ids = set(Student.objects.filter(studio=studio, family_id__in=family_ids, pk__in=eligible_ids).values_list('id',flat=True))
        if not own_ids: raise Http404()
    elif role == 'student':
        own_ids = set(Student.objects.filter(studio=studio, user=request.user, pk__in=eligible_ids).values_list('id',flat=True))
        if not own_ids: raise Http404()
    else:
        raise Http404()
    board = dance.drawing_boards.order_by('-updated_at').first()
    if not board:
        return render(request,'performance/dance_choreography_viewer.html',{'studio':studio,'dance':dance,'board':None})
    from resources.models import ClassResource
    students = list(Student.objects.filter(studio=studio, pk__in=eligible_ids).order_by('last_name','first_name'))
    assignments = {int(x['marker']):x.get('student_id') for x in (board.marker_assignments or []) if isinstance(x,dict) and str(x.get('marker','')).isdigit()}
    marker_names = {s.pk:f'{s.first_name} {s.last_name}' for s in students}
    items = []
    timeline = 0
    board_formations = list(board.formations.order_by('sequence_order','id'))
    transitions = {(tr.from_formation_id, tr.to_formation_id): tr.duration_seconds for tr in board.formation_transitions.all()}
    for index, formation in enumerate(board_formations):
        coords=[]
        for pos in formation.positions or []:
            try:
                marker=int(pos['marker']); x=float(pos['x']); y=float(pos['y'])
            except (ValueError,TypeError,KeyError):continue
            if not (0 <= x <= 100 and 0 <= y <= 100):continue
            student_id=assignments.get(marker)
            coords.append({'marker':marker,'x':x,'y':y,'own':student_id in own_ids,'name':marker_names.get(student_id,'Dancer')})
        start = max(timeline, formation.time_seconds)
        next_formation = board_formations[index + 1] if index + 1 < len(board_formations) else None
        transition_seconds = transitions.get((formation.pk, next_formation.pk), 3) if next_formation else 0
        items.append({'name':formation.name,'time':start,'hold':formation.hold_duration_seconds,'transition':transition_seconds,'positions':coords})
        timeline = start + formation.hold_duration_seconds + transition_seconds
    lighting = [{'time':cue.time_seconds,'name':cue.name,'blackout':cue.is_blackout} for cue in board.lighting_cues.order_by('time_seconds','cue_number')]
    song = dance.music_resource
    music_url=''
    if song and song.is_active and song.approval_status==ClassResource.ApprovalStatus.APPROVED and song.visibility==ClassResource.Visibility.ENROLLED and song.file:
        music_url=reverse('resources:music_file',kwargs={'studio_slug':studio.slug,'resource_id':song.pk})
    return render(request,'performance/dance_choreography_viewer.html', {'studio':studio,'dance':dance,'board':board,'formations_json':items,'lighting_json':lighting,'music_url':music_url,'family_mode':role in ('family','student'),'own_available':bool(own_ids)})


@login_required
@transaction.atomic
def drawing_board_stage_template_save(request, studio_slug, board_id):
    """Authorized studio staff save reusable stage drawings (including labels) and lighting."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    board = get_object_or_404(DrawingBoard, pk=board_id, studio=studio)
    role, _ = _board_access(request, studio, board)
    if role not in {"administrator", "teacher"}:
        return JsonResponse({"ok": False, "error": "Instructor or administrator access required."}, status=403)
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 160:
        return JsonResponse({"ok": False, "error": "Enter a template name (up to 160 characters)."}, status=400)
    if StageLightingTemplate.objects.filter(studio=studio, name=name).exists():
        return JsonResponse({"ok": False, "error": "A venue template with this name already exists."}, status=409)
    fixtures = list(board.lighting_fixtures.order_by("fixture_number", "id").values(
        "fixture_number", "label", "fixture_type", "x", "y", "notes"))
    cues = list(board.lighting_cues.order_by("time_seconds", "cue_number").values(
        "cue_number", "name", "time_seconds", "fade_seconds", "is_blackout", "focus_areas", "follow_spots", "fixture_states", "notes"))
    template = StageLightingTemplate.objects.create(
        studio=studio, name=name, stage_drawings=deepcopy(board.stage_drawings or []),
        show_offstage_wings=board.show_offstage_wings, apron_stage_grid=board.apron_stage_grid,
        fixtures=json.loads(json.dumps(fixtures, default=str)), cues=json.loads(json.dumps(cues, default=str)),
    )
    return JsonResponse({"ok": True, "id": template.id, "name": template.name})


@login_required
@transaction.atomic
def drawing_board_stage_template_apply(request, studio_slug, board_id):
    """Replace only the requested board layers. Choreography is never touched."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    board = get_object_or_404(DrawingBoard.objects.select_for_update().select_related("class_instance"), pk=board_id, studio=studio)
    role, instructor = _board_access(request, studio, board)
    if role not in {"administrator", "teacher"}:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)
    try:
        payload = json.loads(request.body)
        template_id = int(payload.get("template_id"))
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Select a valid template."}, status=400)
    stage = payload.get("stage") is True
    lighting = payload.get("lighting") is True
    if not (stage or lighting):
        return JsonResponse({"ok": False, "error": "Choose Stage, Lighting, or both."}, status=400)
    template = get_object_or_404(StageLightingTemplate, pk=template_id, studio=studio)
    # An undo snapshot contains only the replaced layers; never alter choreography.
    snapshot = {}
    if stage:
        snapshot["stage_drawings"] = deepcopy(board.stage_drawings or [])
        snapshot["show_offstage_wings"] = board.show_offstage_wings
        snapshot["apron_stage_grid"] = board.apron_stage_grid
        board.stage_drawings = deepcopy(template.stage_drawings or [])
        board.show_offstage_wings = template.show_offstage_wings
        board.apron_stage_grid = template.apron_stage_grid
        board.save(update_fields=["stage_drawings", "show_offstage_wings", "apron_stage_grid", "updated_at"])
    if lighting:
        snapshot["fixtures"] = json.loads(json.dumps(list(board.lighting_fixtures.values("fixture_number", "label", "fixture_type", "x", "y", "notes")), default=str))
        snapshot["cues"] = json.loads(json.dumps(list(board.lighting_cues.values("cue_number", "name", "time_seconds", "fade_seconds", "is_blackout", "focus_areas", "follow_spots", "fixture_states", "notes")), default=str))
        board.lighting_cues.all().delete()
        board.lighting_fixtures.all().delete()
        for fixture in template.fixtures or []:
            DrawingBoardLightingFixture.objects.create(board=board, fixture_number=fixture["fixture_number"],
                label=fixture.get("label", ""), fixture_type=fixture.get("fixture_type", "par"),
                x=fixture.get("x", 50), y=fixture.get("y", 10), notes=fixture.get("notes", ""),
                created_by=instructor, updated_by=instructor)
        for cue in template.cues or []:
            DrawingBoardLightingCue.objects.create(board=board, cue_number=cue["cue_number"],
                name=cue.get("name", ""), time_seconds=cue.get("time_seconds", 0),
                fade_seconds=cue.get("fade_seconds", 1), is_blackout=cue.get("is_blackout", False),
                focus_areas=deepcopy(cue.get("focus_areas") or []), follow_spots=deepcopy(cue.get("follow_spots") or []),
                fixture_states=deepcopy(cue.get("fixture_states") or []), notes=cue.get("notes", ""),
                created_by=instructor, updated_by=instructor)
    request.session[f"board_template_undo_{board.pk}"] = snapshot
    return JsonResponse({"ok": True, "message": "Template applied. Reloading board."})


@login_required
@transaction.atomic
def drawing_board_stage_template_undo(request, studio_slug, board_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    board = get_object_or_404(DrawingBoard.objects.select_for_update().select_related("class_instance"), pk=board_id, studio=studio)
    role, instructor = _board_access(request, studio, board)
    if role not in {"administrator", "teacher"}:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)
    key = f"board_template_undo_{board.pk}"
    snapshot = request.session.get(key)
    if not isinstance(snapshot, dict) or not snapshot:
        return JsonResponse({"ok": False, "error": "No template change is available to undo."}, status=400)
    if "stage_drawings" in snapshot:
        board.stage_drawings = snapshot["stage_drawings"]
        board.show_offstage_wings = snapshot["show_offstage_wings"]
        board.apron_stage_grid = snapshot["apron_stage_grid"]
        board.save(update_fields=["stage_drawings", "show_offstage_wings", "apron_stage_grid", "updated_at"])
    if "fixtures" in snapshot:
        board.lighting_cues.all().delete()
        board.lighting_fixtures.all().delete()
        for fixture in snapshot["fixtures"]:
            DrawingBoardLightingFixture.objects.create(board=board, fixture_number=fixture["fixture_number"],
                label=fixture.get("label", ""), fixture_type=fixture.get("fixture_type", "par"),
                x=fixture.get("x", 50), y=fixture.get("y", 10), notes=fixture.get("notes", ""),
                created_by=instructor, updated_by=instructor)
        for cue in snapshot.get("cues", []):
            DrawingBoardLightingCue.objects.create(board=board, cue_number=cue["cue_number"],
                name=cue.get("name", ""), time_seconds=cue.get("time_seconds", 0),
                fade_seconds=cue.get("fade_seconds", 1), is_blackout=cue.get("is_blackout", False),
                focus_areas=deepcopy(cue.get("focus_areas") or []), follow_spots=deepcopy(cue.get("follow_spots") or []),
                fixture_states=deepcopy(cue.get("fixture_states") or []), notes=cue.get("notes", ""),
                created_by=instructor, updated_by=instructor)
    del request.session[key]
    return JsonResponse({"ok": True})
