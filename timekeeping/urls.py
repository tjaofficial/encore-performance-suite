from django.urls import path

from . import views

app_name = "timekeeping"

urlpatterns = [
    path(
        "<slug:studio_slug>/",
        views.extra_work_list,
        name="extra_work_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.extra_work_create,
        name="extra_work_create",
    ),
]
