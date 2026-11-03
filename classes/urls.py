from django.urls import path

from . import views

app_name = "classes"

urlpatterns = [
    path("<slug:studio_slug>/approval-codes/", views.approval_codes_overview, name="approval_codes_overview"),
    path(
        "<slug:studio_slug>/settings/list/",
        views.class_list_settings,
        name="class_list_settings",
    ),
    path(
        "<slug:studio_slug>/bulk-edit/",
        views.class_bulk_edit,
        name="class_bulk_edit",
    ),
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
    path("<slug:studio_slug>/<int:class_id>/students/<int:student_id>/notes/", views.class_student_notes_save, name="class_student_notes_save"),
    path("<slug:studio_slug>/<int:class_id>/approval-codes/", views.class_approval_codes, name="class_approval_codes"),
    path(
        "<slug:studio_slug>/<int:class_id>/edit/",
        views.class_edit,
        name="class_edit",
    ),
]
