"""Reviewed, idempotent future-only import billing cutover."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from billing.models import FamilyAccount, ImportedFamilyTuitionReview, RecurringChargeSchedule, StudioTuitionSettings
from billing.services import enrollment_tuition_amount, weekly_hours_for_class, calculate_studio_wide_tuition
from enrollments.models import Enrollment

RECURRING = {"weekly", "monthly", "quarterly"}


def first_import_charge_date(cutover, season, policy, *, today=None):
    """First *future* charge date for an imported schedule, within its season.

    Activation never bills the current day (including a first-of-month cutover),
    which protects against a daily worker running immediately after activation.
    Other billing frequencies retain their cadence rather than being forced monthly.
    """
    today = today or timezone.localdate()
    earliest = max(cutover, season.start_date, today + timedelta(days=1))
    if policy.frequency == "monthly":
        if earliest.day != 1:
            earliest = date(earliest.year + (earliest.month == 12),
                            1 if earliest.month == 12 else earliest.month + 1, 1)
    return earliest if earliest <= season.end_date else None


def activation_preview(studio, cutover):
    settings_obj = StudioTuitionSettings.objects.filter(studio=studio).first()
    studio_wide = bool(settings_obj and settings_obj.is_studio_wide)
    enrollments = list(Enrollment.objects.filter(
        class_instance__studio=studio, source=Enrollment.Source.IMPORT,
        status=Enrollment.Status.ACTIVE, class_instance__season__end_date__gte=cutover,
    ).select_related('student__family', 'class_instance__season', 'class_instance__tuition_plan')
     .prefetch_related('class_instance__meeting_times'))
    groups = defaultdict(list)
    rows = []
    for e in enrollments:
        if studio_wide and e.tuition_override is None and e.class_instance.tuition_amount is None and e.student.family_id:
            groups[(e.student.family_id, e.class_instance.season_id)].append(e)
        else:
            rows.append(_individual_row(e, studio, cutover))
    overrides = {(r.family_id, r.season_id): r.amount_override for r in ImportedFamilyTuitionReview.objects.filter(studio=studio)}
    family_ids = [key[0] for key in groups]
    season_ids = [key[1] for key in groups]
    all_family_enrollments = defaultdict(list)
    if family_ids:
        for e in Enrollment.objects.filter(
            student__family_id__in=family_ids, class_instance__season_id__in=season_ids,
            class_instance__studio=studio, status=Enrollment.Status.ACTIVE,
            tuition_override__isnull=True, class_instance__tuition_amount__isnull=True,
        ).select_related('student', 'class_instance__season').prefetch_related('class_instance__meeting_times'):
            all_family_enrollments[(e.student.family_id, e.class_instance.season_id)].append(e)
    schedules = defaultdict(list)
    if family_ids:
        for s in RecurringChargeSchedule.objects.filter(account__studio=studio, account__family_id__in=family_ids, season_id__in=season_ids).select_related('account'):
            schedules[(s.account.family_id, s.season_id)].append(s)
    policy = settings_obj.default_tuition_plan if studio_wide else None
    for key, imported in groups.items():
        family, season = imported[0].student.family, imported[0].class_instance.season
        members = all_family_enrollments[key]
        hours = sum((weekly_hours_for_class(e.class_instance) for e in members), Decimal('0'))
        computed = calculate_studio_wide_tuition(settings_obj, hours)
        override = overrides.get(key)
        amount = override if override is not None else computed
        existing = schedules[key]
        if any(s.universal_tuition for s in existing):
            status, reason = 'existing', 'Family tuition schedule already exists; not modified.'
        elif any(s.universal_tuition is False and s.enrollment_id is None for s in existing):
            status, reason = 'missing', 'Unrecognized existing family-level schedules; review before activation.'
        elif not policy or policy.studio_id != studio.pk or policy.frequency not in RECURRING:
            status, reason = 'missing', 'Select a valid recurring default studio-wide tuition policy in Tuition Setup.'
        elif not members or hours <= 0:
            status, reason = 'missing', 'No active class meeting hours; check class meeting times.'
        elif amount <= 0:
            status, reason = 'missing', 'Tuition calculates to $0; review rates or enter an adjustment.'
        elif first_import_charge_date(cutover, season, policy) is None:
            status, reason = 'missing', 'No future billing date falls within the season.'
        else:
            status, reason = 'eligible', ''
        rows.append({'kind': 'family', 'family': family, 'season': season,
            'key': f'{family.pk}:{season.pk}', 'members': members,
            'student_count': len({e.student_id for e in members}),
            'enrollment_count': len(imported), 'class_names': ', '.join(sorted({e.class_instance.name for e in members})),
            'weekly_hours': hours, 'computed': computed, 'override': override,
            'amount': amount, 'status': status, 'reason': reason,
            'first_charge_date': first_import_charge_date(cutover, season, policy) if policy and policy.frequency in RECURRING else None})
    # Surface the distinction between included studio-wide classes and separately billed classes.
    # The actual individual schedules remain separate; never fold their prices into the family-wide rate.
    special_by_key = defaultdict(list)
    for row in rows:
        if row['kind'] == 'individual':
            e = row['enrollment']
            if e.student.family_id:
                special_by_key[(e.student.family_id, e.class_instance.season_id)].append(row)
    for row in rows:
        if row['kind'] == 'family':
            key = (row['family'].pk, row['season'].pk)
            row['special_classes'] = special_by_key[key]
            row['special_total'] = sum((item['amount'] for item in special_by_key[key]), Decimal('0.00'))
            row['combined_total'] = row['amount'] + row['special_total']
    rows.sort(key=lambda r: (0 if r['status'] == 'missing' else 1, (r.get('family').family_name if r.get('family') else str(r['enrollment'].student)).lower()))
    counts = {'eligible': 0, 'existing': 0, 'missing': 0, 'total': len(enrollments),
              'families': len(groups), 'individual': len(rows)-len(groups), 'schedules_ready': 0}
    for r in rows:
        counts[r['status']] += 1
        if r['status'] == 'eligible': counts['schedules_ready'] += 1
    return counts, rows


def _individual_row(e, studio, cutover):
    cl = e.class_instance
    existing = RecurringChargeSchedule.objects.filter(enrollment=e).exists()
    amount = enrollment_tuition_amount(e)
    if existing:
        status, reason = 'existing', 'Schedule already exists.'
    elif not e.student.family_id:
        status, reason = 'missing', 'Missing family.'
    elif not cl.tuition_plan_id or cl.tuition_plan.studio_id != studio.pk or cl.tuition_plan.frequency not in RECURRING:
        status, reason = 'missing', 'Class needs a valid recurring tuition policy.'
    elif amount <= 0:
        status, reason = 'missing', 'Class/enrollment tuition is zero.'
    elif first_import_charge_date(cutover, cl.season, cl.tuition_plan) is None:
        status, reason = 'missing', 'No future billing date falls within the season.'
    else:
        status, reason = 'eligible', ''
    return {'kind': 'individual', 'enrollment': e, 'amount': amount, 'status': status, 'reason': reason,
            'key': f'e:{e.pk}',
            'first_charge_date': first_import_charge_date(cutover, cl.season, cl.tuition_plan) if cl.tuition_plan_id and cl.tuition_plan.frequency in RECURRING else None}


@transaction.atomic
def save_family_adjustment(studio, family_id, season_id, raw_amount):
    from families.models import Family
    from classes.models import Season
    from django.core.exceptions import ValidationError
    if not Family.objects.filter(pk=family_id, studio=studio).exists() or not Season.objects.filter(pk=season_id, studio=studio).exists():
        raise ValueError('Invalid family or season.')
    if raw_amount.strip() == '':
        ImportedFamilyTuitionReview.objects.filter(studio=studio, family_id=family_id, season_id=season_id).delete()
        return
    try:
        amount = Decimal(raw_amount)
    except Exception:
        raise ValueError('Enter a valid tuition amount.')
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2 or amount >= Decimal('100000000'):
        raise ValueError('Enter a positive dollar amount with no more than two decimal places.')
    ImportedFamilyTuitionReview.objects.update_or_create(studio=studio, family_id=family_id, season_id=season_id, defaults={'amount_override': amount})


@transaction.atomic
def activate_imported_billing(studio, cutover):
    if cutover < timezone.localdate():
        raise ValueError('Activation date cannot be in the past.')
    from studios.models import Studio
    Studio.objects.select_for_update().get(pk=studio.pk)
    counts, rows = activation_preview(studio, cutover)
    created = 0
    for row in rows:
        if row['status'] != 'eligible':
            continue
        if row['kind'] == 'family':
            family, season = row['family'], row['season']
            account, _ = FamilyAccount.objects.get_or_create(family=family, defaults={'studio': studio})
            # Refuse any competing schedule, not just universal ones.
            if RecurringChargeSchedule.objects.filter(account=account, season=season, universal_tuition=True).exists():
                continue
            policy = StudioTuitionSettings.objects.get(studio=studio).default_tuition_plan
            first_date = first_import_charge_date(cutover, season, policy)
            if first_date is None:
                continue
            RecurringChargeSchedule.objects.create(
                account=account, season=season, universal_tuition=True,
                tuition_plan=policy, schedule_type=RecurringChargeSchedule.ScheduleType.TUITION,
                amount_override=row['amount'], start_date=first_date, end_date=season.end_date,
                next_charge_date=first_date, is_active=True,
                notes='Studio Director import billing cutover. Reviewed family tuition; no historical backfill.')
            created += 1
        else:
            e = row['enrollment']
            cl = e.class_instance
            account, _ = FamilyAccount.objects.get_or_create(family=e.student.family, defaults={'studio': studio})
            # Never create a per-class schedule alongside an existing family-wide schedule.
            if RecurringChargeSchedule.objects.filter(account=account, season=cl.season, universal_tuition=True).exists():
                continue
            first_date = first_import_charge_date(cutover, cl.season, cl.tuition_plan)
            if first_date is None:
                continue
            _, made = RecurringChargeSchedule.objects.get_or_create(enrollment=e, defaults={
                'account': account, 'student': e.student, 'class_instance': cl,
                'season': cl.season, 'tuition_plan': cl.tuition_plan,
                'schedule_type': RecurringChargeSchedule.ScheduleType.TUITION,
                'start_date': first_date, 'end_date': cl.season.end_date,
                'next_charge_date': first_date, 'is_active': True, 'amount_override': row['amount'],
                'notes': 'Studio Director import billing cutover. No historical backfill.'})
            created += int(made)
    return created, counts
