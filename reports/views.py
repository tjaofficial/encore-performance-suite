import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from attendance.models import AttendanceRecord
from billing.models import (
    Charge,
    Credit,
    FamilyAccount,
    Payment,
    PaymentAllocation,
    RecurringChargeSchedule,
)
from classes.models import Class, ClassMeeting, Season
from enrollments.models import Enrollment
from evaluations.models import (
    EvaluationCriterion,
    EvaluationRating,
    StudentEvaluation,
)
from families.models import Family
from instructors.models import Instructor
from students.models import Student
from studios.models import Studio


def _workspace_role(request, studio):
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

    if role != "administrator":
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists():
        return "administrator"

    return None


def _attendance_rate_for_queryset(records):
    total = records.count()

    if not total:
        return None

    attended = records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()

    return round(
        (attended / total) * 100
    )


REPORT_CATALOG = [
    {
        "slug": "overview",
        "title": "Overview & Insights",
        "description": "High-level studio health, trends, and action-oriented reports.",
        "reports": [
            ("studio-health", "Studio Health", "Enrollment, capacity, attendance, families, and staff at a glance.", "dashboard"),
            ("needs-attention", "Needs Attention", "Students, classes, balances, absences, and setup issues that may need action.", "live"),
            ("business-insights", "Business Insights", "Operational trends and decision-support metrics across the studio.", "live"),
            ("enrollment-trends", "Enrollment Trends", "Enrollment growth and changes over time.", "live"),
            ("revenue-trends", "Revenue Trends", "Charges, collections, and revenue trends over time.", "live"),
            ("retention", "Retention", "Returning students and retention movement across seasons.", "live"),
            ("class-opportunities", "Class Opportunity Report", "Full classes, waitlists, underfilled classes, and expansion opportunities.", "live"),
        ],
    },
    {
        "slug": "classes",
        "title": "Classes & Enrollment",
        "description": "Schedules, rosters, enrollment, capacity, drops, and class operations.",
        "reports": [
            ("class-list", "Class List", "Classes with season, instructor, capacity, enrollment, and tuition.", "live"),
            ("class-schedule", "Class Schedule", "Class schedule by season, instructor, and location.", "live"),
            ("class-roster", "Class Roster", "Student rosters for classes in the selected season.", "live"),
            ("enrollment-list", "Enrollment List", "Active, waitlisted, dropped, and other enrollment records.", "live"),
            ("class-capacity", "Class Capacity", "Enrollment, availability, utilization, and waitlist pressure.", "live"),
            ("drop-summary", "Drop Summary", "Enrollment drops summarized by class and season.", "live"),
            ("class-drop-history", "Class Drop History", "Detailed class withdrawal history.", "live"),
            ("cancelled-classes", "Cancelled Classes", "Cancelled class sessions and classes.", "planned"),
            ("makeup-classes", "Make-up Classes", "Make-up class activity and usage.", "planned"),
            ("instructor-work-schedules", "Instructor Work Schedules", "Scheduled teaching workload by instructor.", "live"),
            ("class-skills", "Class Skills Worksheet", "Class skills and evaluation criteria worksheet.", "planned"),
            ("students-multiple-classes", "Students in Multiple Classes", "Students enrolled in more than one class.", "live"),
        ],
    },
    {
        "slug": "students",
        "title": "Students & Families",
        "description": "Student, family, contact, retention, attendance, and participation reporting.",
        "reports": [
            ("student-list", "Student List", "Studio student directory with active class counts.", "live"),
            ("student-class-list", "Student / Class List", "Students cross-referenced with active class enrollment.", "live"),
            ("student-attendance", "Student Attendance", "Attendance percentage and attendance totals by student.", "live"),
            ("student-absences", "Student Absences", "Students with absence counts for the selected season.", "live"),
            ("student-drop-history", "Student Drop History", "Classes each student dropped or withdrew from.", "live"),
            ("student-makeups", "Student Make-ups / Trials / Drop-ins", "Special attendance and participation records.", "planned"),
            ("students-not-returning", "Students Not Returning", "Students active previously but not returning for a later season.", "live"),
            ("student-retention-list", "Retention List", "Student retention status across seasons.", "live"),
            ("student-skills", "Student Skills", "Skills and evaluation progress by student.", "planned"),
            ("student-contact-list", "Student Contact List", "Student and family contact information.", "live"),
            ("preapproved-students", "Pre-approved Student/Class List", "Pre-approved student and class combinations.", "planned"),
            ("student-signin", "Student Sign-in Sheets", "Printable class sign-in sheets.", "planned"),
            ("family-list", "Family List", "Family directory with students and billing account status.", "live"),
            ("family-zip-codes", "Family ZIP Codes", "Geographic distribution of studio families.", "live"),
            ("family-notes", "Family Notes", "Family notes and administrative context.", "live"),
            ("family-referrals", "How Families Heard About Us", "Referral and marketing source metrics.", "live"),
            ("classes-per-family", "Classes per Family", "Family participation by number of class enrollments.", "live"),
        ],
    },
    {
        "slug": "attendance",
        "title": "Attendance & Absences",
        "description": "Attendance quality, repeated absences, class trends, and risk signals.",
        "reports": [
            ("class-attendance", "Class Attendance", "Attendance rate by class for the selected season.", "live"),
            ("student-absences", "Repeated Student Absences", "Students with the most absences in the selected season.", "live"),
            ("attendance-by-instructor", "Attendance by Instructor", "Attendance performance grouped by instructor.", "live"),
            ("attendance-by-day", "Attendance by Day of Week", "Attendance trends by class meeting day.", "live"),
            ("attendance-by-type", "Attendance by Class Type", "Attendance rates grouped by class type.", "live"),
            ("consecutive-absences", "Consecutive Absences", "Students missing multiple classes in a row.", "live"),
            ("paying-not-attending", "Paying but Not Attending", "Active billed enrollments with concerning attendance.", "live"),
        ],
    },
    {
        "slug": "billing",
        "title": "Billing & Payments",
        "description": "Charges, payments, overdue accounts, allocation, revenue, and collection reporting.",
        "reports": [
            ("charges-summary", "Charges Summary", "Charges by status and family with remaining balances.", "live"),
            ("charges-list", "Charges List", "Detailed charge records.", "live"),
            ("payments-list", "Payments List", "Payments received with method and status.", "live"),
            ("overdue-list", "Overdue / Aging List", "Open and partially-paid charges that are past due.", "live"),
            ("family-balances", "Family Charges / Payments Summary", "Family balances, charges, payments, and credits.", "live"),
            ("class-payments", "Class Payments Summary", "Charges and collections grouped by class.", "live"),
            ("payment-allocation", "Payment Allocation Detail", "How payments were allocated against charges.", "live"),
            ("expected-vs-collected", "Expected vs Collected Tuition", "Expected tuition compared with money collected.", "live"),
            ("revenue-by-class", "Revenue by Class", "Revenue performance grouped by class.", "live"),
            ("revenue-by-season", "Revenue by Season", "Revenue performance grouped by season.", "live"),
            ("revenue-by-location", "Revenue by Location", "Revenue grouped by studio location.", "live"),
            ("registration-fees", "Registration Fees Collected", "Registration fee charge and collection reporting.", "live"),
            ("late-fees", "Late Fees Collected", "Late-fee activity and collections.", "live"),
            ("credits-discounts", "Credits / Discounts", "Credits, scholarships, promotions, and discounts.", "live"),
            ("deposits", "Deposit Summary", "Deposit and settlement summaries.", "planned"),
            ("sales-tax", "Sales Tax Charged", "Tax charged on applicable transactions.", "planned"),
            ("payment-plans", "Payment Plans / Promos", "Recurring plans, promotions, and special arrangements.", "live"),
            ("season-charges-trend", "Season Charges Trend", "Charge activity across the selected season.", "live"),
        ],
    },
    {
        "slug": "instructors",
        "title": "Instructors & Staff",
        "description": "Faculty workload, schedules, attendance, time off, and class performance.",
        "reports": [
            ("instructor-list", "Instructor List", "Instructor directory and active class workload.", "live"),
            ("instructor-class-attendance", "Instructor / Class Attendance", "Attendance based on class schedules.", "live"),
            ("instructor-time-attendance", "Instructor Attendance / Timesheets", "Attendance and work activity based on timesheets.", "planned"),
            ("instructor-work-schedules", "Instructor Work Schedules", "Teaching schedule by instructor.", "planned"),
            ("teacher-time-off", "Teacher Time-Off History", "Requested and approved teacher time off.", "planned"),
            ("substitute-assignments", "Substitute Assignments", "Substitute coverage history by teacher and class.", "planned"),
            ("teaching-hours", "Teaching Hours", "Scheduled and recorded teaching hours.", "live"),
        ],
    },
    {
        "slug": "evaluations",
        "title": "Evaluations & Progress",
        "description": "Evaluation completion, student progress, criteria, and teacher follow-through.",
        "reports": [
            ("evaluation-completion", "Evaluation Completion", "Completion status by class and instructor.", "live"),
            ("missing-evaluations", "Missing Evaluations", "Students or classes still needing evaluations.", "live"),
            ("evaluation-status", "Draft vs Published", "Evaluation workflow status.", "live"),
            ("criterion-averages", "Criterion Averages", "Average performance by evaluation criterion.", "live"),
            ("student-progress", "Student Progress Trends", "Progress across multiple evaluations.", "live"),
            ("overdue-evaluations", "Overdue Evaluations", "Evaluations that need completion or publishing.", "live"),
        ],
    },
    {
        "slug": "performance",
        "title": "Performance & Costumes",
        "description": "Dances, performances, music, costumes, measurements, and production readiness.",
        "reports": [
            ("event-list", "Event List", "Performance and event overview.", "planned"),
            ("event-cast-summary", "Event Cast Summary", "Cast counts and class participation by event.", "planned"),
            ("event-cast-list", "Event Cast List", "Detailed event cast roster.", "planned"),
            ("family-event-list", "Family Event List", "Events cross-referenced by family.", "planned"),
            ("event-program", "Event Program", "Printable performance program data.", "planned"),
            ("dances-by-season", "Dances by Season", "Dances attached to current-season classes.", "planned"),
            ("performance-readiness", "Performance Readiness", "Music, costumes, measurements, and Drawing Board completion.", "planned"),
            ("costume-order-list", "Costume Order List", "Costume ordering status and quantities.", "planned"),
            ("student-costume-list", "Student Costume List", "Costumes assigned to each student.", "planned"),
            ("measurement-worksheet", "Costume / Student Measurement Worksheet", "Measurement collection and completeness.", "planned"),
            ("costume-labels", "Costume Labels", "Printable costume labels.", "planned"),
            ("costume-purchase-orders", "Costume Purchase Orders", "Vendor purchase-order data.", "planned"),
            ("costume-vendors", "Costume Vendors", "Vendor directory and usage.", "planned"),
            ("vendor-size-charts", "Costume Vendor Size Charts", "Vendor sizing references.", "planned"),
        ],
    },
    {
        "slug": "communications",
        "title": "Communications & System",
        "description": "Email delivery, communication activity, and account usage.",
        "reports": [
            ("emails-sent", "Emails Sent", "Campaign and transactional email activity.", "planned"),
            ("bounced-emails", "Bounced Emails / Reported as Spam", "Delivery problems and complaint history.", "planned"),
            ("email-performance", "Email Delivery / Open / Click", "Email campaign engagement and delivery performance.", "planned"),
            ("announcement-activity", "Announcement Activity", "Published announcements and read activity.", "planned"),
            ("last-login", "Last Log-In", "User account activity and last login dates.", "planned"),
        ],
    },
    {
        "slug": "documents",
        "title": "Documents & Letters",
        "description": "Printable statements, confirmations, labels, receipts, and studio documents.",
        "reports": [
            ("summary-invoice", "Summary Invoice", "Family invoice summary.", "planned"),
            ("statement-letters", "Statement Letters", "Printable family account statements.", "planned"),
            ("transaction-detail", "Transaction Detail", "Detailed transaction letter/report.", "planned"),
            ("student-summary-receipt", "Student Summary Receipt", "Student-level payment receipt.", "planned"),
            ("class-confirmation", "Class Confirmation", "Class enrollment confirmation.", "planned"),
            ("event-confirmation", "Event Confirmation / Performance Info", "Performance confirmation and information sheet.", "planned"),
            ("family-mailing-labels", "Mailing Labels — Families", "One mailing label per family.", "planned"),
            ("student-mailing-labels", "Mailing Labels — Students", "One mailing label per student.", "planned"),
            ("birthday-card", "Birthday Card Letter", "Birthday card / letter output.", "planned"),
            ("report-card", "Report Card", "Printable student evaluation report card.", "planned"),
        ],
    },
]


