from django.urls import path

from . import views

app_name = "evaluations"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.evaluation_list,
        name="evaluation_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.evaluation_create,
        name="evaluation_create",
    ),
    path(
        "<slug:studio_slug>/<int:evaluation_id>/",
        views.evaluation_detail,
        name="evaluation_detail",
    ),
    path(
        "<slug:studio_slug>/<int:evaluation_id>/edit/",
        views.evaluation_edit,
        name="evaluation_edit",
    ),
]
