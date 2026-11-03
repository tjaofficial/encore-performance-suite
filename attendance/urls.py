from django.urls import path

from . import views, phase2_views

app_name = "attendance"

urlpatterns = [
    path("<slug:studio_slug>/family/overview/", phase2_views.family_attendance, name="family_attendance"),
    path("<slug:studio_slug>/makeups/", phase2_views.makeup_schedule, name="makeup_schedule"),
    path("<slug:studio_slug>/makeups/book/", phase2_views.book_makeup, name="book_makeup"),
    path("<slug:studio_slug>/absence/request/", phase2_views.absence_request_create, name="absence_request_create"),
    path("<slug:studio_slug>/absence/request/<int:request_id>/review/", phase2_views.review_absence_request, name="review_absence_request"),
    path("<slug:studio_slug>/settings/", views.attendance_settings, name="settings"),
    path("<slug:studio_slug>/makeup/available/", views.available_makeup_dates, name="available_makeup_dates"),

    path(
        "<slug:studio_slug>/class/<int:class_id>/",
        views.take_attendance,
        name="take_attendance",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/overview/",
        views.attendance_submission_detail,
        name="submission_detail",
    ),
    path(
        "<slug:studio_slug>/student/<int:student_id>/absences/",
        views.student_absence_detail,
        name="student_absence_detail",
    ),
    path(
        "<slug:studio_slug>/session/<int:session_id>/save/",
        views.update_attendance,
        name="update_attendance",
    ),
    path(
        "<slug:studio_slug>/manager/",
        views.attendance_manager,
        name="manager",
    ),
    path(
        "<slug:studio_slug>/session/<int:session_id>/makeup/search/",
        views.search_makeup_students,
        name="search_makeup_students",
    ),
    path(
        "<slug:studio_slug>/session/<int:session_id>/makeup/add/",
        views.add_makeup_student,
        name="add_makeup_student",
    ),
    path(
        "<slug:studio_slug>/student/history/",
        views.student_attendance_history,
        name="student_history",
    ),
    path(
        "<slug:studio_slug>/family/student/<int:student_id>/history/",
        views.family_student_attendance_history,
        name="family_student_history",
    ),
]
