from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("<slug:studio_slug>/", views.task_list, name="task_list"),
    path("<slug:studio_slug>/add/", views.task_create, name="task_create"),
    path("<slug:studio_slug>/quick-add/", views.task_quick_add, name="task_quick_add"),
    path("<slug:studio_slug>/roster-options/", views.class_roster_options, name="class_roster_options"),
    path("<slug:studio_slug>/<int:task_id>/edit/", views.task_edit, name="task_edit"),
    path("<slug:studio_slug>/<int:task_id>/delete/", views.task_delete, name="task_delete"),
    path("<slug:studio_slug>/<int:task_id>/toggle/", views.task_toggle_complete, name="task_toggle_complete"),
    path(
        "<slug:studio_slug>/<int:task_id>/approval/<str:decision>/",
        views.task_approval,
        name="task_approval",
    ),

    path("<slug:studio_slug>/templates/", views.template_list, name="template_list"),
    path("<slug:studio_slug>/templates/add/", views.template_create, name="template_create"),
    path(
        "<slug:studio_slug>/templates/<int:template_id>/",
        views.template_detail,
        name="template_detail",
    ),
    path(
        "<slug:studio_slug>/templates/<int:template_id>/edit/",
        views.template_edit,
        name="template_edit",
    ),
    path(
        "<slug:studio_slug>/templates/<int:template_id>/trigger/add/",
        views.template_trigger_add,
        name="template_trigger_add",
    ),
    path(
        "<slug:studio_slug>/templates/<int:template_id>/run/",
        views.template_run,
        name="template_run",
    ),
]
