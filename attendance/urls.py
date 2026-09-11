from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path(
        "<slug:studio_slug>/class/<int:class_id>/",
        views.take_attendance,
        name="take_attendance",
    ),
    path(
        "<slug:studio_slug>/session/<int:session_id>/save/",
        views.update_attendance,
        name="update_attendance",
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
