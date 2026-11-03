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
        "<slug:studio_slug>/class/<int:class_id>/measurements/<int:student_id>/cancel/",
        views.measurement_cancel,
        name="measurement_cancel",
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
        "<slug:studio_slug>/class/<int:class_id>/<int:costume_id>/edit/",
        views.costume_edit,
        name="costume_edit",
    ),
    path(
        "<slug:studio_slug>/class/<int:class_id>/<int:costume_id>/assignment/<int:assignment_id>/save/",
        views.costume_assignment_update,
        name="costume_assignment_update",
    ),

    path("<slug:studio_slug>/vendors/", views.vendor_list, name="vendor_list"),
    path("<slug:studio_slug>/vendors/add/", views.vendor_create, name="vendor_create"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/", views.vendor_detail, name="vendor_detail"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/edit/", views.vendor_edit, name="vendor_edit"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/delete/", views.vendor_delete, name="vendor_delete"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/charts/add/", views.vendor_chart_create, name="vendor_chart_create"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/charts/<int:chart_id>/edit/", views.vendor_chart_edit, name="vendor_chart_edit"),
    path("<slug:studio_slug>/vendors/<int:vendor_id>/charts/<int:chart_id>/delete/", views.vendor_chart_delete, name="vendor_chart_delete"),

    path(
        "<slug:studio_slug>/my/",
        views.my_costumes,
        name="my_costumes",
    ),
]
