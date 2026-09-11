from django import forms
from django.db.models import Q

from classes.models import Class
from instructors.models import Instructor
from students.models import Student

from .models import EvaluationTemplate, StudentEvaluation


class StudentEvaluationForm(forms.ModelForm):
    class Meta:
        model = StudentEvaluation
        fields = [
            "student",
            "class_instance",
            "instructor",
            "template",
            "evaluation_date",
            "overall_notes",
            "goals",
            "status",
        ]

        widgets = {
            "evaluation_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "overall_notes": forms.Textarea(
                attrs={"rows": 4}
            ),
            "goals": forms.Textarea(
                attrs={"rows": 4}
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        instructor=None,
        teacher_mode=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if studio is not None:
            self.fields["student"].queryset = Student.objects.filter(
                studio=studio,
                is_active=True,
                enrollments__status="active",
            ).distinct().order_by(
                "last_name",
                "first_name",
            )

            self.fields["class_instance"].queryset = Class.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("name")

            self.fields["instructor"].queryset = Instructor.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("last_name", "first_name")

            self.fields["template"].queryset = EvaluationTemplate.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("name")

        if teacher_mode and instructor is not None:
            self.fields["instructor"].initial = instructor
            self.fields["instructor"].disabled = True

            self.fields["class_instance"].queryset = Class.objects.filter(
                studio=studio,
                is_active=True,
            ).filter(
                Q(instructor=instructor)
                | Q(assistant_instructor=instructor)
            ).distinct().order_by("name")

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class CriterionResponseForm(forms.Form):
    rating = forms.CharField(required=False)

    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": "encore-input",
            }
        ),
    )

    def __init__(self, *args, criterion=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.criterion = criterion

        if criterion is None:
            return

        self.fields["rating"].label = criterion.name

        if (
            criterion.rating_scale
            == criterion.RatingScale.THREE_POINT
        ):
            choices = [
                ("", "Select"),
                ("needs_work", "Needs Work"),
                ("developing", "Developing"),
                ("strong", "Strong"),
            ]
        else:
            choices = [
                ("", "Select"),
                ("1", "1 - Needs Significant Work"),
                ("2", "2 - Developing"),
                ("3", "3 - Meets Expectations"),
                ("4", "4 - Strong"),
                ("5", "5 - Excellent"),
            ]

        self.fields["rating"] = forms.ChoiceField(
            choices=choices,
            required=criterion.is_required,
            label=criterion.name,
            widget=forms.Select(
                attrs={"class": "encore-input"}
            ),
        )
