"""Dance music review and notifications. Studio roles checked on every endpoint."""
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from studios.models import Studio, StudioMembership
from communications.models import WorkspaceNotification
from communications.studio_email import send_studio_email
from families.models import Guardian
from .models import ClassResource
from .views import _workspace_role, _teacher

logger = logging.getLogger(__name__)


def _notify(studio, memberships, kind, title, body, url, key):
    users = set()
    for membership in memberships.select_related('user'):
        if membership.user_id in users:
            continue
        users.add(membership.user_id)
        WorkspaceNotification.objects.get_or_create(
            studio=studio, user=membership.user, dedupe_key=f"music:{key}:{membership.user_id}",
            defaults=dict(category=WorkspaceNotification.Category.SYSTEM, kind=kind,
                          title=title, message=body, action_url=url),
        )
        if membership.user.email:
            try:
                send_studio_email(studio=studio, to=[membership.user.email], subject=title,
                    html_body=f"<p>{escape(body)}</p><p><a href='{escape(url)}'>View in Encore</a></p>",
                    text_body=f"{body}\n\n{url}",
                    tags={'category':'dance_music', 'event':kind})
            except Exception:
                logger.exception('Music email failed for studio=%s recipient_user=%s', studio.pk, membership.user_id)


def notify_music_submitted(resource_id):
    resource = ClassResource.objects.select_related('studio', 'dance', 'class_instance', 'uploaded_by').filter(pk=resource_id).first()
    if not resource or resource.approval_status != ClassResource.ApprovalStatus.PENDING:
        return
    url = reverse('resources:music_manager', kwargs={'studio_slug':resource.studio.slug})
    teacher = str(resource.uploaded_by or 'Teacher')
    body = f"{teacher} submitted '{resource.title}' for {resource.class_instance.name} ({resource.dance}). Review the song in Music Manager."
    admins = StudioMembership.objects.filter(studio=resource.studio, role='administrator', is_active=True)
    _notify(resource.studio, admins, 'dance_music_pending', 'New music approval requested', body, url, f'submit:{resource.pk}')


def notify_music_reviewed(resource_id):
    resource = ClassResource.objects.select_related('studio','class_instance','dance','uploaded_by').get(pk=resource_id)
    approved = resource.approval_status == ClassResource.ApprovalStatus.APPROVED
    url = reverse('performance:plan_detail', kwargs={'studio_slug': resource.studio.slug, 'plan_id':resource.dance_id})
    result = 'approved' if approved else 'rejected'
    body = f"Your song '{resource.title}' for {resource.class_instance.name} was {result}."
    if resource.review_comment:
        body += f" Admin feedback: {resource.review_comment}"
    if resource.uploaded_by_id and resource.uploaded_by.user_id:
        teachers = StudioMembership.objects.filter(studio=resource.studio, user_id=resource.uploaded_by.user_id, is_active=True)
        _notify(resource.studio, teachers, f'dance_music_{result}', f'Dance music {result}', body, url, f'review:{resource.pk}:{result}')
    if not approved:
        return
    # Notify active enrolled guardians once per email address; do not send to withdrawn families.
    guardians = Guardian.objects.filter(
        family__studio=resource.studio, is_active=True,
        family__students__enrollments__class_instance_id=resource.class_instance_id,
        family__students__enrollments__status='active',
    ).exclude(email='').values_list('email', flat=True).distinct()
    for address in set(guardians):
        try:
            send_studio_email(studio=resource.studio, to=[address],
                subject=f'New music for {resource.class_instance.name}',
                html_body=f'<p>New music has been added for {escape(resource.class_instance.name)}. Log in to Encore to access the approved song.</p>',
                tags={'category':'dance_music', 'event':'approved_family'})
        except Exception:
            logger.exception('Family music email failed for resource=%s', resource.pk)


