from django.urls import path

from . import views

app_name = "costumes"

urlpatterns = [
    path(
        "<slug:studio_slug>/class/<int:class_id>/measurements/",
        views.measurement_roster,
        name="measurement_roster",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/measurements/<int:student_id>/save/",
        views.measurement_autosave,
        name="measurement_autosave",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/measurements/<int:student_id>/complete/",
        views.measurement_complete,
        name="measurement_complete",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/measurements/<int:student_id>/new/",
        views.measurement_start_new,
        name="measurement_start_new",
    ),

    path(
        "<slug:studio_slug>/class/<int:class_id>/",
        views.costume_list,
        name="costume_list",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/add/",
        views.costume_create,
        name="costume_create",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/<int:costume_id>/",
        views.costume_detail,
        name="costume_detail",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/<int:costume_id>/assignment/<int:assignment_id>/save/",
        views.costume_assignment_update,
        name="costume_assignment_update",
    ),

    path(
        "<slug:studio_slug>/my/",
        views.my_costumes,
        name="my_costumes",
    ),
]
