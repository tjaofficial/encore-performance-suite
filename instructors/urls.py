from django.urls import path

from . import payroll_views, views

app_name = "instructors"

urlpatterns = [
    path(
        "claim/<uuid:activation_token>/",
        views.instructor_claim_profile,
        name="instructor_claim_profile",
    ),
    path(
        "claim/<uuid:activation_token>/availability/",
        views.instructor_claim_availability,
        name="instructor_claim_availability",
    ),
    path(
        "<slug:studio_slug>/my-hours-pay/",
        payroll_views.teacher_hours_pay,
        name="teacher_hours_pay",
    ),
    path(
        "<slug:studio_slug>/my-hours-pay/export/",
        payroll_views.teacher_hours_pay_export,
        name="teacher_hours_pay_export",
    ),
    path(
        "<slug:studio_slug>/payroll/unlock/",
        payroll_views.payroll_unlock,
        name="payroll_unlock",
    ),
    path(
        "<slug:studio_slug>/payroll/lock/",
        payroll_views.payroll_lock,
        name="payroll_lock",
    ),
    path(
        "<slug:studio_slug>/payroll/",
        payroll_views.payroll_management,
        name="payroll_management",
    ),
    path(
        "<slug:studio_slug>/payroll/staff/<int:instructor_id>/",
        payroll_views.payroll_compensation,
        name="payroll_compensation",
    ),
    path(
        "<slug:studio_slug>/payroll/staff/<int:instructor_id>/<int:compensation_id>/edit/",
        payroll_views.payroll_compensation,
        name="payroll_compensation_edit",
    ),
    path(
        "<slug:studio_slug>/",
        views.instructor_list,
        name="instructor_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.instructor_create,
        name="instructor_create",
    ),
    path(
        "<slug:studio_slug>/<int:instructor_id>/time-off/<int:request_id>/decision/",
        views.instructor_time_off_decision,
        name="instructor_time_off_decision",
    ),
    path(
        "<slug:studio_slug>/<int:instructor_id>/",
        views.instructor_detail,
        name="instructor_detail",
    ),
    path(
        "<slug:studio_slug>/<int:instructor_id>/edit/",
        views.instructor_edit,
        name="instructor_edit",
    ),
]
