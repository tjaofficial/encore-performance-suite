from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from students.models import Student

from .email_service import EncoreEmailError, send_email
from .models import (
    Announcement,
    AutomatedEmailSetting,
    EmailCampaign,
    EmailCampaignRecipient,
    EmailEvent,
    EmailSignature,
    EmailSuppression,
    EmailTemplate,
)


def workspace_role(request, studio):
    role = request.session.get(
        "encore_workspace_role"
    )

    selected_studio = request.session.get(
        "encore_workspace_studio_slug"
    )

    if selected_studio != studio.slug:
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


def teacher_for_user(user, studio):
    return Instructor.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()


def visible_announcements_for_user(
    request,
    studio,
):
    role = workspace_role(
        request,
        studio,
    )

    if role is None:
        return Announcement.objects.none()

    now = timezone.now()

    announcements = (
        Announcement.objects
        .filter(
            studio=studio,
            is_published=True,
            publish_at__lte=now,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
        .prefetch_related("classes")
        .select_related("created_by")
    )

    if role == "administrator":
        return announcements

    if role == "teacher":
        instructor = teacher_for_user(
            request.user,
            studio,
        )

        if instructor is None:
            return Announcement.objects.none()

        class_ids = list(
            instructor.primary_classes
            .filter(is_active=True)
            .values_list("id", flat=True)
        )

        class_ids += list(
            instructor.assistant_classes
            .filter(is_active=True)
            .values_list("id", flat=True)
        )

        return (
            announcements
            .filter(
                Q(
                    audience=Announcement.Audience.STUDIO
                )
                | Q(
                    audience=Announcement.Audience.STAFF
                )
                | Q(
                    audience=Announcement.Audience.TEACHERS
                )
                | Q(
                    audience=Announcement.Audience.CLASS,
                    classes__id__in=class_ids,
                )
            )
            .distinct()
        )

    if role == "family":
        family_ids = list(
            Guardian.objects
            .filter(
                family__studio=studio,
                user=request.user,
                is_active=True,
            )
            .values_list(
                "family_id",
                flat=True,
            )
        )

        class_ids = list(
            Enrollment.objects
            .filter(
                student__family_id__in=family_ids,
                status=Enrollment.Status.ACTIVE,
                class_instance__studio=studio,
            )
            .values_list(
                "class_instance_id",
                flat=True,
            )
        )

        return (
            announcements
            .filter(
                Q(
                    audience=Announcement.Audience.STUDIO
                )
                | Q(
                    audience=Announcement.Audience.FAMILIES
                )
                | Q(
                    audience=Announcement.Audience.CLASS,
                    classes__id__in=class_ids,
                )
            )
            .distinct()
        )

    # Student workspace
    class_ids = list(
        Enrollment.objects
        .filter(
            student__studio=studio,
            student__user=request.user,
            status=Enrollment.Status.ACTIVE,
        )
        .values_list(
            "class_instance_id",
            flat=True,
        )
    )

    return (
        announcements
        .filter(
            Q(
                audience=Announcement.Audience.STUDIO
            )
            | Q(
                audience=Announcement.Audience.STUDENTS
            )
            | Q(
                audience=Announcement.Audience.CLASS,
                classes__id__in=class_ids,
            )
        )
        .distinct()
    )



DEFAULT_AUTOMATED_EMAILS = [
    {
        "trigger": AutomatedEmailSetting.Trigger.REGISTRATION_STARTED,
        "category": EmailTemplate.Category.REGISTRATION,
        "name": "Registration Started Default",
        "subject": "We received your registration",
        "body": (
            "<p>Hi there,</p>"
            "<p>We received your registration information. "
            "The studio will let you know if anything else is needed.</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.ENROLLMENT_CONFIRMATION,
        "category": EmailTemplate.Category.ENROLLMENT,
        "name": "Enrollment Confirmation Default",
        "subject": "Class enrollment confirmed",
        "body": (
            "<p>Your class enrollment has been confirmed.</p>"
            "<p>We look forward to seeing you in class!</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.REGISTRATION_COMPLETE,
        "category": EmailTemplate.Category.REGISTRATION,
        "name": "Registration Complete Default",
        "subject": "Registration complete",
        "body": (
            "<p>Your registration is complete.</p>"
            "<p>Thank you for joining us!</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.PAYMENT_CONFIRMATION,
        "category": EmailTemplate.Category.PAYMENT,
        "name": "Payment Confirmation Default",
        "subject": "Payment received",
        "body": (
            "<p>Your payment has been received.</p>"
            "<p>This email confirms your completed payment.</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.TASK_ASSIGNED,
        "category": EmailTemplate.Category.TASK,
        "name": "Task Assigned Default",
        "subject": "New task assigned",
        "body": (
            "<p>A new task has been assigned to you in Encore.</p>"
            "<p>Open your task list for the details and due date.</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.EVENT_ANNOUNCEMENT,
        "category": EmailTemplate.Category.EVENT,
        "name": "Event Announcement Default",
        "subject": "New studio event",
        "body": (
            "<p>A new event has been added to the studio calendar.</p>"
            "<p>Please open Encore for the date, time, and event details.</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.BIRTHDAY,
        "category": EmailTemplate.Category.BIRTHDAY,
        "name": "Birthday Default",
        "subject": "Happy Birthday!",
        "body": (
            "<h2>Happy Birthday!</h2>"
            "<p>We hope you have an amazing day and a wonderful year ahead!</p>"
        ),
    },
    {
        "trigger": AutomatedEmailSetting.Trigger.COSTUME_INFORMATION,
        "category": EmailTemplate.Category.COSTUME,
        "name": "Costume Information Default",
        "subject": "New costume information",
        "body": (
            "<p>New costume information has been added.</p>"
            "<p>Open Encore to review the costume photos, links, and notes.</p>"
        ),
    },
]


def ensure_default_email_setup(
    studio,
    *,
    user=None,
):
    default_signature = (
        EmailSignature.objects
        .filter(
            studio=studio,
            is_default=True,
            is_active=True,
        )
        .first()
    )

    if default_signature is None:
        default_signature = EmailSignature.objects.create(
            studio=studio,
            name="Studio Default",
            body=(
                f"Thank you,\n"
                f"{studio.name}"
            ),
            is_default=True,
            is_active=True,
            created_by=user,
        )

    for item in DEFAULT_AUTOMATED_EMAILS:
        template, _ = EmailTemplate.objects.get_or_create(
            studio=studio,
            name=item["name"],
            defaults={
                "category": item["category"],
                "subject": item["subject"],
                "html_body": item["body"],
                "text_body": strip_tags(
                    item["body"]
                ),
                "signature": default_signature,
                "is_system_default": True,
                "is_active": True,
                "created_by": user,
            },
        )

        AutomatedEmailSetting.objects.get_or_create(
            studio=studio,
            trigger=item["trigger"],
            defaults={
                "enabled": True,
                "template": template,
                "sender_type": (
                    AutomatedEmailSetting.SenderType.NO_REPLY
                ),
                "send_to_guardians": True,
                "send_to_students": False,
                "delay_minutes": 0,
            },
        )


def sender_address_for_campaign(
    campaign,
):
    if (
        campaign.sender_type
        == EmailCampaign.SenderType.INFO
    ):
        return (
            "Encore Performance Suite "
            "<info@encoreperformancesuite.com>"
        )

    return (
        "Encore Performance Suite "
        "<no-reply@encoreperformancesuite.com>"
    )


def _add_recipient(
    bucket,
    *,
    email,
    display_name="",
    recipient_type,
    source_key="",
):
    email = (
        email
        or ""
    ).strip().lower()

    if not email:
        return

    if email not in bucket:
        bucket[email] = {
            "email": email,
            "display_name": display_name,
            "recipient_type": recipient_type,
            "source_key": source_key,
        }


def _add_guardian_recipients_for_students(
    bucket,
    students,
):
    student_ids = [
        student.pk
        for student in students
        if student.pk
    ]

    guardians = (
        Guardian.objects
        .filter(
            family__students__id__in=student_ids,
            family__students__is_active=True,
            is_active=True,
        )
        .distinct()
    )

    for guardian in guardians:
        _add_recipient(
            bucket,
            email=guardian.email,
            display_name=(
                f"{guardian.first_name} "
                f"{guardian.last_name}"
            ).strip(),
            recipient_type=(
                EmailCampaignRecipient.RecipientType.GUARDIAN
            ),
            source_key=(
                f"guardian:{guardian.pk}"
            ),
        )

    family_ids = {
        student.family_id
        for student in students
        if student.family_id
    }

    from families.models import Family

    families = Family.objects.filter(
        pk__in=family_ids,
        is_active=True,
    )

    for family in families:
        label = (
            family.family_name
            or (
                f"{family.primary_contact_first_name} "
                f"{family.primary_contact_last_name}"
            ).strip()
        )

        _add_recipient(
            bucket,
            email=family.primary_email,
            display_name=label,
            recipient_type=(
                EmailCampaignRecipient.RecipientType.GUARDIAN
            ),
            source_key=(
                f"family:{family.pk}:primary"
            ),
        )

        _add_recipient(
            bucket,
            email=family.secondary_email,
            display_name=label,
            recipient_type=(
                EmailCampaignRecipient.RecipientType.GUARDIAN
            ),
            source_key=(
                f"family:{family.pk}:secondary"
            ),
        )


def _add_student_recipients(
    bucket,
    students,
):
    for student in students:
        email = (
            student.user.email
            if student.user_id
            and student.user
            else ""
        )

        _add_recipient(
            bucket,
            email=email,
            display_name=(
                f"{student.first_name} "
                f"{student.last_name}"
            ).strip(),
            recipient_type=(
                EmailCampaignRecipient.RecipientType.STUDENT
            ),
            source_key=(
                f"student:{student.pk}"
            ),
        )


def _active_admin_users(studio):
    User = get_user_model()

    return (
        User.objects
        .filter(
            studio_memberships__studio=studio,
            studio_memberships__role="administrator",
            studio_memberships__is_active=True,
            is_active=True,
        )
        .distinct()
        .order_by(
            "last_name",
            "first_name",
            "email",
        )
    )


def _add_instructor_recipients(bucket, instructors):
    for instructor in instructors:
        email = (
            instructor.email
            or (
                instructor.user.email
                if instructor.user_id and instructor.user
                else ""
            )
        )

        _add_recipient(
            bucket,
            email=email,
            display_name=instructor.full_name,
            recipient_type=EmailCampaignRecipient.RecipientType.INSTRUCTOR,
            source_key=f"instructor:{instructor.pk}",
        )


def _add_admin_recipients(bucket, admins):
    for admin in admins:
        _add_recipient(
            bucket,
            email=admin.email,
            display_name=admin.get_full_name() or admin.email,
            recipient_type=EmailCampaignRecipient.RecipientType.ADMIN,
            source_key=f"admin:{admin.pk}",
        )


def resolve_recipient_selection(
    studio,
    selection,
    *,
    send_to_students=False,
):
    bucket = {}

    selection = selection if isinstance(selection, dict) else {}
    groups = selection.get("groups", {})
    if not isinstance(groups, dict):
        groups = {}

    all_selected = bool(selection.get("all"))

    all_students = (
        Student.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "family",
            "user",
        )
    )

    def id_set(key):
        return {
            int(value)
            for value in groups.get(key, [])
            if str(value).isdigit()
        }

    selected_student_ids = id_set("students")
    selected_class_ids = id_set("classes")
    instructor_student_ids = id_set("instructor_students")
    direct_instructor_ids = id_set("instructors")
    admin_ids = id_set("admins")

    student_ids = set(selected_student_ids)

    if selected_class_ids:
        student_ids.update(
            all_students
            .filter(
                enrollments__class_instance_id__in=selected_class_ids,
                enrollments__status=Enrollment.Status.ACTIVE,
            )
            .values_list("id", flat=True)
        )

    if instructor_student_ids:
        instructor_classes = (
            Class.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .filter(
                Q(instructor_id__in=instructor_student_ids)
                | Q(
                    assistant_instructor_id__in=instructor_student_ids
                )
            )
        )

        student_ids.update(
            all_students
            .filter(
                enrollments__class_instance__in=instructor_classes,
                enrollments__status=Enrollment.Status.ACTIVE,
            )
            .values_list("id", flat=True)
        )

    if all_selected:
        student_ids.update(
            all_students.values_list(
                "id",
                flat=True,
            )
        )

    if student_ids:
        students = list(
            all_students.filter(
                id__in=student_ids,
            )
        )

        _add_guardian_recipients_for_students(
            bucket,
            students,
        )

        if send_to_students:
            _add_student_recipients(
                bucket,
                students,
            )

    if direct_instructor_ids or all_selected:
        instructors = (
            Instructor.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .select_related("user")
        )

        if not all_selected:
            instructors = instructors.filter(
                id__in=direct_instructor_ids,
            )

        _add_instructor_recipients(
            bucket,
            instructors,
        )

    if admin_ids or all_selected:
        admins = _active_admin_users(
            studio
        )

        if not all_selected:
            admins = admins.filter(
                id__in=admin_ids,
            )

        _add_admin_recipients(
            bucket,
            admins,
        )

    suppressed = set(
        EmailSuppression.objects
        .filter(
            studio=studio,
            is_active=True,
            email__in=list(bucket.keys()),
        )
        .values_list(
            "email",
            flat=True,
        )
    )

    return [
        {
            **recipient,
            "suppressed": recipient["email"] in suppressed,
        }
        for recipient in bucket.values()
    ]


def resolve_campaign_recipients(
    campaign,
):
    if campaign.recipient_selection:
        return resolve_recipient_selection(
            campaign.studio,
            campaign.recipient_selection,
            send_to_students=campaign.send_to_students,
        )

    bucket = {}

    if (
        campaign.recipient_mode
        == EmailCampaign.RecipientMode.INSTRUCTORS
    ):
        instructors = campaign.selected_instructors.all()

        if not instructors.exists():
            instructors = Instructor.objects.filter(
                studio=campaign.studio,
                is_active=True,
            )

        for instructor in instructors:
            email = (
                instructor.email
                or (
                    instructor.user.email
                    if instructor.user_id
                    and instructor.user
                    else ""
                )
            )

            _add_recipient(
                bucket,
                email=email,
                display_name=instructor.full_name,
                recipient_type=(
                    EmailCampaignRecipient.RecipientType.INSTRUCTOR
                ),
                source_key=(
                    f"instructor:{instructor.pk}"
                ),
            )

    else:
        students = Student.objects.filter(
            studio=campaign.studio,
            is_active=True,
        ).select_related(
            "family",
            "user",
        )

        if (
            campaign.recipient_mode
            == EmailCampaign.RecipientMode.CLASSES
        ):
            students = students.filter(
                enrollments__class_instance__in=(
                    campaign.selected_classes.all()
                ),
                enrollments__status=Enrollment.Status.ACTIVE,
            ).distinct()

        elif (
            campaign.recipient_mode
            == EmailCampaign.RecipientMode.INSTRUCTOR_CLASSES
        ):
            instructors = campaign.selected_instructors.all()

            classes = Class.objects.filter(
                studio=campaign.studio,
                is_active=True,
            ).filter(
                Q(instructor__in=instructors)
                | Q(
                    assistant_instructor__in=instructors
                )
            )

            students = students.filter(
                enrollments__class_instance__in=classes,
                enrollments__status=Enrollment.Status.ACTIVE,
            ).distinct()

        if campaign.send_to_guardians:
            _add_guardian_recipients_for_students(
                bucket,
                list(students),
            )

        if campaign.send_to_students:
            _add_student_recipients(
                bucket,
                list(students),
            )

    suppressed = set(
        EmailSuppression.objects
        .filter(
            studio=campaign.studio,
            is_active=True,
            email__in=list(
                bucket.keys()
            ),
        )
        .values_list(
            "email",
            flat=True,
        )
    )

    return [
        {
            **recipient,
            "suppressed": (
                recipient["email"]
                in suppressed
            ),
        }
        for recipient in bucket.values()
    ]


def build_campaign_body(
    campaign,
):
    html_body = campaign.html_body

    if (
        campaign.signature_id
        and campaign.signature
    ):
        signature_html = (
            campaign.signature.body
            .replace(
                "\n",
                "<br>",
            )
        )

        html_body = (
            f"{html_body}"
            f"<hr style='margin:24px 0;border:0;"
            f"border-top:1px solid #e5e7eb;'>"
            f"<div>{signature_html}</div>"
        )

    text_body = (
        campaign.text_body
        or strip_tags(
            campaign.html_body
        )
    )

    if (
        campaign.signature_id
        and campaign.signature
    ):
        text_body = (
            f"{text_body}\n\n"
            f"{campaign.signature.body}"
        )

    return (
        html_body,
        text_body,
    )


@transaction.atomic
def materialize_campaign_recipients(
    campaign,
):
    recipient_rows = resolve_campaign_recipients(
        campaign
    )

    campaign.recipients.all().delete()

    for recipient in recipient_rows:
        EmailCampaignRecipient.objects.create(
            campaign=campaign,
            email=recipient["email"],
            display_name=recipient[
                "display_name"
            ],
            recipient_type=recipient[
                "recipient_type"
            ],
            source_key=recipient[
                "source_key"
            ],
            status=(
                EmailCampaignRecipient.Status.SUPPRESSED
                if recipient["suppressed"]
                else EmailCampaignRecipient.Status.QUEUED
            ),
        )

    campaign.total_recipients = len(
        recipient_rows
    )

    campaign.save(
        update_fields=[
            "total_recipients",
            "updated_at",
        ]
    )

    return campaign.recipients.all()


def refresh_campaign_counts(
    campaign,
):
    recipients = campaign.recipients.all()

    campaign.total_recipients = recipients.count()

    campaign.sent_count = recipients.filter(
        status__in=[
            EmailCampaignRecipient.Status.SENT,
            EmailCampaignRecipient.Status.DELIVERED,
            EmailCampaignRecipient.Status.OPENED,
            EmailCampaignRecipient.Status.CLICKED,
            EmailCampaignRecipient.Status.DELAYED,
        ]
    ).count()

    campaign.delivered_count = recipients.filter(
        status__in=[
            EmailCampaignRecipient.Status.DELIVERED,
            EmailCampaignRecipient.Status.OPENED,
            EmailCampaignRecipient.Status.CLICKED,
        ]
    ).count()

    campaign.opened_count = recipients.filter(
        status__in=[
            EmailCampaignRecipient.Status.OPENED,
            EmailCampaignRecipient.Status.CLICKED,
        ]
    ).count()

    campaign.clicked_count = recipients.filter(
        status=EmailCampaignRecipient.Status.CLICKED,
    ).count()

    campaign.failed_count = recipients.filter(
        status=EmailCampaignRecipient.Status.FAILED,
    ).count()

    campaign.bounced_count = recipients.filter(
        status=EmailCampaignRecipient.Status.BOUNCED,
    ).count()

    campaign.complaint_count = recipients.filter(
        status=EmailCampaignRecipient.Status.COMPLAINT,
    ).count()

    campaign.save(
        update_fields=[
            "total_recipients",
            "sent_count",
            "delivered_count",
            "opened_count",
            "clicked_count",
            "failed_count",
            "bounced_count",
            "complaint_count",
            "updated_at",
        ]
    )


def send_campaign(
    campaign,
):
    if not campaign.recipients.exists():
        materialize_campaign_recipients(
            campaign
        )

    campaign.status = (
        EmailCampaign.Status.SENDING
    )

    campaign.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    html_body, text_body = (
        build_campaign_body(
            campaign
        )
    )

    sent = 0
    failed = 0

    for recipient in (
        campaign.recipients
        .filter(
            status__in=[
                EmailCampaignRecipient.Status.QUEUED,
                EmailCampaignRecipient.Status.FAILED,
            ]
        )
    ):
        try:
            result = send_email(
                to=[
                    recipient.email,
                ],
                subject=campaign.subject,
                html_body=html_body,
                text_body=text_body,
                from_address=(
                    sender_address_for_campaign(
                        campaign
                    )
                ),
                tags={
                    "campaign_id": campaign.pk,
                    "studio_id": (
                        campaign.studio_id
                    ),
                    "recipient_id": (
                        recipient.pk
                    ),
                },
            )

        except EncoreEmailError as exc:
            recipient.status = (
                EmailCampaignRecipient.Status.FAILED
            )

            recipient.error_message = str(
                exc
            )

            recipient.save(
                update_fields=[
                    "status",
                    "error_message",
                ]
            )

            failed += 1
            continue

        recipient.status = (
            EmailCampaignRecipient.Status.SENT
        )

        recipient.ses_message_id = (
            result.message_id
        )

        recipient.sent_at = timezone.now()

        recipient.save(
            update_fields=[
                "status",
                "ses_message_id",
                "sent_at",
            ]
        )

        EmailEvent.objects.create(
            recipient=recipient,
            event_type=EmailEvent.EventType.SEND,
            occurred_at=recipient.sent_at,
            payload={
                "source": "encore_send",
                "message_id": (
                    result.message_id
                ),
            },
        )

        sent += 1

    campaign.sent_at = timezone.now()

    if sent and failed:
        campaign.status = (
            EmailCampaign.Status.PARTIAL_FAILED
        )

    elif sent:
        campaign.status = (
            EmailCampaign.Status.SENT
        )

    else:
        campaign.status = (
            EmailCampaign.Status.FAILED
        )

    campaign.save(
        update_fields=[
            "status",
            "sent_at",
            "updated_at",
        ]
    )

    refresh_campaign_counts(
        campaign
    )

    return {
        "sent": sent,
        "failed": failed,
        "suppressed": (
            campaign.recipients.filter(
                status=(
                    EmailCampaignRecipient.Status.SUPPRESSED
                )
            ).count()
        ),
    }


def _event_status_map():
    return {
        "SEND": (
            EmailCampaignRecipient.Status.SENT,
            EmailEvent.EventType.SEND,
        ),
        "DELIVERY": (
            EmailCampaignRecipient.Status.DELIVERED,
            EmailEvent.EventType.DELIVERY,
        ),
        "OPEN": (
            EmailCampaignRecipient.Status.OPENED,
            EmailEvent.EventType.OPEN,
        ),
        "CLICK": (
            EmailCampaignRecipient.Status.CLICKED,
            EmailEvent.EventType.CLICK,
        ),
        "BOUNCE": (
            EmailCampaignRecipient.Status.BOUNCED,
            EmailEvent.EventType.BOUNCE,
        ),
        "COMPLAINT": (
            EmailCampaignRecipient.Status.COMPLAINT,
            EmailEvent.EventType.COMPLAINT,
        ),
        "REJECT": (
            EmailCampaignRecipient.Status.FAILED,
            EmailEvent.EventType.REJECT,
        ),
        "RENDERING_FAILURE": (
            EmailCampaignRecipient.Status.FAILED,
            EmailEvent.EventType.RENDERING_FAILURE,
        ),
        "DELIVERY_DELAY": (
            EmailCampaignRecipient.Status.DELAYED,
            EmailEvent.EventType.DELIVERY_DELAY,
        ),
        "SUBSCRIPTION": (
            None,
            EmailEvent.EventType.SUBSCRIPTION,
        ),
    }


def record_ses_event(
    payload,
):
    detail = payload.get(
        "detail",
        payload,
    )

    event_type = (
        detail.get(
            "eventType"
        )
        or detail.get(
            "event_type"
        )
        or ""
    ).upper()

    mail = detail.get(
        "mail",
        {},
    )

    message_id = (
        mail.get(
            "messageId"
        )
        or detail.get(
            "messageId"
        )
        or ""
    )

    if not message_id:
        return None

    recipient = (
        EmailCampaignRecipient.objects
        .filter(
            ses_message_id=message_id,
        )
        .select_related(
            "campaign",
            "campaign__studio",
        )
        .first()
    )

    if recipient is None:
        return None

    mapping = _event_status_map().get(
        event_type
    )

    if mapping is None:
        return recipient

    new_status, internal_event = mapping

    occurred_at = timezone.now()

    EmailEvent.objects.create(
        recipient=recipient,
        event_type=internal_event,
        occurred_at=occurred_at,
        payload=payload,
    )

    update_fields = []

    if new_status is not None:
        recipient.status = new_status
        update_fields.append(
            "status"
        )

    timestamp_field = {
        "DELIVERY": "delivered_at",
        "OPEN": "opened_at",
        "CLICK": "clicked_at",
        "BOUNCE": "bounced_at",
        "COMPLAINT": "complained_at",
    }.get(
        event_type
    )

    if timestamp_field:
        setattr(
            recipient,
            timestamp_field,
            occurred_at,
        )

        update_fields.append(
            timestamp_field
        )

    if update_fields:
        recipient.save(
            update_fields=update_fields
        )

    if event_type in {
        "BOUNCE",
        "COMPLAINT",
    }:
        reason = (
            EmailSuppression.Reason.HARD_BOUNCE
            if event_type == "BOUNCE"
            else EmailSuppression.Reason.COMPLAINT
        )

        EmailSuppression.objects.update_or_create(
            studio=recipient.campaign.studio,
            email=recipient.email.lower(),
            defaults={
                "reason": reason,
                "is_active": True,
            },
        )

    refresh_campaign_counts(
        recipient.campaign
    )

    return recipient
