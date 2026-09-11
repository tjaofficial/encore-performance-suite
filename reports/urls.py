from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.reports_dashboard,
        name="reports_dashboard",
    ),
    path(
        "<slug:studio_slug>/report/<slug:report_key>/",
        views.report_detail,
        name="report_detail",
    ),
    path(
        "<slug:studio_slug>/report/<slug:report_key>.csv",
        views.report_csv,
        name="report_csv",
    ),
    path(
        "<slug:studio_slug>/students.csv",
        views.all_students_csv,
        name="all_students_csv",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/roster.csv",
        views.class_roster_csv,
        name="class_roster_csv",
    ),
]
