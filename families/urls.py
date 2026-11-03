from django.urls import path

from . import views

app_name = "families"

urlpatterns = [
    path(
        "<slug:studio_slug>/portal/",
        views.parent_family_detail,
        name="parent_family_detail",
    ),
    path(
        "<slug:studio_slug>/portal/edit/",
        views.parent_family_edit,
        name="parent_family_edit",
    ),
    path(
        "<slug:studio_slug>/portal/guardians/add/",
        views.parent_guardian_add,
        name="parent_guardian_add",
    ),
    path(
        "<slug:studio_slug>/portal/guardians/invite/",
        views.parent_guardian_invite,
        name="parent_guardian_invite",
    ),
    path(
        "<slug:studio_slug>/",
        views.family_list,
        name="family_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.family_create,
        name="family_create",
    ),
    path(
        "<slug:studio_slug>/<int:family_id>/",
        views.family_detail,
        name="family_detail",
    ),
    path(
        "<slug:studio_slug>/<int:family_id>/edit/",
        views.family_edit,
        name="family_edit",
    ),
]
