from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from classes.models import Class
from families.models import Guardian
from instructors.models import Instructor
from studios.models import Studio
from dashboard.parent_portal import parent_portal_context

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
            approval_status=ClassResource.ApprovalStatus.APPROVED,
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
            approval_status=ClassResource.ApprovalStatus.APPROVED,
            class_instance__is_active=True,
            class_instance__enrollments__student__user=user,
            class_instance__enrollments__student__is_active=True,
            class_instance__enrollments__status="active",
        )
        .distinct()
    )


def _manageable_classes(role, instructor, studio):
    classes = Class.objects.filter(
        studio=studio,
        is_active=True,
    )

    if role == "teacher":
        if instructor is None:
            return Class.objects.none()

        classes = classes.filter(
            Q(instructor=instructor)
            | Q(assistant_instructor=instructor)
        ).distinct()

    return classes


def _music_for_reuse(role, instructor, studio, target_class):
    music = (
        ClassResource.objects
        .filter(
            studio=studio,
            resource_type=ClassResource.ResourceType.MUSIC,
            approval_status=ClassResource.ApprovalStatus.APPROVED,
            is_active=True,
            class_instance__is_active=True,
            class_instance__season_id=target_class.season_id,
        )
        .exclude(class_instance=target_class)
        .select_related(
            "class_instance",
            "class_instance__season",
            "uploaded_by",
        )
    )

    if role == "teacher":
        music = music.filter(
            Q(class_instance__instructor=instructor)
            | Q(class_instance__assistant_instructor=instructor)
        ).distinct()

    return music.order_by(
        "title",
        "class_instance__name",
        "-created_at",
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

    target_class = None

    if class_id and role in {
        "administrator",
        "teacher",
    }:
        manageable = _manageable_classes(
            role,
            instructor,
            studio,
        )

        try:
            target_class = manageable.filter(
                pk=int(class_id)
            ).first()
        except (TypeError, ValueError):
            target_class = None

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

    context = {
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
        "target_class": target_class,
        "reuse_music_count": (
            _music_for_reuse(
                role,
                instructor,
                studio,
                target_class,
            ).count()
            if target_class is not None
            else 0
        ),
    }

    template_name = "resources/resource_list.html"

    if role in ("family", "student"):
        from performance.models import ChoreographyPlan
        if role == "family":
            family_ids = Guardian.objects.filter(family__studio=studio, user=request.user, is_active=True).values_list("family_id", flat=True)
            dance_class_ids = Class.objects.filter(studio=studio, enrollments__student__family_id__in=family_ids, enrollments__status="active", enrollments__student__is_active=True).values_list("id", flat=True)
        else:
            dance_class_ids = Class.objects.filter(studio=studio, enrollments__student__user=request.user, enrollments__status="active", enrollments__student__is_active=True).values_list("id", flat=True)
        context["viewable_dances"] = ChoreographyPlan.objects.filter(studio=studio, class_instance_id__in=dance_class_ids).select_related("class_instance").distinct().order_by("class_instance__name", "title")

    if role == "family":
        context.update(
            parent_portal_context(
                request,
                studio,
                section="resources",
            )
        )
        template_name = "resources/parent_resource_list.html"

    return render(
        request,
        template_name,
        context,
    )


@login_required
def resource_reuse_music(request, studio_slug):
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

    if role == "teacher" and instructor is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    class_id = (
        request.POST.get("class")
        if request.method == "POST"
        else request.GET.get("class")
    )
    class_id = str(class_id or "").strip()

    manageable_classes = (
        _manageable_classes(
            role,
            instructor,
            studio,
        )
        .select_related(
            "season",
            "instructor",
            "class_type",
        )
        .order_by(
            "-season__start_date",
            "name",
            "class_id",
        )
    )

    target_class = None

    if class_id:
        try:
            target_class = manageable_classes.filter(
                pk=int(class_id)
            ).first()
        except (TypeError, ValueError):
            target_class = None

    if request.method == "POST":
        if target_class is None:
            messages.error(
                request,
                "Choose a destination class.",
            )

        source_id = request.POST.get(
            "source_resource",
            "",
        ).strip()

        source_music = None

        if target_class is not None and source_id:
            try:
                source_music = _music_for_reuse(
                    role,
                    instructor,
                    studio,
                    target_class,
                ).filter(
                    pk=int(source_id)
                ).first()
            except (TypeError, ValueError):
                source_music = None

        if target_class is not None and source_music is None:
            messages.error(
                request,
                "Choose music to reuse.",
            )

        if target_class is not None and source_music is not None:
            duplicate_query = ClassResource.objects.filter(
                studio=studio,
                class_instance=target_class,
                resource_type=ClassResource.ResourceType.MUSIC,
                is_active=True,
                title__iexact=source_music.title,
            )

            if source_music.file:
                duplicate_query = duplicate_query.filter(
                    file=source_music.file.name
                )
            elif source_music.external_url:
                duplicate_query = duplicate_query.filter(
                    external_url=source_music.external_url
                )

            if duplicate_query.exists():
                messages.info(
                    request,
                    "That music is already attached to this class.",
                )

                return redirect(
                    f"{reverse('resources:resource_list', kwargs={'studio_slug': studio.slug})}?class={target_class.id}"
                )

            reused = ClassResource(
                studio=studio,
                class_instance=target_class,
                uploaded_by=instructor,
                resource_type=ClassResource.ResourceType.MUSIC,
                title=source_music.title,
                artist=source_music.artist,
                duration_seconds=source_music.duration_seconds,
                description=source_music.description,
                external_url=source_music.external_url,
                visibility=source_music.visibility,
                is_active=True,
                sort_order=source_music.sort_order,
            )

            if source_music.file:
                reused.file.name = source_music.file.name

            reused.full_clean()
            reused.save()

            messages.success(
                request,
                (
                    f'"{source_music.title}" is now available in '
                    f'"{target_class.name}" without uploading another file.'
                ),
            )

            return redirect(
                f"{reverse('resources:resource_list', kwargs={'studio_slug': studio.slug})}?class={target_class.id}"
            )

    reusable_music = (
        _music_for_reuse(
            role,
            instructor,
            studio,
            target_class,
        )
        if target_class is not None
        else ClassResource.objects.none()
    )

    return render(
        request,
        "resources/resource_reuse_music.html",
        {
            "studio": studio,
            "role": role,
            "target_class": target_class,
            "manageable_classes": manageable_classes,
            "reusable_music": reusable_music,
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

    from performance.models import ChoreographyPlan
    dance = None
    if request.GET.get("dance"):
        dance = get_object_or_404(ChoreographyPlan, pk=request.GET["dance"], studio=studio)
        if not _manageable_classes(role, instructor, studio).filter(pk=dance.class_instance_id).exists():
            return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    # Video creation has its own manager. Keep the class filter on return.
    selected_class_id = str(dance.class_instance_id) if dance else request.GET.get("class", "").strip()
    valid_classes = _manageable_classes(role, instructor, studio)
    if selected_class_id and not valid_classes.filter(pk=selected_class_id).exists():
        selected_class_id = ""
    from urllib.parse import urlencode
    video_return_url = reverse("resources:video_manager", kwargs={"studio_slug": studio.slug})
    if selected_class_id:
        video_return_url += "?" + urlencode({"class": selected_class_id})

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
            if dance is not None:
                resource.class_instance = dance.class_instance
                resource.dance = dance

            if instructor is not None:
                resource.uploaded_by = instructor

            # Staff-submitted dance music is private until reviewed.
            if resource.resource_type == ClassResource.ResourceType.MUSIC and resource.dance_id and teacher_mode:
                resource.approval_status = ClassResource.ApprovalStatus.PENDING
                resource.visibility = ClassResource.Visibility.STAFF
            resource.full_clean()
            resource.save()
            if resource.approval_status == ClassResource.ApprovalStatus.PENDING:
                from .music_reviews import notify_music_submitted
                transaction.on_commit(lambda resource_id=resource.pk: notify_music_submitted(resource_id))
            elif resource.resource_type == ClassResource.ResourceType.MUSIC and resource.dance_id and role == "administrator":
                from .music_reviews import notify_music_reviewed
                previous = resource.dance.music_resource
                if previous and previous.pk != resource.pk and previous.dance_id == resource.dance_id:
                    previous.approval_status = ClassResource.ApprovalStatus.REPLACED
                    previous.visibility = ClassResource.Visibility.STAFF
                    previous.save(update_fields=["approval_status", "visibility", "updated_at"])
                dance_plan = resource.dance
                dance_plan.music_resource = resource
                dance_plan.song_title = resource.title
                dance_plan.artist = resource.artist
                dance_plan.save(update_fields=["music_resource", "song_title", "artist", "updated_at"])
                transaction.on_commit(lambda resource_id=resource.pk: notify_music_reviewed(resource_id))

            messages.success(
                request,
                "Class resource added.",
            )

            if dance is not None:
                if resource.resource_type == ClassResource.ResourceType.VIDEO:
                    return redirect("resources:dance_video_manager", studio_slug=studio.slug, plan_id=dance.id)
                return redirect("performance:plan_detail", studio_slug=studio.slug, plan_id=dance.id)
            if resource.resource_type == ClassResource.ResourceType.VIDEO:
                return redirect(video_return_url)
            return redirect("resources:resource_list", studio_slug=studio.slug)
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
                "dance": dance,
                "class_instance": dance.class_instance if dance else valid_classes.filter(pk=selected_class_id).first() if selected_class_id else None,
                "resource_type": request.GET.get("type", "music"),
            },
        )

    template_name = "resources/resource_form.html"
    if dance and request.GET.get("type") == "music":
        template_name = "resources/dance_music_submit.html"
    elif dance and request.GET.get("type") == "video":
        template_name = "resources/dance_video_add.html"

    return render(
        request,
        template_name,
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": ("Submit Dance Music" if dance and request.GET.get("type") == "music" else "Add Rehearsal Video" if dance and request.GET.get("type") == "video" else "Add Dance Resource" if dance else "Add Class Resource"),
            "dance_media_type": request.GET.get("type") if dance else None,
            "dance_context": dance,
            "video_return_url": video_return_url,
            "is_video_create": request.GET.get("type") == "video",
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

    # A teacher must submit a new song for review rather than silently
    # replacing an already reviewed recording.
    if teacher_mode and resource.resource_type == ClassResource.ResourceType.MUSIC and resource.dance_id:
        messages.warning(request, "For dance music, submit a replacement from Dance Resources so it can be approved.")
        return redirect("performance:plan_detail", studio_slug=studio.slug, plan_id=resource.dance_id)

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

@login_required
def dance_video_manager(request, studio_slug, plan_id):
    """Dance-scoped rehearsal video library; creation uses the existing validated resource form."""
    from performance.models import ChoreographyPlan
    from django.http import HttpResponseForbidden
    from urllib.parse import urlparse, parse_qs
    import re
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _workspace_role(request, studio)
    instructor = _teacher(request.user, studio)
    dance = get_object_or_404(ChoreographyPlan.objects.select_related('class_instance'), studio=studio, pk=plan_id)
    if role not in {'administrator', 'teacher'} or (role == 'teacher' and not (instructor and (dance.class_instance.instructor_id == instructor.pk or dance.class_instance.assistant_instructor_id == instructor.pk))):
        return HttpResponseForbidden('Class staff access required.')
    videos = list(ClassResource.objects.filter(studio=studio, class_instance=dance.class_instance, resource_type=ClassResource.ResourceType.VIDEO, is_active=True).filter(Q(dance=dance) | Q(dance__isnull=True)).order_by('sort_order', '-created_at'))
    for video in videos:
        parsed=urlparse(video.external_url or '')
        host=(parsed.hostname or '').lower()
        vid=''
        if host in {'www.youtube.com','youtube.com','m.youtube.com'} and parsed.path == '/watch':
            vid=parse_qs(parsed.query).get('v',[''])[0]
        elif host in {'youtu.be','www.youtu.be'}:
            vid=parsed.path.strip('/').split('/')[0]
        elif host in {'youtube.com','www.youtube.com'} and parsed.path.startswith('/shorts/'):
            vid=parsed.path.split('/')[2]
        video.thumbnail_url=f'https://img.youtube.com/vi/{vid}/hqdefault.jpg' if re.fullmatch(r'[a-zA-Z0-9_-]{11}',vid) else ''
    if request.method == 'POST':
        video = get_object_or_404(ClassResource, studio=studio, pk=request.POST.get('video_id'), class_instance=dance.class_instance, resource_type=ClassResource.ResourceType.VIDEO, is_active=True)
        if video.dance_id not in (None,dance.id):
            return HttpResponseForbidden('Video belongs to another dance.')
        video.dance = dance if request.POST.get('action') == 'attach' else None
        video.save(update_fields=['dance','updated_at'])
        messages.success(request,'Video association updated.')
        return redirect('resources:dance_video_manager',studio_slug=studio.slug,plan_id=dance.id)
    return render(request, 'resources/dance_video_manager.html', {'studio':studio,'dance':dance,'videos':videos})


@login_required
def video_manager(request, studio_slug):
    """Studio/class video library, independent of whether a dance exists."""
    from django.http import HttpResponseForbidden
    from django.utils.http import url_has_allowed_host_and_scheme
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _workspace_role(request, studio)
    if role not in ('administrator', 'teacher'):
        return HttpResponseForbidden('Studio staff access required.')
    instructor = _teacher(request.user, studio)
    classes = Class.objects.filter(studio=studio)
    if role == 'teacher':
        classes = classes.filter(Q(instructor=instructor) | Q(assistant_instructor=instructor)).distinct() if instructor else classes.none()
    selected_class = request.GET.get('class', '').strip()
    videos = ClassResource.objects.filter(studio=studio, resource_type=ClassResource.ResourceType.VIDEO, is_active=True, class_instance__in=classes).select_related('class_instance','dance')
    if selected_class:
        videos = videos.filter(class_instance_id=selected_class)
    q = request.GET.get('q','').strip()
    if q:
        videos = videos.filter(Q(title__icontains=q)|Q(class_instance__name__icontains=q))
    origin = request.GET.get('next', '').strip()
    if not origin:
        origin = request.META.get('HTTP_REFERER', '')
    if not url_has_allowed_host_and_scheme(origin, allowed_hosts={request.get_host()}, require_https=request.is_secure()) or '/video-manager/' in origin:
        origin = reverse('performance:plan_list', kwargs={'studio_slug':studio.slug})
    return render(request,'resources/video_manager.html',{'studio':studio, 'videos':videos.order_by('-created_at')[:200], 'classes':classes.order_by('name'), 'selected_class':selected_class, 'query':q, 'back_url':origin, 'workspace_role':role, 'role':role})
