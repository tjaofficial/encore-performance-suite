from django.urls import path

from . import views

app_name = "families"

urlpatterns = [
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
