from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.student_list,
        name="student_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.student_create,
        name="student_create",
    ),
    path(
        "<slug:studio_slug>/<int:student_id>/",
        views.student_detail,
        name="student_detail",
    ),
    path(
        "<slug:studio_slug>/<int:student_id>/edit/",
        views.student_edit,
        name="student_edit",
    ),
]
