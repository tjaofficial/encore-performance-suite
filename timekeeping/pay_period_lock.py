"""Allow teacher corrections only within the current, configured pay period."""
from datetime import timedelta
from django.utils import timezone
from instructors.models import PayrollSettings


def can_modify_extra_work(studio, work_date):
    today = timezone.localdate()
    if not work_date or work_date > today:
        return False
    config = PayrollSettings.objects.filter(studio=studio).first()
    if config is None:
        return False  # Fail closed until payroll calendar is configured.
    frequency = config.pay_period_frequency
    if frequency == PayrollSettings.PayPeriodFrequency.MONTHLY:
        return (work_date.year, work_date.month) == (today.year, today.month)
    if frequency == PayrollSettings.PayPeriodFrequency.SEMIMONTHLY:
        return (work_date.year, work_date.month, work_date.day <= 15) == (today.year, today.month, today.day <= 15)
    days = 7 if frequency == PayrollSettings.PayPeriodFrequency.WEEKLY else 14
    anchor = config.pay_period_anchor_date
    if anchor is None:
        return False  # Never invent an anchor for locking payroll data.
    return (work_date - anchor).days // days == (today - anchor).days // days
