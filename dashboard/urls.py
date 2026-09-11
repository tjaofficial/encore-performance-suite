from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path(
        "<slug:studio_slug>/admin/",
        views.admin_dashboard,
        name="admin_dashboard",
    ),
    path(
        "<slug:studio_slug>/teacher/",
        views.teacher_dashboard,
        name="teacher_dashboard",
    ),
    path(
        "<slug:studio_slug>/family/",
        views.family_dashboard,
        name="family_dashboard",
    ),
    path(
        "<slug:studio_slug>/student/",
        views.student_dashboard,
        name="student_dashboard",
    ),
]
