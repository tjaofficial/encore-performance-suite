from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory

from performance.models import ChoreographyPlan

from .models import (
    Costume,
    CostumeLink,
    StudentCostumeAssignment,
    Vendor,
    VendorSizeChart,
    VendorSizeEntry,
)


class CostumeForm(forms.ModelForm):
    create_student_task = forms.BooleanField(
        required=False,
        label="Create a Task for Students / Guardians",
    )

    task_due_date = forms.DateField(
        required=False,
        label="Task Due Date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    send_notification = forms.BooleanField(
        required=False,
        label="Send a Notification",
    )

    class Meta:
        model = Costume
        fields = [
            "dance",
            "name",
            "gender_scope",
            "vendor",
            "vendor_size_chart",
            "student_notes",
            "internal_notes",
        ]

        labels = {
            "dance": "Dance",
            "name": "Costume Name",
            "gender_scope": "Gender",
            "vendor": "Vendor",
            "vendor_size_chart": "Vendor Size Chart",
            "student_notes": "Student / Guardian Notes",
            "internal_notes": "Internal Staff Notes",
        }

        widgets = {
            "student_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": (
                        "Instructions students and guardians should see."
                    ),
                }
            ),
            "internal_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Private notes for teachers and administrators."
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        class_instance=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        # ModelForm performs model validation before the view's form.save().
        # The unsaved Costume must already carry its studio so clean() can
        # compare it with the selected Dance's studio correctly.
        if studio is not None:
            self.instance.studio = studio

        dances = ChoreographyPlan.objects.none()

        if studio is not None:
            dances = (
                ChoreographyPlan.objects
                .filter(
                    studio=studio,
                )
                .select_related(
                    "class_instance",
                )
            )

        if class_instance is not None:
            dances = dances.filter(
                class_instance=class_instance,
            )

        self.fields[
            "dance"
        ].queryset = dances.order_by(
            "class_instance__name",
            "title",
        )

        self.fields[
            "dance"
        ].label_from_instance = (
            lambda dance: (
                f"{dance.title or 'Untitled Dance'} "
                f"— {dance.class_instance.name}"
            )
        )

        self.fields["vendor"].queryset = Vendor.objects.none()
        self.fields["vendor_size_chart"].queryset = VendorSizeChart.objects.none()

        if studio is not None:
            self.fields["vendor"].queryset = Vendor.objects.filter(
                studio=studio, is_active=True
            ).order_by("name")
            self.fields["vendor_size_chart"].queryset = VendorSizeChart.objects.filter(
                vendor__studio=studio, vendor__is_active=True, is_active=True
            ).select_related("vendor").order_by("vendor__name", "sort_order", "name")

        self.fields["vendor"].required = False
        self.fields["vendor_size_chart"].required = False

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs[
                    "class"
                ] = "encore-checkbox"
            else:
                field.widget.attrs[
                    "class"
                ] = "encore-input"


    def clean(self):
        cleaned = super().clean()
        vendor = cleaned.get("vendor")
        chart = cleaned.get("vendor_size_chart")
        if chart and not vendor:
            self.add_error("vendor", "Select the vendor for this size chart.")
        if chart and vendor and chart.vendor_id != vendor.id:
            self.add_error("vendor_size_chart", "Select a size chart from the chosen vendor.")
        return cleaned


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            "name", "abbreviation", "contact_name", "website",
            "email", "phone", "fax", "customer_number",
            "address_line_1", "address_line_2", "city", "state",
            "postal_code", "notes", "is_active",
        ]
        labels = {
            "name": "Vendor Name",
            "abbreviation": "Abbreviation",
            "contact_name": "Vendor Contact",
            "website": "Store Website",
            "customer_number": "Customer / Account Number",
            "address_line_1": "Address 1",
            "address_line_2": "Address 2",
            "postal_code": "ZIP / Postal Code",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class VendorSizeChartForm(forms.ModelForm):
    class Meta:
        model = VendorSizeChart
        fields = ["name", "gender", "notes", "is_active"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class VendorSizeEntryForm(forms.ModelForm):
    range_measurement_fields = (
        "bust", "waist", "hips", "girth", "height"
    )
    single_measurement_fields = {
        "inseam": "inseam_min",
        "outseam": "outseam_min",
    }

    class Meta:
        model = VendorSizeEntry
        fields = [
            "size_label", "sort_order",
            "bust_min", "bust_max", "waist_min", "waist_max",
            "hips_min", "hips_max", "girth_min", "girth_max",
            "inseam_min", "outseam_min",
            "height_min", "height_max", "age_min", "age_max", "notes",
        ]

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio
        unit = (
            getattr(getattr(studio, "settings", None), "measurement_unit", "in")
            if studio
            else "in"
        )
        multiplier = Decimal("2.54") if unit == "cm" else Decimal("1")
        suffix = "cm" if unit == "cm" else "in."

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"

        display_names = {
            "bust": "Chest",
            "waist": "Waist",
            "hips": "Hips",
            "girth": "Girth",
            "height": "Height",
            "inseam": "Inseam",
            "outseam": "Outseam",
        }

        for key in self.range_measurement_fields:
            for ending in ("min", "max"):
                name = f"{key}_{ending}"
                self.fields[name].label = (
                    f"{display_names[key]} {ending.title()} ({suffix})"
                )
                if self.instance and self.instance.pk:
                    value = getattr(self.instance, name)
                    if value is not None and multiplier != 1:
                        self.initial[name] = round(
                            Decimal(value) * multiplier,
                            2,
                        )

        for key, storage_name in self.single_measurement_fields.items():
            self.fields[storage_name].label = f"{display_names[key]} ({suffix})"
            if self.instance and self.instance.pk:
                value = getattr(self.instance, storage_name)
                if value is not None and multiplier != 1:
                    self.initial[storage_name] = round(
                        Decimal(value) * multiplier,
                        2,
                    )

        self.fields["age_min"].label = "Age Min"
        self.fields["age_max"].label = "Age Max"

    def clean(self):
        cleaned = super().clean()
        unit = (
            getattr(getattr(self.studio, "settings", None), "measurement_unit", "in")
            if self.studio
            else "in"
        )

        if unit == "cm":
            for key in self.range_measurement_fields:
                for ending in ("min", "max"):
                    name = f"{key}_{ending}"
                    value = cleaned.get(name)
                    if value is not None:
                        cleaned[name] = value / Decimal("2.54")

            for storage_name in self.single_measurement_fields.values():
                value = cleaned.get(storage_name)
                if value is not None:
                    cleaned[storage_name] = value / Decimal("2.54")

        return cleaned


VendorSizeEntryFormSet = inlineformset_factory(
    VendorSizeChart,
    VendorSizeEntry,
    form=VendorSizeEntryForm,
    extra=0,
    can_delete=True,
)


class CostumeLinkForm(forms.ModelForm):
    class Meta:
        model = CostumeLink
        fields = [
            "label",
            "url",
            "notes",
        ]

        labels = {
            "label": "Link Label",
            "url": "URL",
            "notes": "Link Notes",
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"


CostumeLinkFormSet = inlineformset_factory(
    Costume,
    CostumeLink,
    form=CostumeLinkForm,
    extra=1,
    can_delete=True,
)


class StudentCostumeAssignmentForm(forms.ModelForm):
    class Meta:
        model = StudentCostumeAssignment
        fields = [
            "costume_size",
            "shoe_size",
            "status",
            "student_notes",
            "internal_notes",
        ]

        widgets = {
            "student_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                }
            ),
            "internal_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                }
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"
