from django.contrib import admin

from .models import (
    Charge,
    Credit,
    CreditAllocation,
    FamilyAccount,
    Payment,
    PaymentAllocation,
    RecurringChargeSchedule,
    TuitionPlan,
)


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0


class CreditAllocationInline(admin.TabularInline):
    model = CreditAllocation
    extra = 0


@admin.register(FamilyAccount)
class FamilyAccountAdmin(admin.ModelAdmin):
    list_display = (
        "family",
        "studio",
        "balance_display",
        "autopay_enabled",
        "is_active",
    )

    list_filter = (
        "studio",
        "autopay_enabled",
        "is_active",
    )

    search_fields = (
        "family__family_name",
        "family__primary_contact_first_name",
        "family__primary_contact_last_name",
        "family__primary_email",
    )

    def balance_display(self, obj):
        return f"${obj.balance:.2f}"

    balance_display.short_description = "Balance"


@admin.register(TuitionPlan)
class TuitionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "frequency",
        "amount",
        "registration_fee",
        "late_fee",
        "is_active",
    )

    list_filter = (
        "studio",
        "frequency",
        "is_active",
    )

    search_fields = (
        "name",
        "description",
    )


@admin.register(RecurringChargeSchedule)
class RecurringChargeScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "student",
        "class_instance",
        "tuition_plan",
        "start_date",
        "next_charge_date",
        "is_active",
    )

    list_filter = (
        "account__studio",
        "is_active",
        "schedule_type",
    )

    search_fields = (
        "account__family__family_name",
        "student__first_name",
        "student__last_name",
        "class_instance__name",
        "tuition_plan__name",
    )


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "description",
        "charge_type",
        "amount",
        "balance_display",
        "due_date",
        "status",
    )

    list_filter = (
        "account__studio",
        "charge_type",
        "status",
        "due_date",
    )

    search_fields = (
        "account__family__family_name",
        "student__first_name",
        "student__last_name",
        "description",
    )

    inlines = [
        PaymentAllocationInline,
        CreditAllocationInline,
    ]

    def balance_display(self, obj):
        return f"${obj.balance_remaining:.2f}"

    balance_display.short_description = "Remaining"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "amount",
        "method",
        "status",
        "paid_at",
        "unallocated_display",
    )

    list_filter = (
        "account__studio",
        "method",
        "status",
    )

    search_fields = (
        "account__family__family_name",
        "external_reference",
    )

    inlines = [
        PaymentAllocationInline,
    ]

    def unallocated_display(self, obj):
        return f"${obj.unallocated_amount:.2f}"

    unallocated_display.short_description = "Unallocated"


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "description",
        "credit_type",
        "amount",
        "remaining_display",
        "is_void",
    )

    list_filter = (
        "account__studio",
        "credit_type",
        "is_void",
    )

    search_fields = (
        "account__family__family_name",
        "description",
    )

    inlines = [
        CreditAllocationInline,
    ]

    def remaining_display(self, obj):
        return f"${obj.remaining_amount:.2f}"

    remaining_display.short_description = "Remaining"


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "payment",
        "charge",
        "amount",
        "created_at",
    )


@admin.register(CreditAllocation)
class CreditAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "credit",
        "charge",
        "amount",
        "created_at",
    )
