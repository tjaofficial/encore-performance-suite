from django.urls import path

from . import views

app_name = "resources"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.resource_list,
        name="resource_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.resource_create,
        name="resource_create",
    ),
    path(
        "<slug:studio_slug>/<int:resource_id>/edit/",
        views.resource_edit,
        name="resource_edit",
    ),
]