@login_required
def music_manager(request, studio_slug):
    from django.utils.http import url_has_allowed_host_and_scheme
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _workspace_role(request, studio)
    if role not in ('administrator', 'teacher'):
        return HttpResponseForbidden('Studio staff access required.')
    state = request.GET.get('status', 'pending')
    records = ClassResource.objects.filter(studio=studio, dance__isnull=False,
        resource_type=ClassResource.ResourceType.MUSIC).select_related('class_instance', 'dance', 'uploaded_by')
    if role == 'teacher':
        instructor = _teacher(request.user,studio)
        if instructor is None:
            records = records.none()
        else:
            records = records.filter(Q(class_instance__instructor=instructor)|Q(class_instance__assistant_instructor=instructor))
    selected_class = request.GET.get('class','').strip()
    if selected_class:
        records = records.filter(class_instance_id=selected_class)
    if state in {k for k, _ in ClassResource.ApprovalStatus.choices}:
        records = records.filter(approval_status=state)
    query = request.GET.get('q','').strip()
    if query:
        records = records.filter(Q(title__icontains=query)|Q(class_instance__name__icontains=query)|Q(artist__icontains=query))
    origin = request.GET.get('next','').strip() or request.META.get('HTTP_REFERER','')
    if not url_has_allowed_host_and_scheme(origin, allowed_hosts={request.get_host()}, require_https=request.is_secure()) or '/music-manager/' in origin:
        origin = reverse('performance:plan_list', kwargs={'studio_slug':studio.slug})
    return render(request,'resources/music_manager.html',dict(studio=studio, records=records.order_by('-created_at')[:150],
        status=state, query=query, selected_class=selected_class, back_url=origin, role=role, workspace_role=role, can_review=role=='administrator'))


@login_required
def music_review(request, studio_slug, resource_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _workspace_role(request,studio) != 'administrator':
        return HttpResponseForbidden('Studio administrator access required.')
    song = get_object_or_404(ClassResource.objects.select_related('dance','class_instance','uploaded_by'),
        pk=resource_id,studio=studio,resource_type=ClassResource.ResourceType.MUSIC,dance__isnull=False)
    if request.method=='POST':
        action = request.POST.get('decision')
        reason = request.POST.get('comment','').strip()
        if action not in ('approved','rejected') or (action=='rejected' and not reason):
            messages.error(request,'Choose an action and supply a reason when rejecting music.')
        else:
            with transaction.atomic():
                song = ClassResource.objects.select_for_update().get(pk=song.pk,studio=studio)
                if song.approval_status != ClassResource.ApprovalStatus.PENDING:
                    messages.error(request,'This submission was already reviewed. No action was taken.')
                else:
                    song.approval_status = action
                    song.review_comment = reason
                    song.reviewed_by = request.user
                    song.reviewed_at = timezone.now()
                    song.visibility = ClassResource.Visibility.ENROLLED if action=='approved' else ClassResource.Visibility.STAFF
                    song.save(update_fields=['approval_status','review_comment','reviewed_by','reviewed_at','visibility','updated_at'])
                    if action=='approved':
                        from performance.models import ChoreographyPlan
                        dance = ChoreographyPlan.objects.select_for_update().get(pk=song.dance_id,studio=studio)
                        previous = dance.music_resource
                        if previous and previous.pk != song.pk and previous.dance_id == dance.pk and previous.resource_type == ClassResource.ResourceType.MUSIC:
                            previous.approval_status = ClassResource.ApprovalStatus.REPLACED
                            previous.visibility = ClassResource.Visibility.STAFF
                            previous.save(update_fields=['approval_status','visibility','updated_at'])
                        dance.music_resource = song
                        dance.song_title = song.title
                        dance.artist = song.artist
                        dance.save(update_fields=['music_resource','song_title','artist','updated_at'])
                    transaction.on_commit(lambda pk=song.pk: notify_music_reviewed(pk))
                    messages.success(request, f'Music {action}.')
            return redirect('resources:music_manager',studio_slug=studio.slug)
    return render(request,'resources/music_review.html',dict(studio=studio,song=song))

@login_required
def music_file(request, studio_slug, resource_id):
    """Authenticated streaming gateway for music (public /media/ must also be blocked by web server)."""
    from django.http import FileResponse, Http404
    from .views import _family_resource_queryset, _student_resource_queryset
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _workspace_role(request,studio)
    music = get_object_or_404(ClassResource, pk=resource_id,studio=studio,
                              resource_type=ClassResource.ResourceType.MUSIC, is_active=True)
    if role == 'administrator':
        allowed = True
    elif role == 'teacher':
        instructor = _teacher(request.user,studio)
        allowed = bool(instructor and (music.class_instance.instructor_id == instructor.pk or music.class_instance.assistant_instructor_id == instructor.pk))
    elif role in ('family','student') and music.approval_status == ClassResource.ApprovalStatus.APPROVED:
        qs = _family_resource_queryset(request.user,studio) if role == 'family' else _student_resource_queryset(request.user,studio)
        allowed = qs.filter(pk=music.pk).exists()
    else:
        allowed = False
    if not allowed or not music.file:
        raise Http404()
    try:
        handle = music.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404()
    response = FileResponse(handle, as_attachment=False)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
