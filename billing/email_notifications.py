"""Family billing email outbox. Enqueue only; explicit worker performs external send.

No billing transaction is ever rolled back or payment duplicated due to SES failure.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.conf import settings
from families.models import Guardian
from .models import BillingEmailDelivery, Charge, Payment, RecurringChargeSchedule

logger = logging.getLogger(__name__)


def queue_billing_notice(account, event_type, event_key, subject, body):
    """Idempotent per recipient, even if webhook/job is replayed."""
    recipients = set()
    for guardian in Guardian.objects.filter(family=account.family, is_active=True).select_related('user'):
        address = (getattr(guardian.user, 'email', '') or guardian.email or '').strip().lower()
        if address:
            recipients.add(address)
    for address in recipients:
        BillingEmailDelivery.objects.get_or_create(
            account=account, event_key=str(event_key)[:200], recipient=address,
            defaults={'event_type':event_type, 'subject':subject[:255], 'body':body})


def queue_charge_notice(charge_id):
    charge = Charge.objects.select_related('account__studio','account__family').filter(pk=charge_id).first()
    if not charge or charge.status != Charge.Status.OPEN or charge.amount <= 0:
        return
    # Imported opening balances, historic records and draft charges must not
    # trigger new invoice emails. Recurring tuition is issued by the daily job.
    if not charge.recurring_schedule_id or not charge.due_date or charge.due_date < timezone.localdate():
        return
    studio=charge.account.studio
    body=(f"{studio.name} has issued a tuition charge: {charge.description}.\n"
          f"Amount: ${charge.amount:.2f}\nDue: {charge.due_date}\n"
          "Sign in to your family billing portal to review or pay.")
    queue_billing_notice(charge.account, 'invoice', f'invoice:{charge.pk}',
                         f'{studio.name} — Tuition invoice', body)


def queue_payment_notice(payment_id):
    payment=Payment.objects.select_related('account__studio').filter(pk=payment_id).first()
    if not payment:
        return
    if payment.status != Payment.Status.SUCCEEDED or payment.amount <= 0:
        return
    studio=payment.account.studio
    queue_billing_notice(payment.account,'receipt',f'receipt:{payment.pk}',
                         f'{studio.name} — Payment receipt',
                         f"Payment received: ${payment.amount:.2f}\n"
                         f"Payment method: {payment.get_method_display()}\n"
                         f"Date: {timezone.localtime(payment.paid_at):%B %d, %Y}\n"
                         "Thank you. View your family billing account for payment history.")


def queue_upcoming_tuition(as_of=None, days_ahead=5, dry_run=True):
    today=as_of or timezone.localdate()
    day=today+timedelta(days=days_ahead)
    schedules=(RecurringChargeSchedule.objects.filter(is_active=True,next_charge_date=day,
        amount__gt=Decimal('0.00'), account__is_active=True)
        .select_related('account__studio','account__family','season'))
    results={'eligible':0,'queued':0}
    for schedule in schedules.iterator():
        if schedule.end_date and schedule.end_date < day: continue
        results['eligible']+=1
        if dry_run: continue
        event_key=f'upcoming:{schedule.pk}:{day}'
        before=BillingEmailDelivery.objects.filter(account=schedule.account,event_key=event_key).count()
        queue_billing_notice(schedule.account,'upcoming',event_key,
           f'{schedule.account.studio.name} — Upcoming tuition',
           f'Tuition of ${schedule.amount:.2f} is scheduled for {day:%B %d, %Y}.\n'
           'Review your family billing account for details and payment options.')
        results['queued']+=BillingEmailDelivery.objects.filter(account=schedule.account,event_key=event_key).count()-before
    return results


def dispatch_billing_emails(limit=100, retry_failed=False):
    from communications.studio_email import send_studio_email
    qs=BillingEmailDelivery.objects.filter(status__in=['pending','failed'] if retry_failed else ['pending']).order_by('created_at')
    counters={'sent':0,'failed':0}
    for pk in qs.values_list('pk',flat=True)[:limit]:
        with transaction.atomic():
            item=BillingEmailDelivery.objects.select_for_update().select_related('account__studio').get(pk=pk)
            if item.status not in (('pending','failed') if retry_failed else ('pending',)): continue
            item.status='sending';item.attempts+=1
            item.save(update_fields=['status','attempts'])
        try:
            result=send_studio_email(studio=item.account.studio,to=[item.recipient],subject=item.subject,
                html_body='<div style="font-family:Arial,sans-serif;line-height:1.6"><h2>'+escape(item.account.studio.name)+'</h2><p>'+escape(item.body).replace('\n','<br>')+'</p></div>',
                text_body=item.body,tags={'message_type':'billing','billing_event':item.event_type})
        except Exception as exc:
            logger.exception('Billing email delivery failed: id=%s',item.pk)
            item.status='failed';item.error=str(exc)[:1500];counters['failed']+=1
            item.save(update_fields=['status','error'])
        else:
            item.status='sent';item.sent_at=timezone.now();item.provider_message_id=getattr(result,'message_id','')
            item.error='';item.save(update_fields=['status','sent_at','provider_message_id','error'])
            counters['sent']+=1
    return counters
