from datetime import date, timedelta
from decimal import Decimal
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from classes.models import Class, Season
from scheduling.models import ClassOccurrenceOverride
from studios.models import Studio, StudioMembership

from .models import (
    Instructor,
    InstructorCompensation,
    PayrollSettings,
)
from .payroll_forms import (
    InstructorCompensationForm,
    PayrollSettingsForm,
    PayrollUnlockForm,
)
from .payroll_services import calculate_payroll, payroll_by_period


PAYROLL_UNLOCK_SECONDS = 15 * 60


def _admin_workspace(request, studio):
    if request.user.is_superuser:
        return True

    return (
        request.session.get("encore_workspace_role")
        == StudioMembership.Role.ADMINISTRATOR
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role=StudioMembership.Role.ADMINISTRATOR,
            is_active=True,
        ).exists()
    )


def _teacher_workspace(request, studio):
    return (
        request.session.get("encore_workspace_role")
        == StudioMembership.Role.TEACHER
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role=StudioMembership.Role.TEACHER,
            is_active=True,
        ).exists()
    )


def _payroll_unlock_key(studio):
    return f"encore_payroll_unlocked_until_{studio.pk}"


def _payroll_is_unlocked(request, studio):
    raw_value = request.session.get(
        _payroll_unlock_key(studio)
    )

    try:
        unlocked_until = float(raw_value)
    except (TypeError, ValueError):
        return False

    return unlocked_until > timezone.now().timestamp()


def _safe_payroll_next(request, studio, value):
    if not value:
        return reverse(
            "instructors:payroll_management",
            kwargs={"studio_slug": studio.slug},
        )

    if not url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return reverse(
            "instructors:payroll_management",
            kwargs={"studio_slug": studio.slug},
        )

    payroll_prefix = f"/instructors/{studio.slug}/payroll/"
    if not value.startswith(payroll_prefix):
        return reverse(
            "instructors:payroll_management",
            kwargs={"studio_slug": studio.slug},
        )

    return value


def _require_payroll_unlock(request, studio):
    if _payroll_is_unlocked(request, studio):
        return None

    unlock_url = reverse(
        "instructors:payroll_unlock",
        kwargs={"studio_slug": studio.slug},
    )
    return redirect(
        f"{unlock_url}?next={request.path}"
    )


def _teacher_instructor(request, studio):
    return get_object_or_404(
        Instructor.objects.select_related("user"),
        studio=studio,
        user=request.user,
        is_active=True,
    )


def _sum_amount(entries):
    total = 0
    unresolved = 0

    for entry in entries:
        if entry["amount"] is None:
            unresolved += 1
            continue
        total += entry["amount"]

    return total, unresolved


def _teacher_season_tree(
    *,
    studio,
    instructor,
):
    primary_season_ids = set(
        Class.objects
        .filter(
            studio=studio,
            instructor=instructor,
        )
        .values_list(
            "season_id",
            flat=True,
        )
    )

    substitute_season_ids = set(
        ClassOccurrenceOverride.objects
        .filter(
            studio=studio,
            substitute_instructor=instructor,
            status=ClassOccurrenceOverride.Status.ACTIVE,
        )
        .values_list(
            "class_instance__season_id",
            flat=True,
        )
    )

    season_ids = (
        primary_season_ids
        | substitute_season_ids
    )

    seasons = list(
        Season.objects
        .filter(
            studio=studio,
            pk__in=season_ids,
        )
        .order_by(
            "-start_date",
            "name",
        )
    )

    season_rows = []

    for season in seasons:
        result = payroll_by_period(
            studio=studio,
            start_date=season.start_date,
            end_date=season.end_date,
            instructor_ids=[instructor.pk],
            season=season,
        )

        entries = [
            entry
            for entry in result["entries"]
            if entry["instructor"].pk
            == instructor.pk
        ]

        class_groups = {}

        for entry in entries:
            class_instance = entry.get(
                "class_instance"
            )

            if class_instance is None:
                key = "extra_work"
                label = "Extra Work"
            else:
                key = f"class-{class_instance.pk}"
                label = class_instance.name

            group = class_groups.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "class_instance": class_instance,
                    "entries": [],
                },
            )
            group["entries"].append(entry)

        class_rows = []

        for group in class_groups.values():
            group_entries = group["entries"]

            total_minutes = sum(
                entry["minutes"]
                for entry in group_entries
            )
            total_pay, unresolved = (
                _sum_amount(group_entries)
            )

            period_rows = []

            for period in result["pay_periods"]:
                period_entries = [
                    entry
                    for entry in period["entries"]
                    if entry in group_entries
                ]

                if not period_entries:
                    continue

                period_minutes = sum(
                    entry["minutes"]
                    for entry in period_entries
                )
                period_pay, period_unresolved = (
                    _sum_amount(period_entries)
                )

                period_rows.append(
                    {
                        "start_date": period["start_date"],
                        "end_date": period["end_date"],
                        "minutes": period_minutes,
                        "hours": (
                            period_minutes / 60
                        ),
                        "pay": period_pay,
                        "unresolved_count": (
                            period_unresolved
                        ),
                        "entries": period_entries,
                    }
                )

            class_rows.append(
                {
                    **group,
                    "minutes": total_minutes,
                    "hours": total_minutes / 60,
                    "pay": total_pay,
                    "unresolved_count": unresolved,
                    "pay_periods": period_rows,
                }
            )

        class_rows.sort(
            key=lambda row: (
                row["class_instance"] is None,
                row["label"].lower(),
            )
        )

        teacher_row = next(
            (
                row
                for row in result["staff_rows"]
                if row["instructor"].pk
                == instructor.pk
            ),
            None,
        )

        season_rows.append(
            {
                "season": season,
                "classes": class_rows,
                "hours": (
                    teacher_row["net_hours"]
                    if teacher_row
                    else 0
                ),
                "pay": (
                    teacher_row["total_pay"]
                    if teacher_row
                    else 0
                ),
                "unresolved_count": (
                    teacher_row[
                        "unresolved_count"
                    ]
                    if teacher_row
                    else 0
                ),
                "pay_period_warning": (
                    result["pay_period_warning"]
                ),
            }
        )

    return season_rows


