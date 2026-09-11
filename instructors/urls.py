from django.urls import path

from . import views

app_name = "instructors"

urlpatterns = [
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
