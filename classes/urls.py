from django.urls import path

from . import views

app_name = "classes"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.class_list,
        name="class_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.class_create,
        name="class_create",
    ),
    path(
        "<slug:studio_slug>/<int:class_id>/",
        views.class_detail,
        name="class_detail",
    ),
    path(
        "<slug:studio_slug>/<int:class_id>/students/<int:student_id>/",
        views.class_student_detail,
        name="class_student_detail",
    ),
    path(
        "<slug:studio_slug>/<int:class_id>/edit/",
        views.class_edit,
        name="class_edit",
    ),
]
