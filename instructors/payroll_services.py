from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from classes.models import Class, ClassMeeting
from scheduling.models import (
    ClassOccurrenceOverride,
    TeacherTimeOffDate,
)
from timekeeping.models import ExtraWorkEntry

from .models import (
    Instructor,
    InstructorCompensation,
    PayrollSettings,
)


MONEY_QUANT = Decimal("0.01")
HOURS_QUANT = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def minutes_to_hours(minutes):
    return (
        Decimal(minutes)
        / Decimal("60")
    ).quantize(
        HOURS_QUANT,
        rounding=ROUND_HALF_UP,
    )


def payable_minutes(
    scheduled_minutes,
    payroll_settings,
):
    """
    Apply the studio's minimum paid-session rule and optional rounding.

    Examples with the default 60-minute minimum and exact rounding:
    45 -> 60, 60 -> 60, 75 -> 75.
    """
    scheduled = max(
        int(scheduled_minutes or 0),
        0,
    )
    minimum = max(
        int(
            payroll_settings.minimum_session_minutes
            or 1
        ),
        1,
    )

    if scheduled <= minimum:
        return minimum

    increment = int(
        payroll_settings.rounding_minutes
        or 0
    )

    if increment <= 0:
        return scheduled

    rounded = int(
        (
            Decimal(scheduled)
            / Decimal(increment)
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        * Decimal(increment)
    )

    return max(
        rounded,
        minimum,
    )


def first_weekday_on_or_after(
    start_date,
    weekday,
):
    delta = (
        int(weekday)
        - start_date.weekday()
    ) % 7
    return start_date + timedelta(days=delta)


def occurrence_dates(
    start_date,
    end_date,
    weekday,
):
    current = first_weekday_on_or_after(
        start_date,
        weekday,
    )

    while current <= end_date:
        yield current
        current += timedelta(days=7)


def compensation_for_date(
    records,
    work_date,
):
    for record in records:
        if record.effective_start > work_date:
            continue

        if (
            record.effective_end is not None
            and record.effective_end < work_date
        ):
            continue

        return record

    return None


def _hourly_amount(
    minutes,
    rate,
):
    if rate is None:
        return None

    return _money(
        (
            Decimal(minutes)
            / Decimal("60")
        )
        * Decimal(rate)
    )


def _rate_for_source(
    compensation,
    payroll_settings,
    source_type,
):
    if compensation is None:
        return None, "No compensation record covers this date."

    if source_type == "extra_work":
        if compensation.extra_work_hourly_rate is not None:
            return (
                compensation.extra_work_hourly_rate,
                "",
            )

        if (
            payroll_settings.extra_work_uses_regular_rate
            and compensation.compensation_type
            == InstructorCompensation.CompensationType.HOURLY
        ):
            return (
                compensation.hourly_rate,
                "",
            )

        return (
            None,
            "No payable extra-work rate is configured for this date.",
        )

    if (
        compensation.compensation_type
        == InstructorCompensation.CompensationType.HOURLY
    ):
        return compensation.hourly_rate, ""

    return (
        None,
        (
            "Salary compensation is stored for this date, but Encore does "
            "not convert salary into per-class deductions or occurrence pay "
            "until a salary-pay policy is configured."
        ),
    )


def _entry(
    *,
    entry_date,
    instructor,
    source_type,
    minutes,
    payroll_settings,
    compensation_records,
    class_instance=None,
    meeting=None,
    extra_work=None,
    note="",
):
    compensation = compensation_for_date(
        compensation_records.get(
            instructor.pk,
            [],
        ),
        entry_date,
    )

    rate, missing_reason = _rate_for_source(
        compensation,
        payroll_settings,
        source_type,
    )

    amount = _hourly_amount(
        minutes,
        rate,
    )

    return {
        "date": entry_date,
        "instructor": instructor,
        "source_type": source_type,
        "minutes": int(minutes),
        "hours": minutes_to_hours(minutes),
        "rate": rate,
        "amount": amount,
        "compensation": compensation,
        "class_instance": class_instance,
        "meeting": meeting,
        "extra_work": extra_work,
        "season": (
            class_instance.season
            if class_instance is not None
            else None
        ),
        "note": note,
        "missing_reason": missing_reason,
        "is_resolved": amount is not None,
    }


def _compensation_map(
    instructors,
):
    instructor_ids = [
        instructor.pk
        for instructor in instructors
    ]

    records = (
        InstructorCompensation.objects
        .filter(
            instructor_id__in=instructor_ids,
        )
        .select_related("instructor")
        .order_by(
            "instructor_id",
            "-effective_start",
            "-created_at",
        )
    )

    result = defaultdict(list)

    for record in records:
        result[record.instructor_id].append(
            record
        )

    return result


def _active_time_off_keys(
    studio,
    start_date,
    end_date,
):
    approved_statuses = {
        TeacherTimeOffDate.Status.APPROVED,
        TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
    }

    rows = (
        TeacherTimeOffDate.objects
        .filter(
            request__studio=studio,
            date__gte=start_date,
            date__lte=end_date,
            status__in=approved_statuses,
        )
        .values_list(
            "request__instructor_id",
            "date",
        )
    )

    return set(rows)


def _override_map(
    studio,
    start_date,
    end_date,
):
    overrides = (
        ClassOccurrenceOverride.objects
        .filter(
            studio=studio,
            occurrence_date__gte=start_date,
            occurrence_date__lte=end_date,
            status=ClassOccurrenceOverride.Status.ACTIVE,
        )
        .select_related(
            "substitute_instructor",
            "absent_instructor",
            "class_instance",
            "class_instance__season",
            "meeting",
        )
    )

    return {
        (
            item.meeting_id,
            item.occurrence_date,
        ): item
        for item in overrides
    }


def calculate_payroll(
    *,
    studio,
    start_date,
    end_date,
    instructor_ids=None,
    season=None,
):
    """
    Calculate live payroll entries for the requested date range.

    Hourly teaching:
      scheduled class occurrence
      + approved time-off deduction
      + substitute occurrence when coverage is assigned
      + extra work

    Salary records are deliberately not converted into occurrence pay here.
    They remain visible as unresolved calculation items until the studio's
    salary-pay policy is defined.
    """
    if end_date < start_date:
        start_date, end_date = (
            end_date,
            start_date,
        )

    payroll_settings, _created = (
        PayrollSettings.objects.get_or_create(
            studio=studio
        )
    )

    instructor_query = Instructor.objects.filter(
        studio=studio,
    ).select_related("user")

    if instructor_ids is not None:
        instructor_query = instructor_query.filter(
            pk__in=instructor_ids,
        )

    instructors = list(
        instructor_query.order_by(
            "last_name",
            "first_name",
        )
    )
    instructors_by_id = {
        instructor.pk: instructor
        for instructor in instructors
    }

    compensation_records = _compensation_map(
        instructors
    )

    classes = (
        Class.objects
        .filter(
            studio=studio,
            season__start_date__lte=end_date,
            season__end_date__gte=start_date,
        )
        .select_related(
            "season",
            "instructor",
            "instructor__user",
        )
        .prefetch_related(
            "meeting_times",
        )
        .order_by(
            "season__start_date",
            "name",
        )
    )

    if season is not None:
        classes = classes.filter(
            season=season
        )

    if instructor_ids is not None:
        # Keep classes where the selected teacher could be the normal
        # instructor. Substitute occurrences are added separately below.
        classes = classes.filter(
            instructor_id__in=instructor_ids
        )

    time_off_keys = _active_time_off_keys(
        studio,
        start_date,
        end_date,
    )
    overrides = _override_map(
        studio,
        start_date,
        end_date,
    )

    entries = []

    for class_instance in classes:
        instructor = class_instance.instructor

        if instructor is None:
            continue

        if instructor.pk not in instructors_by_id:
            continue

        class_start = max(
            start_date,
            class_instance.season.start_date,
        )
        class_end = min(
            end_date,
            class_instance.season.end_date,
        )

        if class_end < class_start:
            continue

        for meeting in class_instance.meeting_times.all():
            if not meeting.is_active:
                continue

            paid_minutes = payable_minutes(
                meeting.duration_minutes,
                payroll_settings,
            )

            for occurrence_date in occurrence_dates(
                class_start,
                class_end,
                meeting.day_of_week,
            ):
                entries.append(
                    _entry(
                        entry_date=occurrence_date,
                        instructor=instructor,
                        source_type="regular_class",
                        minutes=paid_minutes,
                        payroll_settings=payroll_settings,
                        compensation_records=compensation_records,
                        class_instance=class_instance,
                        meeting=meeting,
                        note="Scheduled class occurrence",
                    )
                )

                is_time_off = (
                    instructor.pk,
                    occurrence_date,
                ) in time_off_keys

                if not is_time_off:
                    continue

                entries.append(
                    _entry(
                        entry_date=occurrence_date,
                        instructor=instructor,
                        source_type="time_off",
                        minutes=-paid_minutes,
                        payroll_settings=payroll_settings,
                        compensation_records=compensation_records,
                        class_instance=class_instance,
                        meeting=meeting,
                        note="Approved time off deduction",
                    )
                )

                override = overrides.get(
                    (
                        meeting.pk,
                        occurrence_date,
                    )
                )

                if override is None:
                    continue

                substitute = (
                    override.substitute_instructor
                )

                if (
                    instructor_ids is not None
                    and substitute.pk
                    not in instructors_by_id
                ):
                    # The caller asked for specific teachers. A substitute
                    # outside that selection should not be added.
                    continue

                if substitute.pk not in instructors_by_id:
                    # Expand the compensation lookup on demand for a substitute
                    # not in the original instructor queryset.
                    instructors_by_id[
                        substitute.pk
                    ] = substitute
                    substitute_records = list(
                        substitute.compensation_records
                        .all()
                        .order_by(
                            "-effective_start",
                            "-created_at",
                        )
                    )
                    compensation_records[
                        substitute.pk
                    ] = substitute_records

                entries.append(
                    _entry(
                        entry_date=occurrence_date,
                        instructor=substitute,
                        source_type="substitute",
                        minutes=paid_minutes,
                        payroll_settings=payroll_settings,
                        compensation_records=compensation_records,
                        class_instance=class_instance,
                        meeting=meeting,
                        note=(
                            f"Substitute coverage for "
                            f"{instructor.full_name}"
                        ),
                    )
                )

    # When calculating a selected instructor who only substituted, their
    # substitute entries may not have been encountered above because their
    # normal class wasn't in the filtered class queryset. Add those overrides.
    if instructor_ids is not None:
        selected_ids = set(
            int(value)
            for value in instructor_ids
        )

        for override in overrides.values():
            substitute = override.substitute_instructor

            if substitute.pk not in selected_ids:
                continue

            duplicate = any(
                entry["source_type"] == "substitute"
                and entry["meeting"] is not None
                and entry["meeting"].pk
                == override.meeting_id
                and entry["date"]
                == override.occurrence_date
                and entry["instructor"].pk
                == substitute.pk
                for entry in entries
            )

            if duplicate:
                continue

            if substitute.pk not in compensation_records:
                compensation_records[
                    substitute.pk
                ] = list(
                    substitute.compensation_records
                    .all()
                    .order_by(
                        "-effective_start",
                        "-created_at",
                    )
                )

            entries.append(
                _entry(
                    entry_date=override.occurrence_date,
                    instructor=substitute,
                    source_type="substitute",
                    minutes=payable_minutes(
                        override.meeting.duration_minutes,
                        payroll_settings,
                    ),
                    payroll_settings=payroll_settings,
                    compensation_records=compensation_records,
                    class_instance=override.class_instance,
                    meeting=override.meeting,
                    note=(
                        f"Substitute coverage for "
                        f"{override.absent_instructor.full_name}"
                    ),
                )
            )

    extra_work = (
        ExtraWorkEntry.objects
        .filter(
            studio=studio,
            work_date__gte=start_date,
            work_date__lte=end_date,
        )
        .select_related("user")
        .order_by(
            "work_date",
            "created_at",
        )
    )

    if instructor_ids is not None:
        selected_user_ids = [
            instructor.user_id
            for instructor in instructors
            if instructor.user_id
        ]
        extra_work = extra_work.filter(
            user_id__in=selected_user_ids,
        )

    instructor_by_user = {
        instructor.user_id: instructor
        for instructor in Instructor.objects.filter(
            studio=studio,
            user__isnull=False,
        ).select_related("user")
    }

    for item in extra_work:
        instructor = instructor_by_user.get(
            item.user_id
        )

        if instructor is None:
            continue

        if (
            instructor_ids is not None
            and instructor.pk
            not in set(instructor_ids)
        ):
            continue

        if instructor.pk not in compensation_records:
            compensation_records[
                instructor.pk
            ] = list(
                instructor.compensation_records
                .all()
                .order_by(
                    "-effective_start",
                    "-created_at",
                )
            )

        entries.append(
            _entry(
                entry_date=item.work_date,
                instructor=instructor,
                source_type="extra_work",
                minutes=item.duration_minutes,
                payroll_settings=payroll_settings,
                compensation_records=compensation_records,
                extra_work=item,
                note=item.get_category_display(),
            )
        )

    entries.sort(
        key=lambda entry: (
            entry["date"],
            entry["instructor"].last_name.lower(),
            entry["instructor"].first_name.lower(),
            entry["source_type"],
        )
    )

    staff_map = {}

    for entry in entries:
        instructor = entry["instructor"]
        row = staff_map.setdefault(
            instructor.pk,
            {
                "instructor": instructor,
                "regular_minutes": 0,
                "time_off_minutes": 0,
                "substitute_minutes": 0,
                "extra_work_minutes": 0,
                "net_minutes": 0,
                "regular_pay": Decimal("0.00"),
                "time_off_pay": Decimal("0.00"),
                "substitute_pay": Decimal("0.00"),
                "extra_work_pay": Decimal("0.00"),
                "total_pay": Decimal("0.00"),
                "unresolved_count": 0,
                "unresolved_reasons": set(),
                "entries": [],
            },
        )

        row["entries"].append(entry)
        row["net_minutes"] += entry["minutes"]

        source = entry["source_type"]

        if source == "regular_class":
            row["regular_minutes"] += entry["minutes"]
            bucket = "regular_pay"
        elif source == "time_off":
            row["time_off_minutes"] += entry["minutes"]
            bucket = "time_off_pay"
        elif source == "substitute":
            row["substitute_minutes"] += entry["minutes"]
            bucket = "substitute_pay"
        else:
            row["extra_work_minutes"] += entry["minutes"]
            bucket = "extra_work_pay"

        if entry["amount"] is None:
            row["unresolved_count"] += 1
            if entry["missing_reason"]:
                row["unresolved_reasons"].add(
                    entry["missing_reason"]
                )
            continue

        row[bucket] += entry["amount"]
        row["total_pay"] += entry["amount"]

    staff_rows = list(staff_map.values())

    for row in staff_rows:
        row["net_hours"] = minutes_to_hours(
            row["net_minutes"]
        )
        row["regular_hours"] = minutes_to_hours(
            row["regular_minutes"]
        )
        row["time_off_hours"] = minutes_to_hours(
            row["time_off_minutes"]
        )
        row["substitute_hours"] = minutes_to_hours(
            row["substitute_minutes"]
        )
        row["extra_work_hours"] = minutes_to_hours(
            row["extra_work_minutes"]
        )
        row["unresolved_reasons"] = sorted(
            row["unresolved_reasons"]
        )
        for key in (
            "regular_pay",
            "time_off_pay",
            "substitute_pay",
            "extra_work_pay",
            "total_pay",
        ):
            row[key] = _money(row[key])

    staff_rows.sort(
        key=lambda row: (
            row["instructor"].last_name.lower(),
            row["instructor"].first_name.lower(),
        )
    )

    known_pay_total = _money(
        sum(
            (
                row["total_pay"]
                for row in staff_rows
            ),
            Decimal("0.00"),
        )
    )
    net_minutes_total = sum(
        row["net_minutes"]
        for row in staff_rows
    )
    unresolved_total = sum(
        row["unresolved_count"]
        for row in staff_rows
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "payroll_settings": payroll_settings,
        "entries": entries,
        "staff_rows": staff_rows,
        "known_pay_total": known_pay_total,
        "net_minutes_total": net_minutes_total,
        "net_hours_total": minutes_to_hours(
            net_minutes_total
        ),
        "unresolved_total": unresolved_total,
        "is_complete": unresolved_total == 0,
    }


def _month_periods(
    start_date,
    end_date,
):
    periods = []
    current = start_date.replace(day=1)

    while current <= end_date:
        last_day = monthrange(
            current.year,
            current.month,
        )[1]
        period_end = date(
            current.year,
            current.month,
            last_day,
        )

        periods.append(
            (
                max(start_date, current),
                min(end_date, period_end),
            )
        )

        if current.month == 12:
            current = date(
                current.year + 1,
                1,
                1,
            )
        else:
            current = date(
                current.year,
                current.month + 1,
                1,
            )

    return periods


def _semimonthly_periods(
    start_date,
    end_date,
):
    periods = []

    for month_start, month_end in _month_periods(
        start_date,
        end_date,
    ):
        month_first = month_start.replace(
            day=1
        )
        month_last = date(
            month_first.year,
            month_first.month,
            monthrange(
                month_first.year,
                month_first.month,
            )[1],
        )

        for raw_start, raw_end in (
            (
                month_first,
                month_first.replace(day=15),
            ),
            (
                month_first.replace(day=16),
                month_last,
            ),
        ):
            clipped_start = max(
                start_date,
                raw_start,
            )
            clipped_end = min(
                end_date,
                raw_end,
            )

            if clipped_start <= clipped_end:
                periods.append(
                    (
                        clipped_start,
                        clipped_end,
                    )
                )

    return periods


def pay_periods_for_range(
    *,
    payroll_settings,
    start_date,
    end_date,
):
    """
    Return inclusive pay-period date pairs.

    Weekly/biweekly schedules use the configured anchor date. If no anchor is
    configured yet, the requested range start is used and a warning is returned.
    """
    frequency = (
        payroll_settings.pay_period_frequency
    )

    if frequency == PayrollSettings.PayPeriodFrequency.MONTHLY:
        return _month_periods(
            start_date,
            end_date,
        ), ""

    if frequency == PayrollSettings.PayPeriodFrequency.SEMIMONTHLY:
        return _semimonthly_periods(
            start_date,
            end_date,
        ), ""

    days = (
        7
        if frequency
        == PayrollSettings.PayPeriodFrequency.WEEKLY
        else 14
    )

    anchor = (
        payroll_settings.pay_period_anchor_date
    )
    warning = ""

    if anchor is None:
        anchor = start_date
        warning = (
            "No pay-period anchor date is configured. Encore temporarily "
            "aligned periods to the requested range start."
        )

    while anchor > start_date:
        anchor -= timedelta(days=days)

    while (
        anchor + timedelta(days=days - 1)
        < start_date
    ):
        anchor += timedelta(days=days)

    periods = []
    current = anchor

    while current <= end_date:
        period_end = (
            current
            + timedelta(days=days - 1)
        )
        clipped_start = max(
            start_date,
            current,
        )
        clipped_end = min(
            end_date,
            period_end,
        )

        if clipped_start <= clipped_end:
            periods.append(
                (
                    clipped_start,
                    clipped_end,
                )
            )

        current += timedelta(days=days)

    return periods, warning


def payroll_by_period(
    *,
    studio,
    start_date,
    end_date,
    instructor_ids=None,
    season=None,
):
    result = calculate_payroll(
        studio=studio,
        start_date=start_date,
        end_date=end_date,
        instructor_ids=instructor_ids,
        season=season,
    )

    periods, warning = pay_periods_for_range(
        payroll_settings=result[
            "payroll_settings"
        ],
        start_date=start_date,
        end_date=end_date,
    )

    rows = []

    for period_start, period_end in periods:
        period_entries = [
            entry
            for entry in result["entries"]
            if (
                period_start
                <= entry["date"]
                <= period_end
            )
        ]

        minutes = sum(
            entry["minutes"]
            for entry in period_entries
        )
        known_pay = _money(
            sum(
                (
                    entry["amount"]
                    for entry in period_entries
                    if entry["amount"] is not None
                ),
                Decimal("0.00"),
            )
        )
        unresolved_count = sum(
            1
            for entry in period_entries
            if entry["amount"] is None
        )

        rows.append(
            {
                "start_date": period_start,
                "end_date": period_end,
                "entries": period_entries,
                "minutes": minutes,
                "hours": minutes_to_hours(
                    minutes
                ),
                "known_pay": known_pay,
                "unresolved_count": (
                    unresolved_count
                ),
            }
        )

    result["pay_periods"] = rows
    result["pay_period_warning"] = warning

    return result