@login_required
def payroll_unlock(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    next_value = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    )
    next_url = _safe_payroll_next(
        request,
        studio,
        next_value,
    )

    form = PayrollUnlockForm(
        request.POST or None
    )

    if request.method == "POST" and form.is_valid():
        password = form.cleaned_data["password"]

        if request.user.check_password(password):
            request.session[
                _payroll_unlock_key(studio)
            ] = (
                timezone.now()
                + timedelta(
                    seconds=PAYROLL_UNLOCK_SECONDS
                )
            ).timestamp()
            request.session.modified = True

            return redirect(next_url)

        form.add_error(
            "password",
            "That password is incorrect.",
        )

    return render(
        request,
        "instructors/payroll_unlock.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "next": next_url,
        },
    )


@login_required
def payroll_lock(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    request.session.pop(
        _payroll_unlock_key(studio),
        None,
    )
    request.session.modified = True

    return redirect(
        "instructors:payroll_unlock",
        studio_slug=studio.slug,
    )


def _preview_date_range(request):
    today = timezone.localdate()
    default_start = today.replace(day=1)

    if today.month == 12:
        next_month = date(
            today.year + 1,
            1,
            1,
        )
    else:
        next_month = date(
            today.year,
            today.month + 1,
            1,
        )

    default_end = (
        next_month
        - timedelta(days=1)
    )

    start_raw = str(
        request.GET.get("start") or ""
    ).strip()
    end_raw = str(
        request.GET.get("end") or ""
    ).strip()

    try:
        start_date = (
            date.fromisoformat(start_raw)
            if start_raw
            else default_start
        )
    except ValueError:
        start_date = default_start

    try:
        end_date = (
            date.fromisoformat(end_raw)
            if end_raw
            else default_end
        )
    except ValueError:
        end_date = default_end

    if start_date > end_date:
        start_date, end_date = (
            end_date,
            start_date,
        )

    return start_date, end_date


def _admin_payroll_tree(
    *,
    studio,
    active_instructors,
    payroll_preview,
):
    """
    Build the admin expandable payroll hierarchy:

        Studio Payroll
            Instructor
                Season
                    Class
                Extra Work

    The selected preview date range already constrains every entry.
    Extra work is kept directly under the instructor so it is never
    double-counted when multiple seasons overlap the same calendar date.
    """
    preview_staff = {
        row["instructor"].pk: row
        for row in payroll_preview["staff_rows"]
    }

    entries_by_instructor = {}

    for entry in payroll_preview["entries"]:
        entries_by_instructor.setdefault(
            entry["instructor"].pk,
            [],
        ).append(entry)

    teacher_rows = []

    for instructor in active_instructors:
        staff_total = preview_staff.get(
            instructor.pk
        )
        instructor_entries = entries_by_instructor.get(
            instructor.pk,
            [],
        )

        season_groups = {}
        extra_work_entries = []

        for entry in instructor_entries:
            class_instance = entry.get(
                "class_instance"
            )

            if class_instance is None:
                extra_work_entries.append(
                    entry
                )
                continue

            season = class_instance.season
            season_group = season_groups.setdefault(
                season.pk,
                {
                    "season": season,
                    "entries": [],
                    "classes": {},
                },
            )
            season_group["entries"].append(
                entry
            )

            class_group = season_group[
                "classes"
            ].setdefault(
                class_instance.pk,
                {
                    "class_instance": class_instance,
                    "entries": [],
                },
            )
            class_group["entries"].append(
                entry
            )

        seasons = []

        for season_group in season_groups.values():
            class_rows = []

            for class_group in (
                season_group["classes"].values()
            ):
                class_entries = class_group[
                    "entries"
                ]

                minutes = sum(
                    entry["minutes"]
                    for entry in class_entries
                )
                known_pay = sum(
                    (
                        entry["amount"]
                        for entry in class_entries
                        if entry["amount"] is not None
                    ),
                    Decimal("0.00"),
                )
                unresolved = sum(
                    1
                    for entry in class_entries
                    if entry["amount"] is None
                )

                class_rows.append(
                    {
                        "class_instance": (
                            class_group[
                                "class_instance"
                            ]
                        ),
                        "hours": round(
                            minutes / 60,
                            2,
                        ),
                        "known_pay": (
                            known_pay
                        ),
                        "unresolved_count": (
                            unresolved
                        ),
                    }
                )

            class_rows.sort(
                key=lambda row: (
                    row[
                        "class_instance"
                    ].name.lower()
                )
            )

            season_entries = season_group[
                "entries"
            ]
            season_minutes = sum(
                entry["minutes"]
                for entry in season_entries
            )
            season_pay = sum(
                (
                    entry["amount"]
                    for entry in season_entries
                    if entry["amount"] is not None
                ),
                Decimal("0.00"),
            )
            season_unresolved = sum(
                1
                for entry in season_entries
                if entry["amount"] is None
            )

            seasons.append(
                {
                    "season": season_group[
                        "season"
                    ],
                    "hours": round(
                        season_minutes / 60,
                        2,
                    ),
                    "known_pay": season_pay,
                    "unresolved_count": (
                        season_unresolved
                    ),
                    "classes": class_rows,
                }
            )

        seasons.sort(
            key=lambda row: (
                row["season"].start_date,
                row["season"].name.lower(),
            )
        )

        extra_work_minutes = sum(
            entry["minutes"]
            for entry in extra_work_entries
        )
        extra_work_pay = sum(
            (
                entry["amount"]
                for entry in extra_work_entries
                if entry["amount"] is not None
            ),
            Decimal("0.00"),
        )
        extra_work_unresolved = sum(
            1
            for entry in extra_work_entries
            if entry["amount"] is None
        )

        teacher_rows.append(
            {
                "instructor": instructor,
                "hours": (
                    staff_total["net_hours"]
                    if staff_total
                    else Decimal("0.00")
                ),
                "known_pay": (
                    staff_total["total_pay"]
                    if staff_total
                    else Decimal("0.00")
                ),
                "unresolved_count": (
                    staff_total[
                        "unresolved_count"
                    ]
                    if staff_total
                    else 0
                ),
                "seasons": seasons,
                "extra_work": {
                    "hours": round(
                        extra_work_minutes / 60,
                        2,
                    ),
                    "known_pay": (
                        extra_work_pay
                    ),
                    "unresolved_count": (
                        extra_work_unresolved
                    ),
                    "has_activity": bool(
                        extra_work_entries
                    ),
                },
            }
        )

    return {
        "teachers": teacher_rows,
        "hours": payroll_preview[
            "net_hours_total"
        ],
        "known_pay": payroll_preview[
            "known_pay_total"
        ],
        "unresolved_count": payroll_preview[
            "unresolved_total"
        ],
    }


@login_required
def payroll_management(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    unlock_response = _require_payroll_unlock(
        request,
        studio,
    )
    if unlock_response:
        return unlock_response

    payroll_settings, _created = (
        PayrollSettings.objects.get_or_create(
            studio=studio
        )
    )

    settings_form = PayrollSettingsForm(
        request.POST or None,
        instance=payroll_settings,
    )

    if (
        request.method == "POST"
        and request.POST.get("action")
        == "save_settings"
        and settings_form.is_valid()
    ):
        settings_form.save()
        messages.success(
            request,
            "Payroll settings saved.",
        )
        return redirect(
            "instructors:payroll_management",
            studio_slug=studio.slug,
        )

    instructors = list(
        Instructor.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related("user")
        .prefetch_related(
            "compensation_records"
        )
        .order_by(
            "last_name",
            "first_name",
        )
    )

    today = timezone.localdate()
    rows = []

    for instructor in instructors:
        records = list(
            instructor.compensation_records.all()
        )

        current = next(
            (
                record
                for record in records
                if (
                    record.effective_start <= today
                    and (
                        record.effective_end is None
                        or record.effective_end >= today
                    )
                )
            ),
            None,
        )

        rows.append(
            {
                "instructor": instructor,
                "current_compensation": current,
                "history_count": len(records),
            }
        )

    preview_start, preview_end = (
        _preview_date_range(request)
    )

    payroll_preview = calculate_payroll(
        studio=studio,
        start_date=preview_start,
        end_date=preview_end,
    )

    payroll_tree = _admin_payroll_tree(
        studio=studio,
        active_instructors=instructors,
        payroll_preview=payroll_preview,
    )

    return render(
        request,
        "instructors/payroll_management.html",
        {
            "studio": studio,
            "role": "administrator",
            "payroll_settings": payroll_settings,
            "settings_form": settings_form,
            "staff_rows": rows,
            "unlock_minutes": (
                PAYROLL_UNLOCK_SECONDS // 60
            ),
            "preview_start": preview_start,
            "preview_end": preview_end,
            "payroll_preview": payroll_preview,
            "payroll_tree": payroll_tree,
        },
    )


@login_required
def teacher_hours_pay(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _teacher_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = _teacher_instructor(
        request,
        studio,
    )

    season_rows = _teacher_season_tree(
        studio=studio,
        instructor=instructor,
    )

    if season_rows:
        overall_start = min(
            row["season"].start_date
            for row in season_rows
        )
        overall_end = max(
            row["season"].end_date
            for row in season_rows
        )

        overall = calculate_payroll(
            studio=studio,
            start_date=overall_start,
            end_date=overall_end,
            instructor_ids=[instructor.pk],
        )

        teacher_total = next(
            (
                row
                for row in overall["staff_rows"]
                if row["instructor"].pk
                == instructor.pk
            ),
            None,
        )
    else:
        teacher_total = None

    return render(
        request,
        "instructors/teacher_hours_pay.html",
        {
            "studio": studio,
            "role": "teacher",
            "instructor": instructor,
            "season_rows": season_rows,
            "overall_hours": (
                teacher_total["net_hours"]
                if teacher_total
                else 0
            ),
            "overall_pay": (
                teacher_total["total_pay"]
                if teacher_total
                else 0
            ),
            "overall_unresolved": (
                teacher_total[
                    "unresolved_count"
                ]
                if teacher_total
                else 0
            ),
            "overall_unresolved_reasons": (
                teacher_total[
                    "unresolved_reasons"
                ]
                if teacher_total
                else []
            ),
        },
    )


@login_required
def teacher_hours_pay_export(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _teacher_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    instructor = _teacher_instructor(
        request,
        studio,
    )

    season_rows = _teacher_season_tree(
        studio=studio,
        instructor=instructor,
    )

    response = HttpResponse(
        content_type="text/csv",
    )
    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="'
        f'{studio.slug}-{instructor.pk}-hours-pay.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            "Season",
            "Date",
            "Source",
            "Class",
            "Hours",
            "Rate",
            "Amount",
            "Status",
            "Note",
        ]
    )

    for season_row in season_rows:
        for class_row in season_row["classes"]:
            for entry in class_row["entries"]:
                writer.writerow(
                    [
                        season_row["season"].name,
                        entry["date"].isoformat(),
                        entry["source_type"],
                        (
                            entry[
                                "class_instance"
                            ].name
                            if entry[
                                "class_instance"
                            ]
                            else "Extra Work"
                        ),
                        entry["hours"],
                        entry["rate"] or "",
                        entry["amount"] or "",
                        (
                            "Ready"
                            if entry["is_resolved"]
                            else "Unresolved"
                        ),
                        entry["note"],
                    ]
                )

    return response


@login_required
def payroll_compensation(
    request,
    studio_slug,
    instructor_id,
    compensation_id=None,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    unlock_response = _require_payroll_unlock(
        request,
        studio,
    )
    if unlock_response:
        return unlock_response

    instructor = get_object_or_404(
        Instructor,
        pk=instructor_id,
        studio=studio,
    )

    compensation = None
    if compensation_id is not None:
        compensation = get_object_or_404(
            InstructorCompensation,
            pk=compensation_id,
            instructor=instructor,
        )

    form = InstructorCompensationForm(
        request.POST or None,
        instance=compensation,
        instructor=instructor,
    )

    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.instructor = instructor

        if saved.created_by_id is None:
            saved.created_by = request.user

        saved.full_clean()
        saved.save()

        messages.success(
            request,
            (
                "Compensation record updated."
                if compensation
                else "Compensation record added."
            ),
        )
        return redirect(
            "instructors:payroll_compensation",
            studio_slug=studio.slug,
            instructor_id=instructor.pk,
        )

    history = (
        instructor.compensation_records
        .select_related("created_by")
        .all()
    )

    return render(
        request,
        "instructors/payroll_compensation.html",
        {
            "studio": studio,
            "role": "administrator",
            "instructor": instructor,
            "form": form,
            "editing_record": compensation,
            "compensation_history": history,
        },
    )