def _report_catalog():
    return REPORT_CATALOG


def _report_entry(report_key):
    for category in REPORT_CATALOG:
        for key, title, description, status in category["reports"]:
            if key == report_key:
                return {
                    "key": key,
                    "title": title,
                    "description": description,
                    "status": status,
                    "category": category["title"],
                }
    return None


def _selected_season_for_request(request, studio):
    seasons = Season.objects.filter(
        studio=studio,
    ).order_by(
        "-start_date",
        "name",
    )

    season_id = request.GET.get(
        "season",
        "",
    ).strip()

    selected = None

    if season_id:
        selected = seasons.filter(
            pk=season_id,
        ).first()

    if selected is None:
        selected = (
            seasons.filter(is_active=True).first()
            or seasons.first()
        )

    return seasons, selected


def _report_payload(
    report_key,
    *,
    studio,
    selected_season=None,
):
    entry = _report_entry(report_key)

    if entry is None or entry["status"] not in {
        "live",
    }:
        return None

    if report_key == "student-list":
        students = (
            Student.objects
            .filter(studio=studio)
            .select_related("family")
            .annotate(
                active_class_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.ACTIVE,
                    ),
                    distinct=True,
                )
            )
            .order_by("last_name", "first_name")
        )

        rows = [
            {
                "cells": [
                    f"{student.first_name} {student.last_name}",
                    str(student.family) if student.family else "—",
                    str(student.age) if student.age is not None else "—",
                    "Active" if student.is_active else "Inactive",
                    str(student.active_class_count),
                    "Yes" if student.enrollment_blocked else "No",
                ]
            }
            for student in students
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Family",
                "Age",
                "Status",
                "Active Classes",
                "Enrollment Blocked",
            ],
            "rows": rows,
        }

    if report_key == "family-list":
        families = (
            Family.objects
            .filter(studio=studio)
            .annotate(
                student_count=Count("students", distinct=True),
                guardian_count=Count("guardians", distinct=True),
            )
            .order_by("family_name")
        )

        accounts = {
            item.family_id: item
            for item in FamilyAccount.objects
            .filter(studio=studio)
            .select_related("family")
        }

        rows = []

        for family in families:
            account = accounts.get(family.id)

            rows.append(
                {
                    "cells": [
                        str(family),
                        str(family.student_count),
                        str(family.guardian_count),
                        "Active" if family.is_active else "Inactive",
                        f"${account.balance:.2f}" if account else "No account",
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Family",
                "Students",
                "Guardians",
                "Status",
                "Balance",
            ],
            "rows": rows,
        }

    if report_key == "instructor-list":
        instructors = (
            Instructor.objects
            .filter(studio=studio)
            .annotate(
                primary_count=Count(
                    "primary_classes",
                    filter=Q(primary_classes__is_active=True),
                    distinct=True,
                ),
                assistant_count=Count(
                    "assistant_classes",
                    filter=Q(assistant_classes__is_active=True),
                    distinct=True,
                ),
            )
            .order_by("last_name", "first_name")
        )

        rows = [
            {
                "cells": [
                    instructor.full_name,
                    instructor.email or "—",
                    instructor.phone or "—",
                    str(instructor.primary_count),
                    str(instructor.assistant_count),
                    "Active" if instructor.is_active else "Inactive",
                ]
            }
            for instructor in instructors
        ]

        return {
            **entry,
            "columns": [
                "Instructor",
                "Email",
                "Phone",
                "Primary Classes",
                "Assistant Classes",
                "Status",
            ],
            "rows": rows,
        }

    if report_key in {
        "class-list",
        "class-capacity",
        "class-attendance",
    }:
        classes = (
            Class.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .select_related(
                "season",
                "class_type",
                "instructor",
                "tuition_plan",
            )
            .annotate(
                active_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.ACTIVE,
                    ),
                    distinct=True,
                ),
                waitlist_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.WAITLISTED,
                    ),
                    distinct=True,
                ),
            )
            .order_by("name")
        )

        if selected_season:
            classes = classes.filter(
                season=selected_season,
            )

        rows = []

        for item in classes:
            attendance = AttendanceRecord.objects.filter(
                session__class_instance=item,
            )

            attendance_rate = _attendance_rate_for_queryset(
                attendance
            )

            available = max(
                item.capacity - item.active_count,
                0,
            )

            percent = (
                round(
                    item.active_count
                    / item.capacity
                    * 100
                )
                if item.capacity
                else 0
            )

            if report_key == "class-attendance":
                cells = [
                    item.class_id,
                    item.name,
                    item.instructor.full_name,
                    str(item.active_count),
                    (
                        f"{attendance_rate}%"
                        if attendance_rate is not None
                        else "—"
                    ),
                ]
            elif report_key == "class-capacity":
                cells = [
                    item.class_id,
                    item.name,
                    str(item.capacity),
                    str(item.active_count),
                    str(available),
                    str(item.waitlist_count),
                    f"{percent}%",
                ]
            else:
                cells = [
                    item.class_id,
                    item.name,
                    item.class_type.name,
                    item.season.name,
                    item.instructor.full_name,
                    f"{item.active_count}/{item.capacity}",
                    (
                        f"${item.tuition_amount:.2f}"
                        if item.tuition_amount is not None
                        else "Not set"
                    ),
                    (
                        item.tuition_plan.get_frequency_display()
                        if item.tuition_plan_id
                        else "No policy"
                    ),
                ]

            rows.append({"cells": cells})

        columns = {
            "class-attendance": [
                "Class ID",
                "Class",
                "Instructor",
                "Enrollment",
                "Attendance",
            ],
            "class-capacity": [
                "Class ID",
                "Class",
                "Capacity",
                "Enrolled",
                "Available",
                "Waitlist",
                "Full",
            ],
            "class-list": [
                "Class ID",
                "Class",
                "Type",
                "Season",
                "Instructor",
                "Enrollment",
                "Tuition",
                "Billing Policy",
            ],
        }[report_key]

        return {
            **entry,
            "columns": columns,
            "rows": rows,
        }

    if report_key == "enrollment-list":
        enrollments = (
            Enrollment.objects
            .filter(
                class_instance__studio=studio,
            )
            .select_related(
                "student",
                "class_instance",
                "class_instance__season",
            )
            .order_by(
                "student__last_name",
                "student__first_name",
            )
        )

        if selected_season:
            enrollments = enrollments.filter(
                class_instance__season=selected_season,
            )

        rows = [
            {
                "cells": [
                    f"{item.student.first_name} {item.student.last_name}",
                    item.class_instance.name,
                    item.class_instance.season.name,
                    item.get_status_display(),
                    item.get_source_display(),
                    (
                        f"${item.tuition_override:.2f}"
                        if item.tuition_override is not None
                        else (
                            f"${item.class_instance.tuition_amount:.2f}"
                            if item.class_instance.tuition_amount is not None
                            else "Not set"
                        )
                    ),
                ]
            }
            for item in enrollments
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Class",
                "Season",
                "Status",
                "Source",
                "Tuition",
            ],
            "rows": rows,
        }

    if report_key == "student-absences":
        records = AttendanceRecord.objects.filter(
            student__studio=studio,
            status=AttendanceRecord.Status.ABSENT,
        )

        if selected_season:
            records = records.filter(
                session__class_instance__season=selected_season,
            )

        grouped = (
            records
            .values(
                "student_id",
                "student__first_name",
                "student__last_name",
            )
            .annotate(
                absence_count=Count("id"),
            )
            .order_by(
                "-absence_count",
                "student__last_name",
                "student__first_name",
            )
        )

        rows = [
            {
                "cells": [
                    (
                        f"{item['student__first_name']} "
                        f"{item['student__last_name']}"
                    ),
                    str(item["absence_count"]),
                ]
            }
            for item in grouped
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Absences",
            ],
            "rows": rows,
        }

    if report_key in {
        "charges-summary",
        "charges-list",
        "overdue-list",
    }:
        charges = (
            Charge.objects
            .filter(
                account__studio=studio,
            )
            .select_related(
                "account__family",
                "student",
                "class_instance",
            )
            .order_by("-created_at")
        )

        if report_key == "overdue-list":
            from django.utils import timezone

            charges = charges.filter(
                status__in=[
                    Charge.Status.OPEN,
                    Charge.Status.PARTIALLY_PAID,
                ],
                due_date__lt=timezone.localdate(),
            )

        rows = []

        for charge in charges:
            rows.append(
                {
                    "cells": [
                        str(charge.account.family),
                        (
                            f"{charge.student.first_name} "
                            f"{charge.student.last_name}"
                            if charge.student_id
                            else "—"
                        ),
                        (
                            charge.class_instance.name
                            if charge.class_instance_id
                            else "—"
                        ),
                        charge.get_charge_type_display(),
                        charge.description,
                        f"${charge.amount:.2f}",
                        f"${charge.balance_remaining:.2f}",
                        charge.get_status_display(),
                        (
                            charge.due_date.strftime("%b %-d, %Y")
                            if charge.due_date
                            else "—"
                        ),
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Family",
                "Student",
                "Class",
                "Type",
                "Description",
                "Charge",
                "Balance",
                "Status",
                "Due",
            ],
            "rows": rows,
        }

    if report_key == "payments-list":
        payments = (
            Payment.objects
            .filter(
                account__studio=studio,
            )
            .select_related(
                "account__family",
            )
            .order_by("-paid_at")
        )

        rows = [
            {
                "cells": [
                    str(item.account.family),
                    item.get_method_display(),
                    f"${item.amount:.2f}",
                    item.get_status_display(),
                    item.paid_at.strftime("%b %-d, %Y"),
                    f"${item.allocated_amount:.2f}",
                    f"${item.unallocated_amount:.2f}",
                ]
            }
            for item in payments
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Method",
                "Amount",
                "Status",
                "Paid",
                "Allocated",
                "Unallocated",
            ],
            "rows": rows,
        }

    if report_key == "family-balances":
        accounts = (
            FamilyAccount.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .select_related(
                "family",
            )
            .order_by(
                "family__family_name",
            )
        )

        rows = [
            {
                "cells": [
                    str(item.family),
                    f"${item.total_charges:.2f}",
                    f"${item.total_payments:.2f}",
                    f"${item.total_credits:.2f}",
                    f"${item.balance:.2f}",
                    "Yes" if item.autopay_enabled else "No",
                ]
            }
            for item in accounts
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Charges",
                "Payments",
                "Credits",
                "Balance",
                "Autopay",
            ],
            "rows": rows,
        }


    if report_key == "class-schedule":
        meetings = (
            ClassMeeting.objects
            .filter(
                class_instance__studio=studio,
                is_active=True,
                class_instance__is_active=True,
            )
            .select_related(
                "class_instance",
                "class_instance__season",
                "class_instance__instructor",
                "room",
                "location",
            )
            .order_by(
                "day_of_week",
                "start_time",
                "class_instance__name",
            )
        )

        if selected_season:
            meetings = meetings.filter(
                class_instance__season=selected_season,
            )

        rows = [
            {
                "cells": [
                    item.class_instance.class_id,
                    item.class_instance.name,
                    item.get_day_of_week_display(),
                    item.start_time.strftime("%-I:%M %p"),
                    f"{item.duration_minutes} min",
                    (
                        str(item.room)
                        if item.room_id
                        else (
                            str(item.location)
                            if item.location_id
                            else "—"
                        )
                    ),
                    item.class_instance.instructor.full_name,
                ]
            }
            for item in meetings
        ]

        return {
            **entry,
            "columns": [
                "Class ID",
                "Class",
                "Day",
                "Start",
                "Duration",
                "Room / Location",
                "Instructor",
            ],
            "rows": rows,
        }

    if report_key == "class-roster":
        enrollments = (
            Enrollment.objects
            .filter(
                class_instance__studio=studio,
                status=Enrollment.Status.ACTIVE,
            )
            .select_related(
                "student",
                "student__family",
                "class_instance",
                "class_instance__season",
            )
            .order_by(
                "class_instance__name",
                "student__last_name",
                "student__first_name",
            )
        )

        if selected_season:
            enrollments = enrollments.filter(
                class_instance__season=selected_season,
            )

        rows = [
            {
                "cells": [
                    item.class_instance.class_id,
                    item.class_instance.name,
                    f"{item.student.first_name} {item.student.last_name}",
                    str(item.student.age),
                    (
                        str(item.student.family)
                        if item.student.family_id
                        else "—"
                    ),
                    item.get_source_display(),
                ]
            }
            for item in enrollments
        ]

        return {
            **entry,
            "columns": [
                "Class ID",
                "Class",
                "Student",
                "Age",
                "Family",
                "Source",
            ],
            "rows": rows,
        }

    if report_key in {
        "drop-summary",
        "class-drop-history",
        "student-drop-history",
    }:
        dropped = (
            Enrollment.objects
            .filter(
                class_instance__studio=studio,
                status=Enrollment.Status.DROPPED,
            )
            .select_related(
                "student",
                "class_instance",
                "class_instance__season",
            )
            .order_by(
                "-dropped_at",
                "class_instance__name",
            )
        )

        if selected_season:
            dropped = dropped.filter(
                class_instance__season=selected_season,
            )

        if report_key == "drop-summary":
            grouped = (
                dropped
                .values(
                    "class_instance__class_id",
                    "class_instance__name",
                )
                .annotate(
                    drop_count=Count("id"),
                )
                .order_by(
                    "-drop_count",
                    "class_instance__name",
                )
            )

            rows = [
                {
                    "cells": [
                        item["class_instance__class_id"],
                        item["class_instance__name"],
                        str(item["drop_count"]),
                    ]
                }
                for item in grouped
            ]

            return {
                **entry,
                "columns": [
                    "Class ID",
                    "Class",
                    "Drops",
                ],
                "rows": rows,
            }

        rows = [
            {
                "cells": [
                    f"{item.student.first_name} {item.student.last_name}",
                    item.class_instance.class_id,
                    item.class_instance.name,
                    item.class_instance.season.name,
                    (
                        item.dropped_at.strftime("%b %-d, %Y")
                        if item.dropped_at
                        else "—"
                    ),
                    item.notes or "—",
                ]
            }
            for item in dropped
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Class ID",
                "Class",
                "Season",
                "Dropped",
                "Notes",
            ],
            "rows": rows,
        }

    if report_key in {
        "students-multiple-classes",
        "student-class-list",
    }:
        students = (
            Student.objects
            .filter(
                studio=studio,
            )
            .annotate(
                active_class_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.ACTIVE,
                        **(
                            {
                                "enrollments__class_instance__season": selected_season,
                            }
                            if selected_season
                            else {}
                        )
                    ),
                    distinct=True,
                )
            )
            .order_by(
                "last_name",
                "first_name",
            )
        )

        if report_key == "students-multiple-classes":
            students = students.filter(
                active_class_count__gt=1,
            )

            rows = [
                {
                    "cells": [
                        f"{student.first_name} {student.last_name}",
                        str(student.active_class_count),
                        ", ".join(
                            student.enrollments
                            .filter(
                                status=Enrollment.Status.ACTIVE,
                                **(
                                    {
                                        "class_instance__season": selected_season,
                                    }
                                    if selected_season
                                    else {}
                                ),
                            )
                            .values_list(
                                "class_instance__name",
                                flat=True,
                            )
                        ),
                    ]
                }
                for student in students
            ]

            return {
                **entry,
                "columns": [
                    "Student",
                    "Active Classes",
                    "Classes",
                ],
                "rows": rows,
            }

        enrollments = (
            Enrollment.objects
            .filter(
                class_instance__studio=studio,
                status=Enrollment.Status.ACTIVE,
            )
            .select_related(
                "student",
                "student__family",
                "class_instance",
            )
            .order_by(
                "student__last_name",
                "student__first_name",
                "class_instance__name",
            )
        )

        if selected_season:
            enrollments = enrollments.filter(
                class_instance__season=selected_season,
            )

        rows = [
            {
                "cells": [
                    f"{item.student.first_name} {item.student.last_name}",
                    (
                        str(item.student.family)
                        if item.student.family_id
                        else "—"
                    ),
                    item.class_instance.class_id,
                    item.class_instance.name,
                    item.get_source_display(),
                ]
            }
            for item in enrollments
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Family",
                "Class ID",
                "Class",
                "Source",
            ],
            "rows": rows,
        }

    if report_key == "student-attendance":
        records = (
            AttendanceRecord.objects
            .filter(
                student__studio=studio,
            )
            .select_related("student")
        )

        if selected_season:
            records = records.filter(
                session__class_instance__season=selected_season,
            )

        student_ids = (
            records.values_list(
                "student_id",
                flat=True,
            )
            .distinct()
        )

        rows = []

        for student in (
            Student.objects
            .filter(
                studio=studio,
                id__in=student_ids,
            )
            .order_by(
                "last_name",
                "first_name",
            )
        ):
            student_records = records.filter(
                student=student,
            )

            total = student_records.count()
            attended = student_records.filter(
                status__in=[
                    AttendanceRecord.Status.PRESENT,
                    AttendanceRecord.Status.LATE,
                    AttendanceRecord.Status.LEFT_EARLY,
                ]
            ).count()
            absent = student_records.filter(
                status=AttendanceRecord.Status.ABSENT,
            ).count()
            excused = student_records.filter(
                status=AttendanceRecord.Status.EXCUSED,
            ).count()

            rate = (
                round(attended / total * 100)
                if total
                else 0
            )

            rows.append(
                {
                    "cells": [
                        f"{student.first_name} {student.last_name}",
                        str(total),
                        str(attended),
                        str(absent),
                        str(excused),
                        f"{rate}%",
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Student",
                "Records",
                "Attended",
                "Absent",
                "Excused",
                "Attendance Rate",
            ],
            "rows": rows,
        }

    if report_key in {
        "students-not-returning",
        "student-retention-list",
        "retention",
    }:
        seasons = list(
            Season.objects
            .filter(studio=studio)
            .order_by("-start_date")
        )

        current_season = selected_season or (
            seasons[0] if seasons else None
        )

        previous_season = None

        if current_season:
            for season in seasons:
                if season.start_date < current_season.start_date:
                    previous_season = season
                    break

        if not current_season or not previous_season:
            return {
                **entry,
                "columns": [
                    "Student",
                    "Previous Season",
                    "Current Season",
                    "Retention Status",
                ],
                "rows": [],
            }

        previous_ids = set(
            Enrollment.objects
            .filter(
                class_instance__season=previous_season,
                status__in=[
                    Enrollment.Status.ACTIVE,
                    Enrollment.Status.COMPLETED,
                ],
            )
            .values_list(
                "student_id",
                flat=True,
            )
        )

        current_ids = set(
            Enrollment.objects
            .filter(
                class_instance__season=current_season,
                status=Enrollment.Status.ACTIVE,
            )
            .values_list(
                "student_id",
                flat=True,
            )
        )

        if report_key == "students-not-returning":
            target_ids = previous_ids - current_ids
        else:
            target_ids = previous_ids

        students = (
            Student.objects
            .filter(
                studio=studio,
                id__in=target_ids,
            )
            .order_by(
                "last_name",
                "first_name",
            )
        )

        rows = [
            {
                "cells": [
                    f"{student.first_name} {student.last_name}",
                    previous_season.name,
                    current_season.name,
                    (
                        "Returned"
                        if student.id in current_ids
                        else "Not Returning"
                    ),
                ]
            }
            for student in students
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Previous Season",
                "Current Season",
                "Retention Status",
            ],
            "rows": rows,
        }

    if report_key == "student-contact-list":
        students = (
            Student.objects
            .filter(studio=studio)
            .select_related("family")
            .order_by(
                "last_name",
                "first_name",
            )
        )

        rows = [
            {
                "cells": [
                    f"{item.first_name} {item.last_name}",
                    (
                        str(item.family)
                        if item.family_id
                        else "—"
                    ),
                    (
                        item.family.primary_email
                        if item.family_id
                        and item.family.primary_email
                        else "—"
                    ),
                    (
                        item.family.primary_phone
                        if item.family_id
                        and item.family.primary_phone
                        else "—"
                    ),
                    item.emergency_contact_name or "—",
                    item.emergency_contact_phone or "—",
                ]
            }
            for item in students
        ]

        return {
            **entry,
            "columns": [
                "Student",
                "Family",
                "Email",
                "Phone",
                "Emergency Contact",
                "Emergency Phone",
            ],
            "rows": rows,
        }

    if report_key in {
        "family-zip-codes",
        "family-notes",
        "family-referrals",
        "classes-per-family",
    }:
        families = (
            Family.objects
            .filter(studio=studio)
            .order_by("family_name")
        )

        if report_key == "family-zip-codes":
            grouped = (
                families
                .exclude(postal_code="")
                .values(
                    "postal_code",
                    "city",
                    "state",
                )
                .annotate(
                    family_count=Count("id"),
                )
                .order_by(
                    "-family_count",
                    "postal_code",
                )
            )

            rows = [
                {
                    "cells": [
                        item["postal_code"],
                        item["city"] or "—",
                        item["state"] or "—",
                        str(item["family_count"]),
                    ]
                }
                for item in grouped
            ]

            return {
                **entry,
                "columns": [
                    "ZIP / Postal Code",
                    "City",
                    "State",
                    "Families",
                ],
                "rows": rows,
            }

        if report_key == "family-notes":
            rows = [
                {
                    "cells": [
                        str(item),
                        item.notes or "—",
                    ]
                }
                for item in families
                if item.notes
            ]

            return {
                **entry,
                "columns": [
                    "Family",
                    "Notes",
                ],
                "rows": rows,
            }

        if report_key == "family-referrals":
            # Family source is preferred. Student source is available
            # separately and can be used when family source is blank later.
            grouped = (
                families
                .values("how_did_you_hear_about_us")
                .annotate(
                    family_count=Count("id"),
                )
                .order_by("-family_count")
            )

            rows = [
                {
                    "cells": [
                        (
                            item["how_did_you_hear_about_us"]
                            or "Not Provided"
                        ),
                        str(item["family_count"]),
                    ]
                }
                for item in grouped
            ]

            return {
                **entry,
                "columns": [
                    "Referral Source",
                    "Families",
                ],
                "rows": rows,
            }

        family_rows = []

        for family in families:
            enrollment_qs = Enrollment.objects.filter(
                student__family=family,
                status=Enrollment.Status.ACTIVE,
            )

            if selected_season:
                enrollment_qs = enrollment_qs.filter(
                    class_instance__season=selected_season,
                )

            family_rows.append(
                {
                    "cells": [
                        str(family),
                        str(
                            family.students.filter(
                                is_active=True,
                            ).count()
                        ),
                        str(enrollment_qs.count()),
                        str(
                            enrollment_qs.values(
                                "class_instance_id"
                            ).distinct().count()
                        ),
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Family",
                "Active Students",
                "Enrollments",
                "Distinct Classes",
            ],
            "rows": family_rows,
        }

    if report_key in {
        "attendance-by-instructor",
        "attendance-by-day",
        "attendance-by-type",
    }:
        records = AttendanceRecord.objects.filter(
            student__studio=studio,
        )

        if selected_season:
            records = records.filter(
                session__class_instance__season=selected_season,
            )

        if report_key == "attendance-by-instructor":
            instructors = (
                Instructor.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "last_name",
                    "first_name",
                )
            )

            rows = []

            for instructor in instructors:
                subset = records.filter(
                    session__class_instance__instructor=instructor,
                )
                total = subset.count()
                rate = _attendance_rate_for_queryset(subset)

                rows.append(
                    {
                        "cells": [
                            instructor.full_name,
                            str(total),
                            (
                                f"{rate}%"
                                if rate is not None
                                else "—"
                            ),
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Instructor",
                    "Attendance Records",
                    "Attendance Rate",
                ],
                "rows": rows,
            }

        if report_key == "attendance-by-type":
            class_types = (
                Class.objects
                .filter(studio=studio)
                .values(
                    "class_type_id",
                    "class_type__name",
                )
                .distinct()
                .order_by("class_type__name")
            )

            rows = []

            for item in class_types:
                subset = records.filter(
                    session__class_instance__class_type_id=item[
                        "class_type_id"
                    ],
                )

                rate = _attendance_rate_for_queryset(subset)

                rows.append(
                    {
                        "cells": [
                            item["class_type__name"],
                            str(subset.count()),
                            (
                                f"{rate}%"
                                if rate is not None
                                else "—"
                            ),
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Class Type",
                    "Attendance Records",
                    "Attendance Rate",
                ],
                "rows": rows,
            }

        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        rows = []

        for day_number, day_name in enumerate(day_names):
            subset = records.filter(
                session__class_instance__meeting_times__day_of_week=day_number,
            ).distinct()

            rate = _attendance_rate_for_queryset(subset)

            rows.append(
                {
                    "cells": [
                        day_name,
                        str(subset.count()),
                        (
                            f"{rate}%"
                            if rate is not None
                            else "—"
                        ),
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Day",
                "Attendance Records",
                "Attendance Rate",
            ],
            "rows": rows,
        }

    if report_key == "consecutive-absences":
        records = (
            AttendanceRecord.objects
            .filter(
                student__studio=studio,
            )
            .select_related(
                "student",
                "session",
            )
            .order_by(
                "student_id",
                "session__session_date",
                "marked_at",
            )
        )

        if selected_season:
            records = records.filter(
                session__class_instance__season=selected_season,
            )

        by_student = {}

        for record in records:
            by_student.setdefault(
                record.student_id,
                {
                    "student": record.student,
                    "current": 0,
                    "max": 0,
                    "last_absence": None,
                },
            )

            bucket = by_student[record.student_id]

            if record.status == AttendanceRecord.Status.ABSENT:
                bucket["current"] += 1
                bucket["max"] = max(
                    bucket["max"],
                    bucket["current"],
                )
                bucket["last_absence"] = record.session.session_date
            else:
                bucket["current"] = 0

        rows = []

        for bucket in by_student.values():
            if bucket["max"] < 2:
                continue

            student = bucket["student"]

            rows.append(
                {
                    "cells": [
                        f"{student.first_name} {student.last_name}",
                        str(bucket["max"]),
                        (
                            bucket["last_absence"].strftime("%b %-d, %Y")
                            if bucket["last_absence"]
                            else "—"
                        ),
                    ]
                }
            )

        rows.sort(
            key=lambda row: (
                -int(row["cells"][1]),
                row["cells"][0],
            )
        )

        return {
            **entry,
            "columns": [
                "Student",
                "Longest Consecutive Absence Streak",
                "Most Recent Absence",
            ],
            "rows": rows,
        }

    if report_key == "paying-not-attending":
        active_enrollments = (
            Enrollment.objects
            .filter(
                class_instance__studio=studio,
                status=Enrollment.Status.ACTIVE,
            )
            .select_related(
                "student",
                "student__family",
                "class_instance",
            )
        )

        if selected_season:
            active_enrollments = active_enrollments.filter(
                class_instance__season=selected_season,
            )

        rows = []

        for enrollment in active_enrollments:
            attendance = AttendanceRecord.objects.filter(
                student=enrollment.student,
                session__class_instance=enrollment.class_instance,
            )

            total = attendance.count()

            if total < 2:
                continue

            rate = _attendance_rate_for_queryset(attendance)

            if rate is None or rate >= 60:
                continue

            open_tuition = Charge.objects.filter(
                account__studio=studio,
                enrollment=enrollment,
                charge_type=Charge.ChargeType.TUITION,
                status__in=[
                    Charge.Status.OPEN,
                    Charge.Status.PARTIALLY_PAID,
                    Charge.Status.PAID,
                ],
            ).exists()

            if not open_tuition:
                continue

            rows.append(
                {
                    "cells": [
                        f"{enrollment.student.first_name} {enrollment.student.last_name}",
                        enrollment.class_instance.name,
                        f"{rate}%",
                        str(total),
                        (
                            str(enrollment.student.family)
                            if enrollment.student.family_id
                            else "—"
                        ),
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Student",
                "Class",
                "Attendance Rate",
                "Attendance Records",
                "Family",
            ],
            "rows": rows,
        }

    if report_key in {
        "class-payments",
        "expected-vs-collected",
        "revenue-by-class",
        "revenue-by-season",
        "revenue-by-location",
    }:
        charges = Charge.objects.filter(
            account__studio=studio,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
                Charge.Status.PAID,
            ],
        )

        if report_key in {
            "class-payments",
            "expected-vs-collected",
            "revenue-by-class",
        }:
            classes = (
                Class.objects
                .filter(
                    studio=studio,
                )
                .order_by("name")
            )

            if selected_season:
                classes = classes.filter(
                    season=selected_season,
                )

            rows = []

            for item in classes:
                item_charges = charges.filter(
                    class_instance=item,
                )

                charged = (
                    item_charges.aggregate(
                        total=Sum("amount")
                    )["total"]
                    or 0
                )

                allocations = (
                    PaymentAllocation.objects
                    .filter(
                        charge__in=item_charges,
                        payment__status=Payment.Status.SUCCEEDED,
                    )
                    .aggregate(
                        total=Sum("amount")
                    )["total"]
                    or 0
                )

                balance = charged - allocations

                rows.append(
                    {
                        "cells": [
                            item.class_id,
                            item.name,
                            f"${charged:.2f}",
                            f"${allocations:.2f}",
                            f"${balance:.2f}",
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Class ID",
                    "Class",
                    "Charged",
                    "Collected",
                    "Unpaid",
                ],
                "rows": rows,
            }

        if report_key == "revenue-by-season":
            seasons = Season.objects.filter(
                studio=studio,
            ).order_by("-start_date")

            rows = []

            for season in seasons:
                season_charges = charges.filter(
                    class_instance__season=season,
                )

                charged = (
                    season_charges.aggregate(
                        total=Sum("amount")
                    )["total"]
                    or 0
                )

                collected = (
                    PaymentAllocation.objects
                    .filter(
                        charge__in=season_charges,
                        payment__status=Payment.Status.SUCCEEDED,
                    )
                    .aggregate(
                        total=Sum("amount")
                    )["total"]
                    or 0
                )

                rows.append(
                    {
                        "cells": [
                            season.name,
                            f"${charged:.2f}",
                            f"${collected:.2f}",
                            f"${(charged - collected):.2f}",
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Season",
                    "Charged",
                    "Collected",
                    "Unpaid",
                ],
                "rows": rows,
            }

        locations = (
            Class.objects
            .filter(
                studio=studio,
                default_location__isnull=False,
            )
            .values(
                "default_location_id",
                "default_location__name",
            )
            .distinct()
            .order_by("default_location__name")
        )

        rows = []

        for location in locations:
            location_charges = charges.filter(
                class_instance__default_location_id=location[
                    "default_location_id"
                ],
            )

            charged = (
                location_charges.aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
            )

            collected = (
                PaymentAllocation.objects
                .filter(
                    charge__in=location_charges,
                    payment__status=Payment.Status.SUCCEEDED,
                )
                .aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
            )

            rows.append(
                {
                    "cells": [
                        location["default_location__name"],
                        f"${charged:.2f}",
                        f"${collected:.2f}",
                        f"${(charged - collected):.2f}",
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Location",
                "Charged",
                "Collected",
                "Unpaid",
            ],
            "rows": rows,
        }

    if report_key == "payment-allocation":
        allocations = (
            PaymentAllocation.objects
            .filter(
                payment__account__studio=studio,
            )
            .select_related(
                "payment",
                "payment__account__family",
                "charge",
                "charge__student",
                "charge__class_instance",
            )
            .order_by("-created_at")
        )

        rows = [
            {
                "cells": [
                    str(item.payment.account.family),
                    item.payment.paid_at.strftime("%b %-d, %Y"),
                    f"${item.payment.amount:.2f}",
                    item.charge.description,
                    (
                        item.charge.class_instance.name
                        if item.charge.class_instance_id
                        else "—"
                    ),
                    f"${item.amount:.2f}",
                ]
            }
            for item in allocations
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Payment Date",
                "Payment Amount",
                "Charge",
                "Class",
                "Allocated",
            ],
            "rows": rows,
        }

    if report_key in {
        "registration-fees",
        "late-fees",
    }:
        charge_type = (
            Charge.ChargeType.REGISTRATION
            if report_key == "registration-fees"
            else Charge.ChargeType.LATE_FEE
        )

        charges = (
            Charge.objects
            .filter(
                account__studio=studio,
                charge_type=charge_type,
            )
            .select_related(
                "account__family",
                "student",
            )
            .order_by("-created_at")
        )

        rows = [
            {
                "cells": [
                    str(item.account.family),
                    (
                        f"{item.student.first_name} {item.student.last_name}"
                        if item.student_id
                        else "—"
                    ),
                    item.description,
                    f"${item.amount:.2f}",
                    f"${item.paid_amount:.2f}",
                    f"${item.balance_remaining:.2f}",
                    item.get_status_display(),
                ]
            }
            for item in charges
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Student",
                "Description",
                "Charged",
                "Paid",
                "Balance",
                "Status",
            ],
            "rows": rows,
        }

    if report_key == "credits-discounts":
        credits = (
            Credit.objects
            .filter(
                account__studio=studio,
                is_void=False,
            )
            .select_related(
                "account__family",
                "student",
            )
            .order_by("-created_at")
        )

        rows = [
            {
                "cells": [
                    str(item.account.family),
                    (
                        f"{item.student.first_name} {item.student.last_name}"
                        if item.student_id
                        else "—"
                    ),
                    item.get_credit_type_display(),
                    item.description,
                    f"${item.amount:.2f}",
                    f"${item.allocated_amount:.2f}",
                    f"${item.remaining_amount:.2f}",
                ]
            }
            for item in credits
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Student",
                "Type",
                "Description",
                "Credit",
                "Allocated",
                "Remaining",
            ],
            "rows": rows,
        }

    if report_key == "payment-plans":
        schedules = (
            RecurringChargeSchedule.objects
            .filter(
                account__studio=studio,
            )
            .select_related(
                "account__family",
                "student",
                "class_instance",
                "tuition_plan",
            )
            .order_by(
                "-is_active",
                "next_charge_date",
            )
        )

        rows = [
            {
                "cells": [
                    str(item.account.family),
                    (
                        f"{item.student.first_name} {item.student.last_name}"
                        if item.student_id
                        else "—"
                    ),
                    (
                        item.class_instance.name
                        if item.class_instance_id
                        else "—"
                    ),
                    item.tuition_plan.name,
                    item.tuition_plan.get_frequency_display(),
                    f"${item.amount:.2f}",
                    (
                        item.next_charge_date.strftime("%b %-d, %Y")
                        if item.next_charge_date
                        else "—"
                    ),
                    "Active" if item.is_active else "Inactive",
                ]
            }
            for item in schedules
        ]

        return {
            **entry,
            "columns": [
                "Family",
                "Student",
                "Class",
                "Billing Policy",
                "Frequency",
                "Amount",
                "Next Charge",
                "Status",
            ],
            "rows": rows,
        }

    if report_key in {
        "season-charges-trend",
        "revenue-trends",
    }:
        charges = Charge.objects.filter(
            account__studio=studio,
        )

        if selected_season:
            charges = charges.filter(
                class_instance__season=selected_season,
            )

        trend = (
            charges
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                charged=Sum("amount"),
            )
            .order_by("month")
        )

        rows = [
            {
                "cells": [
                    item["month"].strftime("%b %Y"),
                    f"${(item['charged'] or 0):.2f}",
                ]
            }
            for item in trend
        ]

        return {
            **entry,
            "columns": [
                "Month",
                "Charges Created",
            ],
            "rows": rows,
        }

    if report_key in {
        "instructor-class-attendance",
        "instructor-work-schedules",
        "teaching-hours",
    }:
        instructors = (
            Instructor.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .order_by(
                "last_name",
                "first_name",
            )
        )

        rows = []

        for instructor in instructors:
            class_qs = Class.objects.filter(
                studio=studio,
                is_active=True,
            ).filter(
                Q(instructor=instructor)
                | Q(assistant_instructor=instructor)
            ).distinct()

            if selected_season:
                class_qs = class_qs.filter(
                    season=selected_season,
                )

            meetings = ClassMeeting.objects.filter(
                class_instance__in=class_qs,
                is_active=True,
            )

            weekly_minutes = (
                meetings.aggregate(
                    total=Sum("duration_minutes")
                )["total"]
                or 0
            )

            attendance = AttendanceRecord.objects.filter(
                session__class_instance__in=class_qs,
            )

            rate = _attendance_rate_for_queryset(attendance)

            if report_key == "instructor-class-attendance":
                cells = [
                    instructor.full_name,
                    str(class_qs.count()),
                    str(attendance.count()),
                    (
                        f"{rate}%"
                        if rate is not None
                        else "—"
                    ),
                ]
            elif report_key == "teaching-hours":
                cells = [
                    instructor.full_name,
                    str(class_qs.count()),
                    f"{weekly_minutes / 60:.2f}",
                ]
            else:
                schedule_text = "; ".join(
                    (
                        f"{meeting.get_day_of_week_display()} "
                        f"{meeting.start_time.strftime('%-I:%M %p')} "
                        f"— {meeting.class_instance.name}"
                    )
                    for meeting in meetings.select_related(
                        "class_instance"
                    ).order_by(
                        "day_of_week",
                        "start_time",
                    )
                )

                cells = [
                    instructor.full_name,
                    str(class_qs.count()),
                    schedule_text or "No active meetings",
                ]

            rows.append({"cells": cells})

        columns = {
            "instructor-class-attendance": [
                "Instructor",
                "Classes",
                "Attendance Records",
                "Attendance Rate",
            ],
            "teaching-hours": [
                "Instructor",
                "Classes",
                "Scheduled Hours / Week",
            ],
            "instructor-work-schedules": [
                "Instructor",
                "Classes",
                "Weekly Schedule",
            ],
        }[report_key]

        return {
            **entry,
            "columns": columns,
            "rows": rows,
        }

    if report_key in {
        "evaluation-completion",
        "missing-evaluations",
        "evaluation-status",
        "overdue-evaluations",
    }:
        active_enrollments = Enrollment.objects.filter(
            class_instance__studio=studio,
            status=Enrollment.Status.ACTIVE,
        ).select_related(
            "student",
            "class_instance",
            "class_instance__instructor",
        )

        if selected_season:
            active_enrollments = active_enrollments.filter(
                class_instance__season=selected_season,
            )

        if report_key in {
            "evaluation-completion",
            "missing-evaluations",
            "overdue-evaluations",
        }:
            rows = []

            for enrollment in active_enrollments:
                evaluations = StudentEvaluation.objects.filter(
                    studio=studio,
                    student=enrollment.student,
                    class_instance=enrollment.class_instance,
                )

                published = evaluations.filter(
                    status=StudentEvaluation.Status.PUBLISHED,
                ).exists()

                if report_key in {
                    "missing-evaluations",
                    "overdue-evaluations",
                } and published:
                    continue

                rows.append(
                    {
                        "cells": [
                            f"{enrollment.student.first_name} {enrollment.student.last_name}",
                            enrollment.class_instance.name,
                            enrollment.class_instance.instructor.full_name,
                            (
                                "Published"
                                if published
                                else (
                                    "Draft"
                                    if evaluations.exists()
                                    else "Missing"
                                )
                            ),
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Student",
                    "Class",
                    "Instructor",
                    "Evaluation Status",
                ],
                "rows": rows,
            }

        evaluations = (
            StudentEvaluation.objects
            .filter(
                studio=studio,
            )
            .select_related(
                "student",
                "class_instance",
                "instructor",
                "template",
            )
            .order_by("-evaluation_date")
        )

        if selected_season:
            evaluations = evaluations.filter(
                class_instance__season=selected_season,
            )

        rows = [
            {
                "cells": [
                    item.evaluation_date.strftime("%b %-d, %Y"),
                    f"{item.student.first_name} {item.student.last_name}",
                    item.class_instance.name,
                    item.instructor.full_name,
                    item.template.name,
                    item.get_status_display(),
                ]
            }
            for item in evaluations
        ]

        return {
            **entry,
            "columns": [
                "Date",
                "Student",
                "Class",
                "Instructor",
                "Template",
                "Status",
            ],
            "rows": rows,
        }

    if report_key == "criterion-averages":
        ratings = (
            EvaluationRating.objects
            .filter(
                evaluation__studio=studio,
            )
            .select_related(
                "criterion",
                "criterion__template",
            )
        )

        if selected_season:
            ratings = ratings.filter(
                evaluation__class_instance__season=selected_season,
            )

        grouped = {}

        for item in ratings:
            key = (
                item.criterion_id,
                item.criterion.name,
                item.criterion.template.name,
            )

            bucket = grouped.setdefault(
                key,
                {
                    "values": [],
                    "labels": {},
                },
            )

            try:
                numeric = float(item.rating)
                bucket["values"].append(numeric)
            except (TypeError, ValueError):
                label = item.rating or "Blank"
                bucket["labels"][label] = (
                    bucket["labels"].get(label, 0)
                    + 1
                )

        rows = []

        for (
            criterion_id,
            criterion_name,
            template_name,
        ), bucket in grouped.items():
            if bucket["values"]:
                summary = (
                    f"{sum(bucket['values']) / len(bucket['values']):.2f}"
                )
            else:
                summary = ", ".join(
                    (
                        f"{label}: {count}"
                        for label, count
                        in sorted(bucket["labels"].items())
                    )
                ) or "—"

            rows.append(
                {
                    "cells": [
                        template_name,
                        criterion_name,
                        summary,
                        str(
                            len(bucket["values"])
                            + sum(bucket["labels"].values())
                        ),
                    ]
                }
            )

        rows.sort(
            key=lambda row: (
                row["cells"][0],
                row["cells"][1],
            )
        )

        return {
            **entry,
            "columns": [
                "Template",
                "Criterion",
                "Average / Distribution",
                "Ratings",
            ],
            "rows": rows,
        }

    if report_key == "student-progress":
        evaluations = (
            StudentEvaluation.objects
            .filter(
                studio=studio,
                status=StudentEvaluation.Status.PUBLISHED,
            )
            .select_related(
                "student",
                "class_instance",
            )
            .order_by(
                "student__last_name",
                "student__first_name",
                "evaluation_date",
            )
        )

        if selected_season:
            evaluations = evaluations.filter(
                class_instance__season=selected_season,
            )

        grouped = {}

        for item in evaluations:
            grouped.setdefault(
                item.student_id,
                {
                    "student": item.student,
                    "evaluations": [],
                },
            )["evaluations"].append(item)

        rows = []

        for bucket in grouped.values():
            evals = bucket["evaluations"]

            if not evals:
                continue

            rows.append(
                {
                    "cells": [
                        f"{bucket['student'].first_name} {bucket['student'].last_name}",
                        str(len(evals)),
                        evals[0].evaluation_date.strftime("%b %-d, %Y"),
                        evals[-1].evaluation_date.strftime("%b %-d, %Y"),
                        evals[-1].class_instance.name,
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Student",
                "Published Evaluations",
                "First Evaluation",
                "Latest Evaluation",
                "Latest Class",
            ],
            "rows": rows,
        }

    if report_key == "enrollment-trends":
        enrollments = Enrollment.objects.filter(
            class_instance__studio=studio,
        )

        if selected_season:
            enrollments = enrollments.filter(
                class_instance__season=selected_season,
            )

        trend = (
            enrollments
            .annotate(month=TruncMonth("enrolled_at"))
            .values("month")
            .annotate(
                enrollments=Count("id"),
            )
            .order_by("month")
        )

        rows = [
            {
                "cells": [
                    item["month"].strftime("%b %Y"),
                    str(item["enrollments"]),
                ]
            }
            for item in trend
        ]

        return {
            **entry,
            "columns": [
                "Month",
                "Enrollments Created",
            ],
            "rows": rows,
        }

    if report_key == "class-opportunities":
        classes = (
            Class.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .annotate(
                active_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.ACTIVE,
                    ),
                    distinct=True,
                ),
                waitlist_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.WAITLISTED,
                    ),
                    distinct=True,
                ),
            )
            .order_by("name")
        )

        if selected_season:
            classes = classes.filter(
                season=selected_season,
            )

        rows = []

        for item in classes:
            percent = (
                round(item.active_count / item.capacity * 100)
                if item.capacity
                else 0
            )

            if item.waitlist_count > 0:
                opportunity = "Demand / Add Section"
            elif percent >= 90:
                opportunity = "Near Capacity"
            elif percent <= 35:
                opportunity = "Low Enrollment"
            else:
                continue

            rows.append(
                {
                    "cells": [
                        item.class_id,
                        item.name,
                        f"{item.active_count}/{item.capacity}",
                        str(item.waitlist_count),
                        f"{percent}%",
                        opportunity,
                    ]
                }
            )

        return {
            **entry,
            "columns": [
                "Class ID",
                "Class",
                "Enrollment",
                "Waitlist",
                "Utilization",
                "Opportunity",
            ],
            "rows": rows,
        }

    if report_key in {
        "needs-attention",
        "business-insights",
    }:
        classes = (
            Class.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .annotate(
                active_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.ACTIVE,
                    ),
                    distinct=True,
                ),
                waitlist_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=Enrollment.Status.WAITLISTED,
                    ),
                    distinct=True,
                ),
            )
        )

        if selected_season:
            classes = classes.filter(
                season=selected_season,
            )

        if report_key == "needs-attention":
            rows = []

            missing_tuition = classes.filter(
                tuition_amount__isnull=True,
            ).count()

            missing_policy = classes.filter(
                tuition_plan__isnull=True,
            ).count()

            waitlisted = classes.filter(
                waitlist_count__gt=0,
            ).count()

            low_classes = sum(
                1
                for item in classes
                if item.capacity
                and (
                    item.active_count / item.capacity
                    <= 0.35
                )
            )

            overdue = Charge.objects.filter(
                account__studio=studio,
                status__in=[
                    Charge.Status.OPEN,
                    Charge.Status.PARTIALLY_PAID,
                ],
                due_date__lt=__import__(
                    "django.utils.timezone",
                    fromlist=["localdate"],
                ).localdate(),
            ).count()

            repeated = (
                AttendanceRecord.objects
                .filter(
                    student__studio=studio,
                    status=AttendanceRecord.Status.ABSENT,
                )
                .values("student_id")
                .annotate(absences=Count("id"))
                .filter(absences__gte=2)
                .count()
            )

            for label, count, note in [
                (
                    "Classes missing tuition",
                    missing_tuition,
                    "Set tuition on the class before billing.",
                ),
                (
                    "Classes missing billing policy",
                    missing_policy,
                    "Assign a billing policy to control frequency and fees.",
                ),
                (
                    "Classes with waitlists",
                    waitlisted,
                    "Consider an additional section where demand is strong.",
                ),
                (
                    "Classes at or below 35% capacity",
                    low_classes,
                    "Review low-enrollment classes.",
                ),
                (
                    "Past-due charges",
                    overdue,
                    "Review outstanding family balances.",
                ),
                (
                    "Students with 2+ absences",
                    repeated,
                    "Attendance follow-up may be useful.",
                ),
            ]:
                rows.append(
                    {
                        "cells": [
                            label,
                            str(count),
                            note,
                        ]
                    }
                )

            return {
                **entry,
                "columns": [
                    "Attention Area",
                    "Count",
                    "Why It Matters",
                ],
                "rows": rows,
            }

        active_enrollments = Enrollment.objects.filter(
            class_instance__studio=studio,
            status=Enrollment.Status.ACTIVE,
        )

        if selected_season:
            active_enrollments = active_enrollments.filter(
                class_instance__season=selected_season,
            )

        charges = Charge.objects.filter(
            account__studio=studio,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
                Charge.Status.PAID,
            ],
        )

        charged = (
            charges.aggregate(total=Sum("amount"))["total"]
            or 0
        )

        collected = (
            PaymentAllocation.objects
            .filter(
                charge__in=charges,
                payment__status=Payment.Status.SUCCEEDED,
            )
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        average_utilization_values = []

        for item in classes:
            if item.capacity:
                average_utilization_values.append(
                    item.active_count
                    / item.capacity
                    * 100
                )

        avg_utilization = (
            round(
                sum(average_utilization_values)
                / len(average_utilization_values)
            )
            if average_utilization_values
            else 0
        )

        rows = [
            {
                "cells": [
                    "Active enrollments",
                    str(active_enrollments.count()),
                    "Current selected-season participation",
                ]
            },
            {
                "cells": [
                    "Average class utilization",
                    f"{avg_utilization}%",
                    "Average filled capacity across active classes",
                ]
            },
            {
                "cells": [
                    "Charges created",
                    f"${charged:.2f}",
                    "Current studio billing data",
                ]
            },
            {
                "cells": [
                    "Payments allocated",
                    f"${collected:.2f}",
                    "Succeeded payments applied to charges",
                ]
            },
            {
                "cells": [
                    "Uncollected balance",
                    f"${(charged - collected):.2f}",
                    "Charges not yet covered by succeeded payments",
                ]
            },
        ]

        return {
            **entry,
            "columns": [
                "Metric",
                "Value",
                "Interpretation",
            ],
            "rows": rows,
        }

    return None


@login_required
def reports_dashboard(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(
        request,
        studio,
    ) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    season_id = request.GET.get(
        "season",
        "",
    ).strip()

    seasons = Season.objects.filter(
        studio=studio,
    ).order_by(
        "-start_date",
        "name",
    )

    selected_season = None

    if season_id:
        selected_season = seasons.filter(
            pk=season_id,
        ).first()

    if selected_season is None:
        selected_season = seasons.filter(
            is_active=True,
        ).first() or seasons.first()

    classes = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "season",
            "class_type",
            "instructor",
        )
        .annotate(
            active_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            ),
            waitlist_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.WAITLISTED,
                ),
                distinct=True,
            ),
        )
        .order_by("name")
    )

    if selected_season:
        classes = classes.filter(
            season=selected_season,
        )

    class_rows = []

    for class_instance in classes:
        percent_full = 0

        if class_instance.capacity:
            percent_full = round(
                (
                    class_instance.active_count
                    / class_instance.capacity
                )
                * 100
            )

        attendance_records = AttendanceRecord.objects.filter(
            session__class_instance=class_instance,
        )

        class_rows.append(
            {
                "class": class_instance,
                "active_count": class_instance.active_count,
                "waitlist_count": class_instance.waitlist_count,
                "available": max(
                    class_instance.capacity
                    - class_instance.active_count,
                    0,
                ),
                "percent_full": percent_full,
                "attendance_rate": _attendance_rate_for_queryset(
                    attendance_records
                ),
            }
        )

    active_students = Student.objects.filter(
        studio=studio,
        is_active=True,
    )

    active_enrollments = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.ACTIVE,
    )

    if selected_season:
        active_enrollments = active_enrollments.filter(
            class_instance__season=selected_season,
        )

    enrolled_student_ids = (
        active_enrollments
        .values_list(
            "student_id",
            flat=True,
        )
        .distinct()
    )

    season_student_count = (
        Student.objects
        .filter(
            studio=studio,
            id__in=enrolled_student_ids,
        )
        .count()
    )

    attendance_records = AttendanceRecord.objects.filter(
        student__studio=studio,
    )

    if selected_season:
        attendance_records = attendance_records.filter(
            session__class_instance__season=selected_season,
        )

    attendance_rate = _attendance_rate_for_queryset(
        attendance_records
    )

    absence_counts = (
        AttendanceRecord.objects
        .filter(
            student__studio=studio,
            status=AttendanceRecord.Status.ABSENT,
        )
    )

    if selected_season:
        absence_counts = absence_counts.filter(
            session__class_instance__season=selected_season,
        )

    repeated_absences = (
        absence_counts
        .values(
            "student_id",
            "student__first_name",
            "student__last_name",
        )
        .annotate(
            absence_count=Count("id")
        )
        .filter(
            absence_count__gte=2,
        )
        .order_by(
            "-absence_count",
            "student__last_name",
            "student__first_name",
        )[:12]
    )

    top_classes = sorted(
        class_rows,
        key=lambda row: (
            -row["percent_full"],
            row["class"].name,
        ),
    )[:8]

    return render(
        request,
        "reports/reports_dashboard.html",
        {
            "studio": studio,
            "role": "administrator",
            "seasons": seasons,
            "selected_season": selected_season,
            "class_rows": class_rows,
            "top_classes": top_classes,
            "repeated_absences": repeated_absences,
            "active_student_count": active_students.count(),
            "season_student_count": season_student_count,
            "active_enrollment_count": active_enrollments.count(),
            "family_count": Family.objects.filter(
                studio=studio,
                is_active=True,
            ).count(),
            "instructor_count": Instructor.objects.filter(
                studio=studio,
                is_active=True,
            ).count(),
            "attendance_rate": attendance_rate,
            "report_catalog": _report_catalog(),
            "report_catalog_count": sum(
                len(category["reports"])
                for category in REPORT_CATALOG
            ),
            "live_report_count": sum(
                1
                for category in REPORT_CATALOG
                for report in category["reports"]
                if report[3] in {"live", "dashboard"}
            ),
            "attention_counts": {
                "repeated_absences": repeated_absences.count(),
                "full_classes": sum(
                    1
                    for row in class_rows
                    if row["percent_full"] >= 100
                ),
                "waitlisted_classes": sum(
                    1
                    for row in class_rows
                    if row["waitlist_count"] > 0
                ),
                "missing_tuition": sum(
                    1
                    for row in class_rows
                    if row["class"].tuition_amount is None
                ),
            },
        },
    )


