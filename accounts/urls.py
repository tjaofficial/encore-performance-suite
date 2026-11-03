from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "register/",
        views.register_studio,
        name="register",
    ),
    path(
        "register/success/",
        views.registration_success,
        name="registration_success",
    ),
    path(
        "register/verify/<uuid:token>/",
        views.verify_registration_email,
        name="verify_registration_email",
    ),
    path(
        "register/resend-verification/",
        views.resend_registration_verification,
        name="resend_registration_verification",
    ),
    path(
        "login/",
        views.login_view,
        name="login",
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),
    path(
        "profile/",
        views.profile_view,
        name="profile",
    ),
    path(
        "workspaces/",
        views.workspace_selector,
        name="workspace_selector",
    ),
    path(
        "workspaces/<int:membership_id>/select/",
        views.select_workspace,
        name="select_workspace",
    ),
    path(
        "no-studio-access/",
        views.no_studio_access,
        name="no_studio_access",
    ),
]
