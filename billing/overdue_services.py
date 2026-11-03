"""Overdue milestone notifications. Run explicitly via process_overdue_tuition.

No charges, enrollment or attendance states are changed by this job.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from html import escape
from django.utils import timezone
from django.urls import reverse
from .models import Charge, StudioTuitionSettings, BillingNoticeDelivery, FamilyBillingHold, FamilyAutoPayAttempt, FamilyBillingAction

log = logging.getLogger(__name__)

DEFAULT_NOTICES = {
    "overdue": ("Tuition payment overdue", "Your tuition charge of ${amount} was due {due_date}. Please review your family billing account. Your studio allows {grace_days} calendar days after the due date before account review."),
    "grace_warning": ("Tuition grace period nearly over", "Your tuition balance of ${amount} remains overdue. The grace period ends {grace_end}. Please pay or contact the studio."),
    "grace_expired": ("Tuition account requires attention", "Your tuition balance of ${amount} remains unpaid after the grace period ending {grace_end}. Your account has been referred to studio administration for review. Your student has NOT been automatically removed from classes. Please pay or contact the studio."),
    "resolved": ("Tuition balance resolved", "The previously overdue tuition charge dated {due_date} has been paid. Thank you."),
}
TEMPLATE_FIELDS = {"overdue":"overdue_template_id", "grace_warning":"grace_warning_template_id", "grace_expired":"grace_expired_template_id", "resolved":"resolved_template_id"}

def _render(studio, policy, charge, event, grace_end, grace_days):
    subject, text = DEFAULT_NOTICES[event]
    tid = getattr(policy, TEMPLATE_FIELDS[event], None) if policy else None
    if tid:
        from communications.models import EmailTemplate
        template = EmailTemplate.objects.filter(pk=tid, studio=studio, is_active=True).first()
        if template:
            subject = template.subject
            text = template.text_body or template.html_body
    # Plain-text safe token substitution. HTML is escaped before SES send.
    fields = {"studio_name": studio.name, "amount":f"{charge.balance_remaining:.2f}",
              "due_date":str(charge.due_date), "grace_days":str(grace_days),
              "grace_end":str(grace_end), "family_name": str(charge.account.family),
              "charge_description":charge.description}
    for key, value in fields.items():
        subject=subject.replace("{"+key+"}",str(value))
        text=text.replace("{"+key+"}",str(value))
    return subject, text

def _recipients(account):
    from families.models import Guardian
    return list(Guardian.objects.filter(family=account.family,is_active=True,user__isnull=False,user__is_active=True)
                .select_related("user"))

def process_overdue(as_of=None, dry_run=True, studio_id=None):
    today=as_of or timezone.localdate()
    results={"eligible":0,"sent":0,"skipped":0,"failed":0,"reviews":0}
    charges=(Charge.objects.filter(charge_type=Charge.ChargeType.TUITION, due_date__isnull=False,
                due_date__lt=today, account__is_active=True)
             .exclude(status__in=[Charge.Status.DRAFT,Charge.Status.VOID])
             .select_related("account","account__studio","account__family","recurring_schedule__tuition_plan").order_by("pk"))
    if studio_id: charges=charges.filter(account__studio_id=studio_id)
    for charge in charges.iterator():
        settings_obj=StudioTuitionSettings.objects.filter(studio_id=charge.account.studio_id).first()
        if settings_obj is None: continue
        # Each recurring tuition charge uses the policy that generated it.
        # For historical/manual tuition without a schedule, use the studio's
        # default tuition policy; the legacy studio field is only a fallback.
        schedule = charge.recurring_schedule
        policy = schedule.tuition_plan if schedule else settings_obj.default_tuition_plan
        grace_days = (policy.grace_period_days if policy.grace_period_enabled else 0) if policy else settings_obj.overdue_grace_days
        end=charge.due_date+timedelta(days=grace_days)
        # Never escalate an unsettled ACH/card payment: pending does not mean failed.
        if FamilyAutoPayAttempt.objects.filter(charge=charge, status__in=[
            "pending", "submitted", "processing", "requires_action", "requires_confirmation"
        ]).exists():
            results["skipped"] += 1
            continue
        # Admin defer is explicit and survives daily scans. A renewed date may
        # also be managed with a charge due-date extension.
        deferred = False
        last_action = FamilyBillingAction.objects.filter(account=charge.account).first()
        if last_action and last_action.action in {"defer", "retain"}:
            if last_action.action == "retain":
                deferred = True
            else:
                from datetime import date
                try:
                    deferred = today <= date.fromisoformat(last_action.details.get("review_date", ""))
                except (ValueError, TypeError):
                    deferred = False
        previous=BillingNoticeDelivery.objects.filter(charge_id=charge.pk,event__in=["overdue","grace_warning","grace_expired"],status="sent").exists()
        if charge.balance_remaining<=Decimal("0.00"):
            event="resolved" if previous else None
        elif today>end:
            event="grace_expired"
        elif grace_days > 0 and today>=end-timedelta(days=2) and today>charge.due_date:
            event="grace_warning"
        else:
            event="overdue"
        # Review eligibility is independent of email settings and notice deduplication.
        # Every overdue family goes to human review, never automatic withdrawal.
        if not dry_run and charge.balance_remaining > Decimal("0.00") and today > end and not deferred:
            hold, created = FamilyBillingHold.objects.get_or_create(
                account=charge.account,
                defaults={"status": "review", "reason": "Tuition past billing-policy grace period."},
            )
            if created:
                results["reviews"] += 1
            elif hold.status == "released" and hold.reason == "Outstanding account balance paid.":
                hold.status = "review"
                hold.reason = "New tuition overdue past billing-policy grace period."
                hold.save(update_fields=["status", "reason", "updated_at"])
                results["reviews"] += 1
        # Re-evaluate fully paid balances even when no previous milestone was
        # emitted. Reviews must not remain indefinitely for settled balances.
        if not dry_run and charge.account.balance <= Decimal("0.00"):
            FamilyBillingHold.objects.filter(account=charge.account, status__in=["review", "active"]).update(
                status="released", reason="Outstanding account balance paid.")
        if deferred and event == "grace_expired":
            results["skipped"] += 1
            continue
        if event is None: continue
        if BillingNoticeDelivery.objects.filter(charge=charge,event=event,status="sent").exists():
            results["skipped"]+=1;continue
        results["eligible"]+=1
        if dry_run: continue
        if event=="resolved":
            if charge.account.balance <= Decimal("0.00"):
                FamilyBillingHold.objects.filter(account=charge.account,status="review").update(status="released",reason="Outstanding account balance paid.")
        subject, body = _render(charge.account.studio,policy,charge,event,end,grace_days)
        # Disabled means NO outgoing email, but safely keep in-app notice.
        try:
            guardians=_recipients(charge.account)
            # Optional reminders follow the policy toggle; grace expiry must
            # still notify the family of administrator review.
            # Critical review alerts are always sent. Optional emails are
            # independently configured per tuition policy. A disabled grace
            # period never generates a grace-warning milestone.
            if event == "grace_expired":
                send_email = True
            elif policy is None:
                send_email = bool(settings_obj.overdue_email_enabled) if event != "resolved" else True
            else:
                send_email = {
                    "overdue": policy.overdue_notice_enabled,
                    "grace_warning": policy.grace_warning_notice_enabled and policy.grace_period_enabled,
                    "resolved": policy.resolved_notice_enabled,
                }.get(event, False)
            if send_email:
                from communications.studio_email import send_studio_email
                emails=sorted({(g.user.email or g.email or "").strip() for g in guardians if (g.user.email or g.email)})
                for email in emails:
                    send_studio_email(studio=charge.account.studio,to=[email],subject=subject,
                        html_body="<p>"+escape(body).replace("\n","<br>")+"</p>",text_body=body,
                        tags={"message_type":"family_overdue","event":event})
            from communications.models import WorkspaceNotification
            from communications.notification_services import create_workspace_notification
            for g in guardians:
                create_workspace_notification(studio=charge.account.studio,user=g.user,
                    category=WorkspaceNotification.Category.SYSTEM,kind="tuition_"+event,
                    title=subject[:200],message=body,
                    action_url=reverse("billing:family_payments",kwargs={"studio_slug":charge.account.studio.slug}),
                    dedupe_key=f"tuition-{charge.pk}-{event}-{g.user_id}")
            BillingNoticeDelivery.objects.update_or_create(charge=charge,event=event,
                defaults={"status":"sent","error":"","sent_at":timezone.now()})
            results["sent"]+=1
        except Exception as exc:
            log.exception("Overdue notice failed charge=%s event=%s",charge.pk,event)
            BillingNoticeDelivery.objects.update_or_create(charge=charge,event=event,
                defaults={"status":"failed","error":str(exc)[:1000]})
            results["failed"]+=1
    return results
