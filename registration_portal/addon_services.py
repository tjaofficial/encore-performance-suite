"""Existing-family class additions. No new registration or household creation.

The quoted adjustment covers *only the remaining part of the current tuition
cycle*. Existing recurring schedules remain the source for subsequent cycles.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from billing.models import Charge, FamilyAccount, Payment, PaymentAllocation, RecurringChargeSchedule, StudioTuitionSettings
from billing.services import calculate_studio_wide_tuition, sync_billing_for_enrollment, weekly_hours_for_class
from classes.models import Class
from enrollments.models import Enrollment
from families.models import Family
from students.models import Student
from .models import PublicRegistrationSession, RegistrationClassHold

CENT = Decimal('0.01')
ZERO = Decimal('0.00')


def is_addon(session):
    return (session.account_data or {}).get('registration_flow') == 'add_classes'


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _month_after(day):
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1, day=1)
    return day.replace(month=day.month + 1, day=1)


def _monthly_cycle(family, season, today):
    from billing.services import next_schedule_date
    candidates = (RecurringChargeSchedule.objects.filter(
        account__family=family, season=season, is_active=True,
        tuition_plan__frequency='monthly',
    ).select_related('tuition_plan').order_by('-universal_tuition','pk'))
    for schedule in candidates:
        anchor = schedule.next_charge_date or schedule.start_date
        if anchor is None:
            continue
        previous = anchor
        following = anchor
        for _ in range(240):
            if following > today:
                if previous >= following:
                    from calendar import monthrange
                    year, month = (following.year - 1, 12) if following.month == 1 else (following.year, following.month - 1)
                    previous = following.replace(year=year, month=month,
                        day=min(following.day, monthrange(year,month)[1]))
                return previous, following
            previous = following
            following = next_schedule_date(schedule, following)
            if following is None:
                break
    start = today.replace(day=1)
    return start, _month_after(start)


def _tuition_by_season(studio, enrollments, added):
    settings_obj = StudioTuitionSettings.objects.filter(studio=studio).first()
    groups = defaultdict(lambda: {'hours': ZERO, 'explicit': ZERO, 'season': None})
    for student_id, cls, override in [*enrollments, *added]:
        group = groups[cls.season_id]
        group['season'] = cls.season
        if override is not None:
            group['explicit'] += Decimal(override)
        elif cls.tuition_amount is not None:
            group['explicit'] += Decimal(cls.tuition_amount)
        elif settings_obj and settings_obj.is_studio_wide:
            group['hours'] += weekly_hours_for_class(cls)
    result = {}
    for season_id, group in groups.items():
        total = group['explicit']
        if settings_obj and settings_obj.is_studio_wide:
            total += calculate_studio_wide_tuition(settings_obj, group['hours'])
        result[season_id] = (group['season'], _money(total))
    return result


def addon_pricing_snapshot(session, *, waitlisted_class_ids=None):
    if not is_addon(session):
        raise ValueError('This is not an existing-family class addition.')
    data = session.account_data or {}
    family = Family.objects.get(pk=data['existing_family_id'], studio=session.studio, is_active=True)
    raw = session.student_data or {}
    students = raw.get('students') or []
    assignments = raw.get('assignments') or {}
    if not students or not any(assignments.values()):
        raise ValueError('Choose at least one new class.')

    added = []
    rows = []
    waitlisted_class_ids = set(waitlisted_class_ids or ())
    existing = list(Enrollment.objects.filter(
        student__family=family, status=Enrollment.Status.ACTIVE,
        class_instance__studio=session.studio, class_instance__season__is_active=True,
    ).select_related('class_instance__season', 'class_instance__tuition_plan').prefetch_related('class_instance__meeting_times'))
    existing_pairs = {(e.student_id, e.class_instance_id) for e in existing}
    base = [(e.student_id, e.class_instance, e.tuition_override) for e in existing]
    for item in students:
        sid = int(item['existing_student_id'])
        student = Student.objects.get(pk=sid, family=family, studio=session.studio, is_active=True)
        key = item['draft_key']
        for cid in assignments.get(key, []):
            cls = Class.objects.filter(pk=int(cid), studio=session.studio, is_active=True,
                season__is_active=True).select_related('season','tuition_plan').prefetch_related('meeting_times').first()
            if cls is None or not cls.registration_open or not cls.season.registration_open:
                raise ValueError('A selected class is no longer available for registration.')
            if (sid, cls.pk) in existing_pairs:
                raise ValueError(f'{student.first_name} is already enrolled in {cls.name}.')
            tuition_settings = StudioTuitionSettings.objects.filter(studio=session.studio).first()
            if cls.tuition_amount is not None and (not cls.tuition_plan or cls.tuition_plan.frequency != 'monthly'):
                raise ValueError(f'{cls.name} must have a monthly billing policy to use the add-classes checkout.')
            if cls.tuition_amount is None and not (tuition_settings and tuition_settings.is_studio_wide):
                raise ValueError(f'{cls.name} does not have a configured monthly tuition price.')
            if cls.tuition_amount is None and (
                not tuition_settings.default_tuition_plan or
                tuition_settings.default_tuition_plan.frequency != 'monthly'
            ):
                raise ValueError('This studio needs a monthly studio-wide tuition policy for prorated class additions.')
            waitlisted = cls.pk in waitlisted_class_ids
            if not waitlisted:
                added.append((sid, cls, None))
            rows.append(dict(student_key=key, student_name=f'{student.first_name} {student.last_name}',
                class_id=cls.pk, class_name=cls.name, class_code=cls.class_id,
                season=cls.season.name, is_full=waitlisted, waitlist=waitlisted,
                tuition=str(cls.tuition_amount or ZERO), registration_fee='0.00',
                due_today='0.00', future_recurring='0.00', studio_wide=cls.tuition_amount is None))

    before = _tuition_by_season(session.studio, base, [])
    after = _tuition_by_season(session.studio, base, added)
    due = ZERO
    today = timezone.localdate()
    changes = []
    for sid, (season, new_total) in after.items():
        old_total = before.get(sid, (season, ZERO))[1]
        delta = _money(max(ZERO, new_total - old_total))
        fraction = Decimal('0')
        if delta and season.start_date <= today <= season.end_date:
            start, end = _monthly_cycle(family, season, today)
            actual_start = max(today, start, season.start_date)
            actual_end = min(end, season.end_date + timedelta(days=1))
            fraction = Decimal(max(0, (actual_end - actual_start).days)) / Decimal(max(1, (end - start).days))
        prorated = _money(delta * fraction)
        due += prorated
        changes.append(dict(season_id=sid, season=season.name,
            previous_monthly=str(old_total), new_monthly=str(new_total),
            monthly_increase=str(delta), adjustment=str(prorated),
            remaining_fraction=str(fraction)))

    result = dict(items=rows, student_totals=[], studio_wide_items=[],
        monthly_changes=changes, previous_monthly_total=str(_money(sum((x[1] for x in before.values()), ZERO))),
        future_recurring_total=str(_money(sum((x[1] for x in after.values()), ZERO))),
        estimated_monthly_total=str(_money(sum((x[1] for x in after.values()), ZERO))),
        due_today=str(_money(due)), currency='USD', addon=True)
    session.pricing_snapshot = result
    session.save(update_fields=['pricing_snapshot','updated_at'])
    return result


@transaction.atomic
def finalize_addon(session, *, stripe_payment_intent_id='', paid_amount=ZERO):
    from .policy_services import registration_policies_satisfied
    from .security import registration_identity_verified
    from .services import _send_registration_confirmation
    session = PublicRegistrationSession.objects.select_for_update().select_related('studio').get(pk=session.pk)
    if session.status == session.Status.COMPLETED:
        return dict(user=session.linked_user, family=session.linked_family,
            students=[session.linked_student], enrollments=[], payment=session.linked_payment)
    from .approval_codes import validate_session as validate_class_codes, consume_session as consume_class_codes
    validate_class_codes(session)
    if not registration_identity_verified(session) or not registration_policies_satisfied(session):
        raise ValueError('Registration identity or policies have not been verified.')
    if session.status not in {session.Status.READY_FOR_PAYMENT, session.Status.PAYMENT_PENDING}:
        raise ValueError('The additional class registration has not reached checkout.')
    old_quote = dict(session.pricing_snapshot or {})
    waitlisted = {int(row['class_id']) for row in old_quote.get('items', []) if row.get('waitlist')}
    latest = addon_pricing_snapshot(session, waitlisted_class_ids=waitlisted)
    if latest['due_today'] != old_quote.get('due_today') or latest['future_recurring_total'] != old_quote.get('future_recurring_total'):
        raise ValueError('Tuition changed during checkout; contact the studio to reconcile payment.')
    due = _money(latest['due_today'])
    if due and (not stripe_payment_intent_id or _money(paid_amount) != due):
        raise ValueError('The full tuition adjustment must be verified as paid.')
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.get(pk=session.account_data['existing_user_id'], is_active=True)
    family = Family.objects.select_for_update().get(pk=session.account_data['existing_family_id'], studio=session.studio)
    account, _ = FamilyAccount.objects.get_or_create(family=family, defaults={'studio': session.studio})
    enrollments = []
    raw = session.student_data or {}
    for item in raw.get('students', []):
        student = Student.objects.get(pk=item['existing_student_id'], family=family, studio=session.studio)
        for cid in (raw.get('assignments') or {}).get(item['draft_key'], []):
            cls = Class.objects.select_for_update().get(pk=cid, studio=session.studio)
            is_waitlisted = int(cid) in waitlisted
            status = Enrollment.Status.WAITLISTED if is_waitlisted else Enrollment.Status.ACTIVE
            enrollment, created = Enrollment.objects.get_or_create(
                student=student, class_instance=cls,
                defaults={'status':status, 'source':Enrollment.Source.ONLINE})
            if not created:
                if enrollment.status in (Enrollment.Status.ACTIVE, Enrollment.Status.WAITLISTED):
                    raise ValueError(f'{student.first_name} already has an enrollment in {cls.name}.')
                enrollment.status, enrollment.source = status, Enrollment.Source.ONLINE
                enrollment.full_clean()
                enrollment.save(update_fields=['status','source','updated_at'])
            if status == Enrollment.Status.ACTIVE:
                # Existing families pay only the prorated tuition difference in
                # this flow; do not accidentally produce an extra registration
                # fee on top of the agreed checkout amount.
                previous_fee_ids = set(Charge.objects.filter(enrollment=enrollment,
                    charge_type=Charge.ChargeType.REGISTRATION).values_list('pk', flat=True))
                sync_billing_for_enrollment(enrollment)
                Charge.objects.filter(enrollment=enrollment, charge_type=Charge.ChargeType.REGISTRATION,
                    status=Charge.Status.OPEN).exclude(pk__in=previous_fee_ids).update(
                        status=Charge.Status.VOID,
                        notes='Registration fee waived for prorated existing-family class addition.')
                # This enrollment starts being billed at the next *future* cycle;
                # the current cycle's partial tuition is captured by our adjustment.
                schedule = RecurringChargeSchedule.objects.filter(enrollment=enrollment, is_active=True).first()
                if schedule:
                    _, next_day = _monthly_cycle(family, cls.season, timezone.localdate())
                    schedule.next_charge_date = max(next_day, cls.season.start_date)
                    schedule.save(update_fields=['next_charge_date','updated_at'])
            enrollments.append(enrollment)
    # Studio-wide schedules are recomputed by sync_billing_for_enrollment.
    for schedule in RecurringChargeSchedule.objects.filter(account=account, universal_tuition=True, is_active=True, next_charge_date__lte=timezone.localdate()):
        _, upcoming = _monthly_cycle(family, schedule.season, timezone.localdate())
        schedule.next_charge_date = upcoming
        schedule.save(update_fields=['next_charge_date','updated_at'])
    payment = None
    if due > ZERO:
        charge = Charge.objects.create(account=account, charge_type=Charge.ChargeType.TUITION,
            description='Prorated tuition increase — additional classes', amount=due,
            due_date=timezone.localdate(), status=Charge.Status.OPEN,
            notes=f'Additional-class registration session {session.pk}.')
        payment = Payment.objects.create(account=account, amount=due,
            method=Payment.Method.CARD, status=Payment.Status.SUCCEEDED,
            external_reference=stripe_payment_intent_id,
            notes='Prorated class addition paid through studio Stripe Connect.')
        PaymentAllocation.objects.create(payment=payment, charge=charge, amount=due)
    RegistrationClassHold.objects.filter(registration_session=session).update(is_active=False)
    session.linked_user, session.linked_family = user, family
    session.linked_student_id = int(raw['students'][0]['existing_student_id'])
    session.linked_payment = payment
    session.stripe_payment_intent_id = stripe_payment_intent_id
    consume_class_codes(session)
    session.status, session.current_step = session.Status.COMPLETED, 'complete'
    session.finalized_at = timezone.now()
    session.save(update_fields=['linked_user','linked_family','linked_student','linked_payment',
        'stripe_payment_intent_id','status','current_step','finalized_at','updated_at'])
    transaction.on_commit(lambda: _send_registration_confirmation(session, enrollments=enrollments, payment=payment))
    return dict(user=user, family=family, students=[e.student for e in enrollments],
        enrollments=enrollments, payment=payment)