@login_required
def report_detail(
    request,
    studio_slug,
    report_key,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(
        request,
        studio,
    ) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    entry = _report_entry(report_key)

    if entry is None:
        return render(
            request,
            "reports/report_unavailable.html",
            {
                "studio": studio,
                "role": "administrator",
                "report_title": "Report Not Found",
                "report_description": (
                    "This report is not in the Encore report catalog."
                ),
            },
            status=404,
        )

    if entry["status"] == "dashboard":
        from django.shortcuts import redirect

        return redirect(
            "reports:reports_dashboard",
            studio_slug=studio.slug,
        )

    seasons, selected_season = (
        _selected_season_for_request(
            request,
            studio,
        )
    )

    payload = _report_payload(
        report_key,
        studio=studio,
        selected_season=selected_season,
    )

    if payload is None:
        return render(
            request,
            "reports/report_unavailable.html",
            {
                "studio": studio,
                "role": "administrator",
                "report_title": entry["title"],
                "report_description": entry["description"],
                "report_category": entry["category"],
            },
        )

    return render(
        request,
        "reports/report_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "report": payload,
            "seasons": seasons,
            "selected_season": selected_season,
            "report_key": report_key,
        },
    )


@login_required
def report_csv(
    request,
    studio_slug,
    report_key,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(
        request,
        studio,
    ) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    seasons, selected_season = (
        _selected_season_for_request(
            request,
            studio,
        )
    )

    payload = _report_payload(
        report_key,
        studio=studio,
        selected_season=selected_season,
    )

    if payload is None:
        return HttpResponse(
            "This report is not available for CSV export yet.",
            status=404,
            content_type="text/plain",
        )

    response = HttpResponse(
        content_type="text/csv",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{studio.slug}-{report_key}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(payload["columns"])

    for row in payload["rows"]:
        writer.writerow(row["cells"])

    return response


@login_required
def class_roster_csv(
    request,
    studio_slug,
    class_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(
        request,
        studio,
    ) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    class_instance = get_object_or_404(
        Class.objects.select_related(
            "season",
            "instructor",
        ),
        pk=class_id,
        studio=studio,
    )

    enrollments = (
        Enrollment.objects
        .filter(
            class_instance=class_instance,
            status=Enrollment.Status.ACTIVE,
        )
        .select_related(
            "student",
            "student__family",
        )
        .order_by(
            "student__last_name",
            "student__first_name",
        )
    )

    safe_class_id = (
        class_instance.class_id
        .replace("/", "-")
        .replace(" ", "-")
    )

    response = HttpResponse(
        content_type="text/csv",
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="{safe_class_id}-roster.csv"'
    )

    writer = csv.writer(response)

    writer.writerow(
        [
            "Class ID",
            "Class Name",
            "Season",
            "Student First Name",
            "Student Last Name",
            "Age",
            "Family",
            "Enrollment Status",
            "Enrollment Source",
        ]
    )

    for enrollment in enrollments:
        student = enrollment.student

        writer.writerow(
            [
                class_instance.class_id,
                class_instance.name,
                class_instance.season.name,
                student.first_name,
                student.last_name,
                student.age,
                (
                    str(student.family)
                    if student.family
                    else ""
                ),
                enrollment.get_status_display(),
                enrollment.get_source_display(),
            ]
        )

    return response


@login_required
def all_students_csv(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(
        request,
        studio,
    ) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    students = (
        Student.objects
        .filter(studio=studio)
        .select_related("family")
        .annotate(
            active_class_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
        .order_by(
            "last_name",
            "first_name",
        )
    )

    response = HttpResponse(
        content_type="text/csv",
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="{studio.slug}-students.csv"'
    )

    writer = csv.writer(response)

    writer.writerow(
        [
            "First Name",
            "Last Name",
            "Birthday",
            "Age",
            "Family",
            "Active",
            "Enrollment Blocked",
            "Active Class Count",
        ]
    )

    for student in students:
        writer.writerow(
            [
                student.first_name,
                student.last_name,
                student.birthday,
                student.age,
                str(student.family) if student.family else "",
                "Yes" if student.is_active else "No",
                "Yes" if student.enrollment_blocked else "No",
                student.active_class_count,
            ]
        )

    return response
