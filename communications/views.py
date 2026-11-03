import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render

from classes.models import Class
from instructors.models import Instructor
from students.models import Student
from studios.models import Studio
from dashboard.parent_portal import parent_portal_context

from .forms import (
    AnnouncementForm,
    AutomatedEmailSettingForm,
    EmailCampaignForm,
    EmailAutomationRuleForm,
    EmailSignatureForm,
    EmailTemplateForm,
)
from .models import (
    Announcement,
    AnnouncementRead,
    AutomatedEmailSetting,
    EmailCampaign,
    EmailCampaignRecipient,
    EmailAutomationRule,
    EmailSignature,
    EmailSuppression,
    EmailTemplate,
    OutboundEmailLog,
)
from .services import (
    ensure_default_email_setup,
    materialize_campaign_recipients,
    resolve_recipient_selection,
    send_campaign,
    teacher_for_user,
    visible_announcements_for_user,
    workspace_role,
)


def _require_staff(request, studio):
    role = workspace_role(
        request,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return None, None

    instructor = teacher_for_user(
        request.user,
        studio,
    )

    if (
        role == "teacher"
        and instructor is None
    ):
        return None, None

    return role, instructor


def _teacher_can_edit(
    instructor,
    announcement,
):
    if announcement.created_by_id:
        return (
            announcement.created_by_id
            == instructor.user_id
        )

    return False


@login_required
def announcement_list(
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

    if role is None:
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
            "encore_announcement_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_announcement_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

    announcements = (
        visible_announcements_for_user(
            request,
            studio,
        )
        .order_by(
            "-is_pinned",
            "-publish_at",
        )
    )

    search = request.GET.get(
        "q",
        "",
    ).strip()

    priority = request.GET.get(
        "priority",
        "",
    ).strip()

    if search:
        announcements = announcements.filter(
            Q(title__icontains=search)
            | Q(message__icontains=search)
        )

    if priority:
        announcements = announcements.filter(
            priority=priority,
        )

    read_ids = set(
        AnnouncementRead.objects
        .filter(
            user=request.user,
            announcement__in=announcements,
        )
        .values_list(
            "announcement_id",
            flat=True,
        )
    )

    rows = [
        {
            "announcement": item,
            "is_read": item.id in read_ids,
        }
        for item in announcements
    ]

    context = {
        "studio": studio,
        "role": role,
        "announcement_rows": rows,
        "priority_choices": Announcement.Priority.choices,
        "filters": {
            "q": search,
            "priority": priority,
        },
        "can_create": role in {
            "administrator",
            "teacher",
        },
        "view_mode": view_mode,
        "card_view_url": (
            "?"
            + urlencode(
                {
                    "q": search,
                    "priority": priority,
                    "view": "cards",
                }
            )
        ),
        "table_view_url": (
            "?"
            + urlencode(
                {
                    "q": search,
                    "priority": priority,
                    "view": "table",
                }
            )
        ),
    }

    template_name = "communications/announcement_list.html"

    if role == "family":
        context.update(
            parent_portal_context(
                request,
                studio,
                section="announcements",
            )
        )
        template_name = (
            "communications/parent_announcement_list.html"
        )

    return render(
        request,
        template_name,
        context,
    )


@login_required
def announcement_detail(
    request,
    studio_slug,
    announcement_id,
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

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    announcement = get_object_or_404(
        visible_announcements_for_user(
            request,
            studio,
        ),
        pk=announcement_id,
    )

    AnnouncementRead.objects.get_or_create(
        announcement=announcement,
        user=request.user,
    )

    instructor = teacher_for_user(
        request.user,
        studio,
    )

    can_edit = (
        role == "administrator"
        or (
            role == "teacher"
            and instructor is not None
            and _teacher_can_edit(
                instructor,
                announcement,
            )
        )
    )

    context = {
        "studio": studio,
        "role": role,
        "announcement": announcement,
        "can_edit": can_edit,
    }

    template_name = "communications/announcement_detail.html"

    if role == "family":
        context.update(
            parent_portal_context(
                request,
                studio,
                section="announcements",
            )
        )
        template_name = (
            "communications/parent_announcement_detail.html"
        )

    return render(
        request,
        template_name,
        context,
    )


@login_required
def announcement_create(
    request,
    studio_slug,
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

    form = AnnouncementForm(
        request.POST or None,
        studio=studio,
        instructor=instructor,
        teacher_mode=(
            role == "teacher"
        ),
    )

    if request.method == "POST" and form.is_valid():
        announcement = form.save(
            commit=False
        )

        announcement.studio = studio
        announcement.created_by = request.user
        announcement.full_clean()
        announcement.save()
        form.save_m2m()

        messages.success(
            request,
            "Announcement published.",
        )

        return redirect(
            "communications:announcement_detail",
            studio_slug=studio.slug,
            announcement_id=announcement.pk,
        )

    return render(
        request,
        "communications/announcement_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "New Announcement",
        },
    )


@login_required
def announcement_edit(
    request,
    studio_slug,
    announcement_id,
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

    announcement = get_object_or_404(
        Announcement,
        pk=announcement_id,
        studio=studio,
    )

    if (
        role == "teacher"
        and not _teacher_can_edit(
            instructor,
            announcement,
        )
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = AnnouncementForm(
        request.POST or None,
        instance=announcement,
        studio=studio,
        instructor=instructor,
        teacher_mode=(
            role == "teacher"
        ),
    )

    if request.method == "POST" and form.is_valid():
        announcement = form.save(
            commit=False
        )

        announcement.full_clean()
        announcement.save()
        form.save_m2m()

        messages.success(
            request,
            "Announcement updated.",
        )

        return redirect(
            "communications:announcement_detail",
            studio_slug=studio.slug,
            announcement_id=announcement.pk,
        )

    return render(
        request,
        "communications/announcement_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Edit Announcement",
        },
    )



def _require_email_staff(
    request,
    studio,
):
    role, instructor = _require_staff(
        request,
        studio,
    )

    if role is None:
        return None, None

    return role, instructor


@login_required
def email_manager(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    ensure_default_email_setup(
        studio,
        user=request.user,
    )

    campaigns = (
        EmailCampaign.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "created_by",
        )
    )

    if role == "teacher":
        campaigns = campaigns.filter(
            created_by=request.user,
        )

    recent_campaigns = campaigns[:6]

    totals = campaigns.aggregate(
        total_sent=Sum(
            "sent_count"
        ),
        total_delivered=Sum(
            "delivered_count"
        ),
        total_opened=Sum(
            "opened_count"
        ),
        total_failed=Sum(
            "failed_count"
        ),
    )

    scheduled_count = campaigns.filter(
        status=EmailCampaign.Status.SCHEDULED,
    ).count()

    return render(
        request,
        "communications/email/manager.html",
        {
            "studio": studio,
            "role": role,
            "recent_campaigns": recent_campaigns,
            "scheduled_count": scheduled_count,
            "template_count": (
                EmailTemplate.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .count()
            ),
            "signature_count": (
                EmailSignature.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .count()
            ),
            "totals": {
                key: (
                    value
                    or 0
                )
                for key, value
                in totals.items()
            },
        },
    )


def _email_audience_catalog(
    studio,
    *,
    role,
    instructor=None,
):
    classes = (
        Class.objects
        .filter(studio=studio, is_active=True)
        .select_related("season")
        .order_by("name")
    )

    instructors = (
        Instructor.objects
        .filter(studio=studio, is_active=True)
        .select_related("user")
        .order_by("last_name", "first_name")
    )

    students = (
        Student.objects
        .filter(studio=studio, is_active=True)
        .select_related("family", "user")
        .order_by("last_name", "first_name")
    )

    if role == "teacher" and instructor is not None:
        classes = classes.filter(
            Q(instructor=instructor)
            | Q(assistant_instructor=instructor)
        ).distinct()

        students = students.filter(
            enrollments__class_instance__in=classes,
            enrollments__status="active",
        ).distinct()

        instructors = instructors.filter(pk=instructor.pk)

    User = get_user_model()
    admins = (
        User.objects
        .filter(
            studio_memberships__studio=studio,
            studio_memberships__role="administrator",
            studio_memberships__is_active=True,
            is_active=True,
        )
        .distinct()
        .order_by("last_name", "first_name", "email")
    )

    groups = [
        {
            "key": "all",
            "label": "All",
            "description": "All active family contacts, instructors, and administrators.",
        },
        {
            "key": "students",
            "label": "Students",
            "description": "Select students; parents/guardians are emailed by default.",
        },
        {
            "key": "instructors",
            "label": "Instructors",
            "description": "Email selected instructors directly.",
        },
        {
            "key": "classes",
            "label": "Classes",
            "description": "Email parents/guardians for students actively enrolled in selected classes.",
        },
        {
            "key": "instructor_students",
            "label": "Instructor's Students",
            "description": "Select instructors and email families of students in their current classes.",
        },
    ]

    if role == "administrator" and admins.count() > 1:
        groups.append(
            {
                "key": "admins",
                "label": "Admins",
                "description": "Email selected studio administrators.",
            }
        )

    return {
        "groups": groups,
        "options": {
            "students": [
                {
                    "id": item.pk,
                    "label": f"{item.first_name} {item.last_name}".strip(),
                }
                for item in students
            ],
            "instructors": [
                {"id": item.pk, "label": item.full_name}
                for item in instructors
            ],
            "classes": [
                {
                    "id": item.pk,
                    "label": item.name,
                    "meta": item.season.name if item.season_id else "",
                }
                for item in classes
            ],
            "instructor_students": [
                {"id": item.pk, "label": item.full_name}
                for item in instructors
            ],
            "admins": [
                {
                    "id": item.pk,
                    "label": item.get_full_name() or item.email,
                }
                for item in admins
            ],
        },
    }


def _email_template_payloads(studio):
    templates = (
        EmailTemplate.objects
        .filter(studio=studio, is_active=True)
        .select_related("signature")
        .order_by("category", "name")
    )

    return {
        str(item.pk): {
            "name": item.name,
            "subject": item.subject,
            "html_body": item.html_body,
            "text_body": item.text_body,
            "signature_id": item.signature_id or "",
        }
        for item in templates
    }


@login_required
def email_recipient_preview(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return JsonResponse({"error": "Access denied."}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    selection = payload.get("selection", {})

    if role == "teacher":
        selection = dict(selection)
        selection["all"] = False
        groups = dict(selection.get("groups", {}))
        groups["admins"] = []
        selection["groups"] = groups

    recipients = resolve_recipient_selection(
        studio,
        selection,
        send_to_students=bool(
            payload.get("send_to_students", False)
        ),
    )

    counts = {
        "guardian": 0,
        "student": 0,
        "instructor": 0,
        "admin": 0,
        "suppressed": 0,
    }

    for recipient in recipients:
        recipient_type = recipient["recipient_type"]

        if recipient_type in counts:
            counts[recipient_type] += 1

        if recipient["suppressed"]:
            counts["suppressed"] += 1

    return JsonResponse(
        {
            "total": len(recipients),
            "counts": counts,
        }
    )


@login_required
def email_compose(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
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

    ensure_default_email_setup(
        studio,
        user=request.user,
    )

    template = None
    template_id = request.GET.get("template", "")

    if template_id:
        template = (
            EmailTemplate.objects
            .filter(
                studio=studio,
                is_active=True,
                pk=template_id,
            )
            .first()
        )

    form = EmailCampaignForm(
        request.POST or None,
        studio=studio,
        instructor=instructor,
        teacher_mode=(role == "teacher"),
        template=template,
    )

    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.studio = studio
        campaign.created_by = request.user
        campaign.recipient_mode = EmailCampaign.RecipientMode.MIXED
        campaign.send_to_guardians = True

        action = request.POST.get("action", "draft")
        schedule_email = form.cleaned_data.get(
            "schedule_email",
            False,
        )

        if (
            action == "send"
            and schedule_email
            and campaign.scheduled_for
            and campaign.scheduled_for <= timezone.now()
        ):
            form.add_error(
                "scheduled_for",
                "Scheduled email must be in the future.",
            )
        else:
            campaign.status = EmailCampaign.Status.DRAFT

            if action == "send" and schedule_email:
                campaign.status = EmailCampaign.Status.SCHEDULED

            campaign.save()

            selection = campaign.recipient_selection or {}
            groups = selection.get("groups", {})

            campaign.selected_classes.set(
                groups.get("classes", [])
            )

            direct_instructors = set(
                groups.get("instructors", [])
            )
            direct_instructors.update(
                groups.get("instructor_students", [])
            )
            campaign.selected_instructors.set(
                direct_instructors
            )

            materialize_campaign_recipients(
                campaign
            )

            if action == "send" and not schedule_email:
                result = send_campaign(campaign)

                if result["failed"]:
                    messages.warning(
                        request,
                        (
                            f"Email processed: "
                            f"{result['sent']} sent, "
                            f"{result['failed']} failed, "
                            f"{result['suppressed']} suppressed."
                        ),
                    )
                else:
                    messages.success(
                        request,
                        f"Email sent to {result['sent']} recipients.",
                    )

            elif action == "send" and schedule_email:
                messages.success(
                    request,
                    "Email scheduled.",
                )
            else:
                messages.success(
                    request,
                    "Draft saved.",
                )

            return redirect(
                "communications:email_campaign_detail",
                studio_slug=studio.slug,
                campaign_id=campaign.pk,
            )

    return render(
        request,
        "communications/email/compose.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "selected_template": template,
            "audience_catalog": _email_audience_catalog(
                studio,
                role=role,
                instructor=instructor,
            ),
            "template_payloads": _email_template_payloads(studio),
        },
    )


@login_required
def email_campaign_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    campaigns = (
        EmailCampaign.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "created_by",
            "template",
        )
    )

    if role == "teacher":
        campaigns = campaigns.filter(
            created_by=request.user,
        )

    status = request.GET.get(
        "status",
        "",
    )

    if status:
        campaigns = campaigns.filter(
            status=status,
        )

    return render(
        request,
        "communications/email/campaign_list.html",
        {
            "studio": studio,
            "role": role,
            "campaigns": campaigns,
            "status_choices": (
                EmailCampaign.Status.choices
            ),
            "selected_status": status,
        },
    )


@login_required
def email_campaign_detail(
    request,
    studio_slug,
    campaign_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    campaign_qs = (
        EmailCampaign.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "created_by",
            "template",
            "signature",
        )
        .prefetch_related(
            "recipients",
            "selected_classes",
            "selected_instructors",
        )
    )

    if role == "teacher":
        campaign_qs = campaign_qs.filter(
            created_by=request.user,
        )

    campaign = get_object_or_404(
        campaign_qs,
        pk=campaign_id,
    )

    recipients = campaign.recipients.all()

    return render(
        request,
        "communications/email/campaign_detail.html",
        {
            "studio": studio,
            "role": role,
            "campaign": campaign,
            "recipients": recipients,
            "can_send": (
                campaign.status
                in {
                    EmailCampaign.Status.DRAFT,
                    EmailCampaign.Status.FAILED,
                    EmailCampaign.Status.PARTIAL_FAILED,
                }
            ),
        },
    )


@login_required
def email_campaign_send(
    request,
    studio_slug,
    campaign_id,
):
    if request.method != "POST":
        return redirect(
            "communications:email_campaign_detail",
            studio_slug=studio_slug,
            campaign_id=campaign_id,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    campaign_qs = EmailCampaign.objects.filter(
        studio=studio,
    )

    if role == "teacher":
        campaign_qs = campaign_qs.filter(
            created_by=request.user,
        )

    campaign = get_object_or_404(
        campaign_qs,
        pk=campaign_id,
    )

    result = send_campaign(
        campaign
    )

    messages.success(
        request,
        (
            f"Campaign processed: "
            f"{result['sent']} sent, "
            f"{result['failed']} failed, "
            f"{result['suppressed']} suppressed."
        ),
    )

    return redirect(
        "communications:email_campaign_detail",
        studio_slug=studio.slug,
        campaign_id=campaign.pk,
    )


@login_required
def email_template_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    ensure_default_email_setup(
        studio,
        user=request.user,
    )

    templates = (
        EmailTemplate.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "signature",
        )
        .order_by(
            "category",
            "name",
        )
    )

    return render(
        request,
        "communications/email/template_list.html",
        {
            "studio": studio,
            "role": role,
            "templates": templates,
        },
    )


@login_required
def email_template_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
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

    form = EmailTemplateForm(
        request.POST or None,
        studio=studio,
    )

    automation_form = EmailAutomationRuleForm(
        request.POST or None,
        prefix="automation",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and automation_form.is_valid()
    ):
        template = form.save(commit=False)
        template.studio = studio
        template.created_by = request.user
        template.save()

        automation = automation_form.save(commit=False)

        if automation.enabled:
            automation.studio = studio
            automation.template = template

            if not automation.name:
                automation.name = f"{template.name} Automation"

            automation.save()

        messages.success(
            request,
            "Email template created.",
        )

        return redirect(
            "communications:email_template_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "communications/email/template_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "automation_form": automation_form,
            "page_title": "New Email Template",
        },
    )


@login_required
def email_template_edit(
    request,
    studio_slug,
    template_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
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

    template = get_object_or_404(
        EmailTemplate,
        studio=studio,
        pk=template_id,
    )

    automation = (
        template.automation_rules
        .order_by("created_at")
        .first()
    )

    form = EmailTemplateForm(
        request.POST or None,
        instance=template,
        studio=studio,
    )

    automation_form = EmailAutomationRuleForm(
        request.POST or None,
        instance=automation,
        prefix="automation",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and automation_form.is_valid()
    ):
        template = form.save()
        rule = automation_form.save(commit=False)

        if rule.enabled:
            rule.studio = studio
            rule.template = template

            if not rule.name:
                rule.name = f"{template.name} Automation"

            rule.save()

        elif automation is not None:
            automation.enabled = False
            automation.save(
                update_fields=[
                    "enabled",
                    "updated_at",
                ]
            )

        messages.success(
            request,
            "Email template updated.",
        )

        return redirect(
            "communications:email_template_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "communications/email/template_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "automation_form": automation_form,
            "page_title": "Edit Email Template",
            "template": template,
        },
    )


@login_required
def email_signature_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    ensure_default_email_setup(
        studio,
        user=request.user,
    )

    return render(
        request,
        "communications/email/signature_list.html",
        {
            "studio": studio,
            "role": role,
            "signatures": (
                EmailSignature.objects
                .filter(
                    studio=studio,
                )
            ),
        },
    )


@login_required
def email_signature_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    form = EmailSignatureForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        signature = form.save(
            commit=False
        )

        signature.studio = studio
        signature.created_by = (
            request.user
        )

        signature.save()

        messages.success(
            request,
            "Email signature created.",
        )

        return redirect(
            "communications:email_signature_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "communications/email/signature_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "New Email Signature",
        },
    )


@login_required
def email_signature_edit(
    request,
    studio_slug,
    signature_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    signature = get_object_or_404(
        EmailSignature,
        studio=studio,
        pk=signature_id,
    )

    form = EmailSignatureForm(
        request.POST or None,
        instance=signature,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Email signature updated.",
        )

        return redirect(
            "communications:email_signature_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "communications/email/signature_form.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "page_title": "Edit Email Signature",
            "signature": signature,
        },
    )


@login_required
def email_automations(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    ensure_default_email_setup(
        studio,
        user=request.user,
    )

    settings_rows = (
        AutomatedEmailSetting.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "template",
        )
        .order_by(
            "trigger",
        )
    )

    return render(
        request,
        "communications/email/automations.html",
        {
            "studio": studio,
            "role": role,
            "automation_rows": settings_rows,
            "template_automation_rules": (
                EmailAutomationRule.objects
                .filter(studio=studio)
                .select_related("template")
                .order_by(
                    "-enabled",
                    "template__name",
                    "trigger_type",
                )
            ),
        },
    )


@login_required
def email_automation_edit(
    request,
    studio_slug,
    setting_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    automation = get_object_or_404(
        AutomatedEmailSetting,
        studio=studio,
        pk=setting_id,
    )

    form = AutomatedEmailSettingForm(
        request.POST or None,
        instance=automation,
        studio=studio,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            (
                f"{automation.get_trigger_display()} "
                "email settings updated."
            ),
        )

        return redirect(
            "communications:email_automations",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "communications/email/automation_form.html",
        {
            "studio": studio,
            "role": role,
            "automation": automation,
            "form": form,
        },
    )


@login_required
def email_analytics(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    campaigns = EmailCampaign.objects.filter(
        studio=studio,
    )

    if role == "teacher":
        campaigns = campaigns.filter(
            created_by=request.user,
        )

    totals = campaigns.aggregate(
        recipients=Sum(
            "total_recipients"
        ),
        sent=Sum(
            "sent_count"
        ),
        delivered=Sum(
            "delivered_count"
        ),
        opened=Sum(
            "opened_count"
        ),
        clicked=Sum(
            "clicked_count"
        ),
        failed=Sum(
            "failed_count"
        ),
        bounced=Sum(
            "bounced_count"
        ),
        complaints=Sum(
            "complaint_count"
        ),
    )

    totals = {
        key: (
            value
            or 0
        )
        for key, value
        in totals.items()
    }

    delivery_rate = 0
    open_rate = 0

    if totals["sent"]:
        delivery_rate = round(
            (
                totals["delivered"]
                / totals["sent"]
            )
            * 100,
            1,
        )

    if totals["delivered"]:
        open_rate = round(
            (
                totals["opened"]
                / totals["delivered"]
            )
            * 100,
            1,
        )

    return render(
        request,
        "communications/email/analytics.html",
        {
            "studio": studio,
            "role": role,
            "totals": totals,
            "delivery_rate": delivery_rate,
            "open_rate": open_rate,
            "campaigns": campaigns[:12],
        },
    )


@login_required
def email_settings(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    suppressions = (
        EmailSuppression.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .order_by(
            "-updated_at",
        )[:50]
    )

    return render(
        request,
        "communications/email/settings.html",
        {
            "studio": studio,
            "role": role,
            "suppressions": suppressions,
            "email_config": {
                "from_name": getattr(
                    settings,
                    "EMAIL_FROM_NAME",
                    "Encore Performance Suite",
                ),
                "no_reply": getattr(
                    settings,
                    "EMAIL_FROM_ADDRESS",
                    (
                        "no-reply@"
                        "encoreperformancesuite.com"
                    ),
                ),
                "reply_to": getattr(
                    settings,
                    "EMAIL_REPLY_TO",
                    (
                        "info@"
                        "encoreperformancesuite.com"
                    ),
                ),
                "configuration_set": getattr(
                    settings,
                    "SES_CONFIGURATION_SET",
                    "encore-main",
                ),
                "region": getattr(
                    settings,
                    "AWS_SES_REGION",
                    "us-east-2",
                ),
            },
        },
    )



@login_required
def email_campaign_edit(
    request,
    studio_slug,
    campaign_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
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

    campaign_qs = EmailCampaign.objects.filter(
        studio=studio,
        status__in=[
            EmailCampaign.Status.DRAFT,
            EmailCampaign.Status.SCHEDULED,
            EmailCampaign.Status.FAILED,
            EmailCampaign.Status.PARTIAL_FAILED,
        ],
    )

    if role == "teacher":
        campaign_qs = campaign_qs.filter(
            created_by=request.user,
        )

    campaign = get_object_or_404(
        campaign_qs,
        pk=campaign_id,
    )

    form = EmailCampaignForm(
        request.POST or None,
        instance=campaign,
        studio=studio,
        instructor=instructor,
        teacher_mode=(role == "teacher"),
    )

    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.recipient_mode = EmailCampaign.RecipientMode.MIXED
        campaign.send_to_guardians = True

        action = request.POST.get("action", "draft")
        schedule_email = form.cleaned_data.get(
            "schedule_email",
            False,
        )

        if (
            action == "send"
            and schedule_email
            and campaign.scheduled_for
            and campaign.scheduled_for <= timezone.now()
        ):
            form.add_error(
                "scheduled_for",
                "Scheduled email must be in the future.",
            )
        else:
            campaign.status = EmailCampaign.Status.DRAFT

            if action == "send" and schedule_email:
                campaign.status = EmailCampaign.Status.SCHEDULED

            campaign.save()

            selection = campaign.recipient_selection or {}
            groups = selection.get("groups", {})

            campaign.selected_classes.set(
                groups.get("classes", [])
            )

            direct_instructors = set(
                groups.get("instructors", [])
            )
            direct_instructors.update(
                groups.get("instructor_students", [])
            )
            campaign.selected_instructors.set(
                direct_instructors
            )

            materialize_campaign_recipients(campaign)

            if action == "send" and not schedule_email:
                result = send_campaign(campaign)

                messages.success(
                    request,
                    (
                        f"Campaign processed: "
                        f"{result['sent']} sent, "
                        f"{result['failed']} failed, "
                        f"{result['suppressed']} suppressed."
                    ),
                )

            elif action == "send" and schedule_email:
                messages.success(
                    request,
                    "Scheduled email updated.",
                )
            else:
                messages.success(
                    request,
                    "Draft updated.",
                )

            return redirect(
                "communications:email_campaign_detail",
                studio_slug=studio.slug,
                campaign_id=campaign.pk,
            )

    return render(
        request,
        "communications/email/compose.html",
        {
            "studio": studio,
            "role": role,
            "form": form,
            "editing_campaign": campaign,
            "audience_catalog": _email_audience_catalog(
                studio,
                role=role,
                instructor=instructor,
            ),
            "template_payloads": _email_template_payloads(studio),
        },
    )


@login_required
def email_campaign_cancel(
    request,
    studio_slug,
    campaign_id,
):
    if request.method != "POST":
        return redirect(
            "communications:email_campaign_detail",
            studio_slug=studio_slug,
            campaign_id=campaign_id,
        )

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role, instructor = _require_email_staff(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    campaign_qs = EmailCampaign.objects.filter(
        studio=studio,
        status=EmailCampaign.Status.SCHEDULED,
    )

    if role == "teacher":
        campaign_qs = campaign_qs.filter(
            created_by=request.user,
        )

    campaign = get_object_or_404(
        campaign_qs,
        pk=campaign_id,
    )

    campaign.status = (
        EmailCampaign.Status.CANCELLED
    )

    campaign.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    messages.success(
        request,
        "Scheduled email cancelled.",
    )

    return redirect(
        "communications:email_campaign_detail",
        studio_slug=studio.slug,
        campaign_id=campaign.pk,
    )


@login_required
def email_activity(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role, _instructor = _require_email_staff(request, studio)
    if role != "administrator":
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    records = OutboundEmailLog.objects.filter(studio=studio)
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        records = records.filter(Q(subject__icontains=search) | Q(sender__icontains=search) | Q(to_addresses__icontains=search))
    if status:
        records = records.filter(status=status)
    page = Paginator(records, 30).get_page(request.GET.get("page"))
    return render(request, "communications/email/activity.html", {"studio": studio, "role": role, "page": page, "q": search, "status_filter": status, "status_options": [("accepted", "Accepted by SES"), ("delivered", "Delivered"), ("failed", "Failed"), ("bounced", "Bounced"), ("sending", "Sending"), ("queued", "Queued"), ("complained", "Complaint"), ("delayed", "Delayed"), ("rejected", "Rejected")]})


@login_required
def email_activity_detail(request, studio_slug, email_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role, _instructor = _require_email_staff(request, studio)
    if role != "administrator":
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    record = get_object_or_404(OutboundEmailLog.objects.prefetch_related("delivery_events"), pk=email_id, studio=studio)
    return render(request, "communications/email/activity_detail.html", {"studio": studio, "role": role, "record": record})

@csrf_exempt
def outbound_email_events(request):
    """Authenticated SES event forwarder endpoint; not a public unauthenticated SNS endpoint.

    Configure a trusted forwarder (e.g. SNS -> Lambda) to POST the SES event
    JSON with X-Encore-Email-Event-Secret. Direct SNS calls are not authenticated
    by this endpoint and must NOT be configured without a verifying forwarder.
    """
    from django.http import HttpResponse, HttpResponseNotAllowed
    import os
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    from django.db import transaction
    from .models import OutboundEmailEvent
    from datetime import datetime, timezone as datetime_timezone
    import hashlib, hmac

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    secret = os.environ.get("ENCORE_EMAIL_EVENT_SECRET", "")
    provided = request.headers.get("X-Encore-Email-Event-Secret", "")
    if not secret or not hmac.compare_digest(provided, secret):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body)
        if isinstance(payload, dict) and "Message" in payload:
            payload = json.loads(payload["Message"])
        event_type = str(payload.get("eventType") or payload.get("notificationType") or "").lower()
        mail = payload.get("mail") or {}
        message_id = str(mail.get("messageId") or "")
        if not message_id or event_type not in {"delivery", "bounce", "complaint", "reject", "deliverydelay", "send", "renderingfailure"}:
            return HttpResponse(status=400)
        stamp = str((payload.get(event_type) or {}).get("timestamp") or mail.get("timestamp") or "")
        occurred = parse_datetime(stamp) or timezone.now()
        if timezone.is_naive(occurred):
            occurred = timezone.make_aware(occurred, datetime_timezone.utc)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with transaction.atomic():
            records = OutboundEmailLog.objects.select_for_update().filter(provider_message_id=message_id)
            for record in records:
                _event, created = OutboundEmailEvent.objects.get_or_create(
                    event_key=f"ses:{record.pk}:{digest}",
                    defaults={"email": record, "event_type": event_type, "occurred_at": occurred, "detail": payload},
                )
                if not created:
                    continue
                status_map = {"delivery": "delivered", "bounce": "bounced", "complaint": "complained", "reject": "rejected", "deliverydelay": "delayed", "renderingfailure": "failed"}
                if event_type in status_map:
                    record.status = status_map[event_type]
                    if event_type == "delivery":
                        record.delivered_at = occurred
                    record.last_event_at = occurred
                    record.save(update_fields=["status", "delivered_at", "last_event_at"])
        return HttpResponse(status=204)
    except (ValueError, TypeError, KeyError):
        return HttpResponse(status=400)
