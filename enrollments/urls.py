from django.urls import path

from . import views

app_name = "enrollments"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.enrollment_list,
        name="enrollment_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.enrollment_create,
        name="enrollment_create",
    ),
    path(
        "<slug:studio_slug>/<int:enrollment_id>/",
        views.enrollment_detail,
        name="enrollment_detail",
    ),
    path(
        "<slug:studio_slug>/<int:enrollment_id>/edit/",
        views.enrollment_edit,
        name="enrollment_edit",
    ),
]
