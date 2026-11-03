"""Send one activation alert to each active studio administrator per Stripe environment."""
import logging
from communications.studio_email import send_studio_email
from django.utils.html import escape
from django.conf import settings
from django.urls import reverse
from communications.models import WorkspaceNotification
from communications.notification_services import administrator_users

logger = logging.getLogger(__name__)


def notify_payments_activated(subscription, status):
    """Call only after a fresh authenticated Stripe API status check."""
    if not status.get('ready') or not status.get('account_id'):
        return 0
    studio = subscription.studio
    mode = status['mode']
    url = reverse('billing:stripe_activation_page', kwargs={'studio_slug': studio.slug})
    sent = 0
    for user in administrator_users(studio):
        key = f'stripe-payments-active:{mode}:{status["account_id"]}:user:{user.pk}'
        notification, created = WorkspaceNotification.objects.get_or_create(
            studio=studio, user=user, dedupe_key=key,
            defaults={
                'category': WorkspaceNotification.Category.SYSTEM,
                'kind': 'stripe_payments_active',
                'title': f'{studio.name} payments are active',
                'message': ('Stripe has enabled card payments for your studio. '
                            'Families can now make online payments through Encore.'),
                'action_url': url,
            },
        )
        if not created:
            continue
        sent += 1
        if not user.email:
            continue
        try:
            body = (f'Good news! Stripe has enabled card payments for {studio.name}.\n\n'
                    'Your studio can now accept online payments in Encore.\n'
                    f'See your status in Encore: {getattr(settings, "ENCORE_PUBLIC_BASE_URL", "").rstrip("/")}{url}\n\n'
                    'You can review your payment account in Encore at any time.')
            send_studio_email(
                studio=studio, to=[user.email],
                subject=f'Encore: {studio.name} payments are connected',
                html_body=f'<div style="white-space:pre-line">{escape(body)}</div>',
                text_body=body,
                tags={'message_type':'stripe_activation'},
            )
        except Exception:
            logger.exception('Unable to send Stripe activation email for studio %s to user %s', studio.pk, user.pk)
    return sent
