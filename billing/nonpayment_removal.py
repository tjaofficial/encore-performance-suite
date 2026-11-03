"""Administrator-authorized nonpayment withdrawal: never delete financial/attendance history."""
import logging
from django.urls import reverse
from django.utils.html import escape
from communications.notification_services import create_workspace_notification, administrator_users
from communications.models import WorkspaceNotification
from communications.studio_email import send_studio_email
from families.models import Guardian

logger = logging.getLogger(__name__)


def notify_nonpayment_removal(*, studio, account, removals, administrator_id):
    """Post-commit notifications. Failures are logged, not allowed to undo removal."""
    from django.contrib.auth import get_user_model
    admin = get_user_model().objects.filter(pk=administrator_id).first()
    family_link = reverse('billing:family_payments', kwargs={'studio_slug': studio.slug})
    review_link = reverse('billing:studio_billing_reviews', kwargs={'studio_slug': studio.slug})
    guardian_users = {g.user_id: g.user for g in Guardian.objects.filter(
        family_id=account.family_id, is_active=True, user__isnull=False
    ).select_related('user')}
    for enrollment in removals:
        student = enrollment.student
        dance_class = enrollment.class_instance
        display_student = f'{student.first_name} {student.last_name}'.strip()
        title = f'Enrollment update: {display_student}'
        parent_body = (f'{display_student} has been withdrawn from {dance_class.name} by {studio.name} '
                       'because tuition remains unpaid. Previous payments, records, and attendance remain on file. '
                       'Outstanding charges are still payable. Please contact the studio if you have questions.')
        teacher_body = (f'{display_student} was removed from {dance_class.name} due to unpaid tuition. '
                        'Please use the updated roster for future classes. Past attendance is unchanged. '
                        'For questions, contact the studio administrator.')
        for guardian_id, user in guardian_users.items():
            create_workspace_notification(
                studio=studio, user=user, category=WorkspaceNotification.Category.SYSTEM,
                kind='nonpayment_enrollment_removed', title=title, message=parent_body,
                action_url=family_link,
                dedupe_key=f'nonpayment-removal-{enrollment.pk}-{enrollment.updated_at.timestamp()}-{guardian_id}',
            )
        teacher_users = {}
        for instructor in (getattr(dance_class, 'instructor', None), getattr(dance_class, 'assistant_instructor', None)):
            if instructor is not None and getattr(instructor, 'user_id', None):
                teacher_users[instructor.user_id] = instructor.user
        for user_id, user in teacher_users.items():
            create_workspace_notification(
                studio=studio, user=user, category=WorkspaceNotification.Category.SYSTEM,
                kind='nonpayment_roster_change', title=title, message=teacher_body,
                action_url=review_link,
                dedupe_key=f'nonpayment-teacher-{enrollment.pk}-{enrollment.updated_at.timestamp()}-{user_id}',
            )
        for user in administrator_users(studio):
            create_workspace_notification(
                studio=studio, user=user, category=WorkspaceNotification.Category.SYSTEM,
                kind='nonpayment_removal_audit', title=title,
                message=f'{admin or "A studio administrator"} withdrew {display_student} from {dance_class.name} for unpaid tuition.',
                action_url=review_link,
                dedupe_key=f'nonpayment-admin-{enrollment.pk}-{enrollment.updated_at.timestamp()}-{user.pk}',
            )
        destinations = {}
        for user in list(guardian_users.values()):
            if user.email:
                destinations[user.email.strip().lower()] = parent_body
        for user in teacher_users.values():
            if user.email:
                destinations[user.email.strip().lower()] = teacher_body
        for email, body in destinations.items():
            try:
                send_studio_email(studio=studio, to=[email], subject=title,
                                  text_body=body, html_body='<p>'+escape(body)+'</p>')
            except Exception:
                logger.exception('Enrollment removal notice could not be emailed: enrollment=%s', enrollment.pk)
