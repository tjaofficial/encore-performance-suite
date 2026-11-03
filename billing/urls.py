from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("<slug:studio_slug>/account/<int:account_id>/refund/", views.issue_refund, name="issue_refund"),
    path("<slug:studio_slug>/plans/reviews/account/<int:account_id>/", views.studio_overdue_account, name="studio_overdue_account"),
    path("<slug:studio_slug>/plans/reviews/account/<int:account_id>/action/", views.studio_overdue_account_action, name="studio_overdue_account_action"),
    path("<slug:studio_slug>/family/withdrawal/", views.family_withdrawal_request, name="family_withdrawal_request"),
    path("<slug:studio_slug>/plans/reviews/", views.studio_billing_reviews, name="studio_billing_reviews"),
    path("<slug:studio_slug>/plans/reviews/withdrawal/<int:request_id>/", views.studio_withdrawal_decision, name="studio_withdrawal_decision"),
    path("<slug:studio_slug>/plans/reviews/hold/<int:account_id>/", views.studio_hold_decision, name="studio_hold_decision"),
    path('<slug:studio_slug>/subscription/payments/activate/', views.stripe_activation_page, name='stripe_activation_page'),
    path('<slug:studio_slug>/subscription/payments/activate/session/', views.stripe_activation_session, name='stripe_activation_session'),
    path('<slug:studio_slug>/subscription/payments/activate/status/', views.stripe_activation_status, name='stripe_activation_status'),
    path("<slug:studio_slug>/family/autopay/setup/", views.family_autopay_setup, name="family_autopay_setup"),
    path("<slug:studio_slug>/family/autopay/confirm/", views.family_autopay_confirm, name="family_autopay_confirm"),
    path("<slug:studio_slug>/family/autopay/disable/", views.family_autopay_disable, name="family_autopay_disable"),
    path(
        "stripe/webhook/",
        views.stripe_webhook,
        name="stripe_webhook",
    ),
    path(
        "stripe/connect/webhook/",
        views.stripe_connect_webhook,
        name="stripe_connect_webhook",
    ),
    path(
        "<slug:studio_slug>/subscription/payments/connect/",
        views.stripe_connect_start,
        name="stripe_connect_start",
    ),
    path(
        "<slug:studio_slug>/subscription/payments/connect/refresh/",
        views.stripe_connect_refresh,
        name="stripe_connect_refresh",
    ),
    path(
        "<slug:studio_slug>/subscription/payments/connect/return/",
        views.stripe_connect_return,
        name="stripe_connect_return",
    ),
    path(
        "<slug:studio_slug>/subscription/",
        views.studio_subscription,
        name="studio_subscription",
    ),
    path(
        "<slug:studio_slug>/subscription/history/",
        views.billing_history,
        name="billing_history",
    ),
    path(
        "<slug:studio_slug>/subscription/plan/",
        views.change_subscription_plan,
        name="change_subscription_plan",
    ),
    path(
        "<slug:studio_slug>/subscription/drawing-board/",
        views.change_drawing_board,
        name="change_drawing_board",
    ),
    path(
        "<slug:studio_slug>/subscription/cancel/",
        views.cancel_studio_subscription,
        name="cancel_studio_subscription",
    ),
    path(
        "<slug:studio_slug>/subscription/resume/",
        views.resume_studio_subscription,
        name="resume_studio_subscription",
    ),
    path(
        "<slug:studio_slug>/subscription/notices/<int:notice_id>/read/",
        views.mark_subscription_notice_read,
        name="mark_subscription_notice_read",
    ),
    path(
        "<slug:studio_slug>/family/payments/",
        views.family_payments,
        name="family_payments",
    ),
    path(
        "<slug:studio_slug>/family/payments/intent/",
        views.family_payment_intent,
        name="family_payment_intent",
    ),
    path(
        "<slug:studio_slug>/family/payments/return/",
        views.family_payment_return,
        name="family_payment_return",
    ),
    path(
        "<slug:studio_slug>/family/billing/cancel/",
        views.cancel_family_billing,
        name="cancel_family_billing",
    ),
    path(
        "<slug:studio_slug>/account/<int:account_id>/",
        views.account_detail,
        name="account_detail",
    ),
    path(
        "<slug:studio_slug>/account/<int:account_id>/charge/add/",
        views.add_charge,
        name="add_charge",
    ),
    path(
        "<slug:studio_slug>/account/<int:account_id>/payment/add/",
        views.record_payment,
        name="record_payment",
    ),
    path(
        "<slug:studio_slug>/account/<int:account_id>/credit/add/",
        views.add_credit,
        name="add_credit",
    ),
    path(
        "<slug:studio_slug>/plans/",
        views.tuition_plan_list,
        name="tuition_plan_list",
    ),
    path(
        "<slug:studio_slug>/plans/add/",
        views.tuition_plan_create,
        name="tuition_plan_create",
    ),
    path(
        "<slug:studio_slug>/plans/<int:plan_id>/edit/",
        views.tuition_plan_edit,
        name="tuition_plan_edit",
    ),
    path(
        "<slug:studio_slug>/run-recurring/",
        views.run_recurring_billing,
        name="run_recurring_billing",
    ),
]
