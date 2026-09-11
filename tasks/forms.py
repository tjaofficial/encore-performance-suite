from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import inlineformset_factory

from classes.models import Class
from enrollments.models import Enrollment
from students.models import Student
from studios.models import StudioMembership

from .models import (
    Task,
    TaskTemplate,
    TaskTemplateItem,
    TaskTemplateTrigger,
)

User = get_user_model()


class TaskForm(forms.ModelForm):
    selected_teachers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Selected Teachers",
        widget=forms.CheckboxSelectMultiple,
    )

    selected_students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.none(),
        required=False,
        label="Selected Students",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "priority",
            "due_date",
            "context_type",
            "class_instance",
            "student",
            "audience_type",
            "notify_assignees",
        ]

        labels = {
            "class_instance": "Related Class",
            "student": "Related Student",
            "audience_type": "Assign To",
            "notify_assignees": "Notify Assignees",
        }

        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(
        self,
        *args,
        studio=None,
        user=None,
        role=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.studio = studio
        self.user = user
        self.role = role

        if studio is not None:
            self.instance.studio = studio

        classes = Class.objects.none()
        students = Student.objects.none()

        if studio is not None:
            classes = Class.objects.filter(
                studio=studio,
                is_active=True,
            )

            students = Student.objects.filter(
                studio=studio,
                is_active=True,
            )

            if (
                role == StudioMembership.Role.TEACHER
                and user is not None
            ):
                classes = classes.filter(
                    Q(instructor__user=user)
                    | Q(assistant_instructor__user=user)
                ).distinct()

                students = students.filter(
                    enrollments__class_instance__in=classes,
                    enrollments__status=Enrollment.Status.ACTIVE,
                ).distinct()

        self.fields["class_instance"].queryset = classes.order_by("name")
        self.fields["student"].queryset = students.order_by(
            "last_name",
            "first_name",
        )

        teacher_memberships = StudioMembership.objects.none()

        if studio is not None:
            teacher_memberships = (
                StudioMembership.objects
                .filter(
                    studio=studio,
                    role=StudioMembership.Role.TEACHER,
                    is_active=True,
                    user__is_active=True,
                )
                .select_related("user")
                .order_by(
                    "user__first_name",
                    "user__last_name",
                    "user__email",
                )
            )

        teacher_ids = list(
            teacher_memberships.values_list(
                "user_id",
                flat=True,
            )
        )

        self.fields["selected_teachers"].queryset = (
            User.objects
            .filter(pk__in=teacher_ids)
            .order_by(
                "first_name",
                "last_name",
                "email",
            )
        )

        selected_class_id = None

        if self.is_bound:
            selected_class_id = self.data.get(
                "class_instance"
            )
        elif self.instance.pk:
            selected_class_id = (
                self.instance.class_instance_id
            )

        selected_student_qs = students

        if (
            selected_class_id
            and str(selected_class_id).isdigit()
        ):
            selected_student_qs = (
                selected_student_qs
                .filter(
                    enrollments__class_instance_id=int(selected_class_id),
                    enrollments__status=Enrollment.Status.ACTIVE,
                )
                .distinct()
            )

        self.fields["selected_students"].queryset = (
            selected_student_qs.order_by(
                "last_name",
                "first_name",
            )
        )

        if role == StudioMembership.Role.ADMINISTRATOR:
            allowed = {
                Task.AudienceType.SELF,
                Task.AudienceType.SELECTED_TEACHERS,
                Task.AudienceType.ALL_TEACHERS,
                Task.AudienceType.CLASS_STAFF,
                Task.AudienceType.SELECTED_STUDENTS,
                Task.AudienceType.ALL_STUDENTS_IN_CLASS,
            }

        elif role == StudioMembership.Role.TEACHER:
            allowed = {
                Task.AudienceType.SELF,
                Task.AudienceType.ADMIN,
                Task.AudienceType.CLASS_STAFF,
                Task.AudienceType.SELECTED_STUDENTS,
                Task.AudienceType.ALL_STUDENTS_IN_CLASS,
            }

        else:
            allowed = set()

        self.fields["audience_type"].choices = [
            choice
            for choice in Task.AudienceType.choices
            if choice[0] in allowed
        ]

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs["class"] = (
                    "encore-checkbox"
                )
            elif isinstance(
                field.widget,
                forms.CheckboxSelectMultiple,
            ):
                field.widget.attrs["class"] = (
                    "task-checkbox-list"
                )
            else:
                field.widget.attrs["class"] = (
                    "encore-input"
                )

    def clean(self):
        cleaned = super().clean()

        audience = cleaned.get(
            "audience_type"
        )

        class_instance = cleaned.get(
            "class_instance"
        )

        selected_teachers = cleaned.get(
            "selected_teachers"
        )

        selected_students = cleaned.get(
            "selected_students"
        )

        if (
            audience
            == Task.AudienceType.SELECTED_TEACHERS
            and not selected_teachers
        ):
            self.add_error(
                "selected_teachers",
                "Select at least one teacher.",
            )

        if audience in {
            Task.AudienceType.CLASS_STAFF,
            Task.AudienceType.SELECTED_STUDENTS,
            Task.AudienceType.ALL_STUDENTS_IN_CLASS,
        } and not class_instance:
            self.add_error(
                "class_instance",
                "Select the related class for this assignment.",
            )

        if (
            audience
            == Task.AudienceType.SELECTED_STUDENTS
            and not selected_students
        ):
            self.add_error(
                "selected_students",
                "Select at least one student.",
            )

        if audience in {
            Task.AudienceType.SELECTED_STUDENTS,
            Task.AudienceType.ALL_STUDENTS_IN_CLASS,
        }:
            cleaned["context_type"] = (
                Task.ContextType.CLASS
            )

        return cleaned


class TaskTemplateForm(forms.ModelForm):
    class Meta:
        model = TaskTemplate
        fields = [
            "name",
            "description",
            "visibility",
            "status",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "encore-input"
            )


class TaskTemplateItemForm(forms.ModelForm):
    class Meta:
        model = TaskTemplateItem
        fields = [
            "order",
            "title",
            "description",
            "context_type",
            "audience_type",
            "priority",
            "due_rule",
            "due_offset_days",
            "due_time",
            "notify_assignees",
        ]

        widgets = {
            "order": forms.HiddenInput(),
            "description": forms.Textarea(
                attrs={"rows": 2}
            ),
            "due_time": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        allowed_template_audiences = {
            Task.AudienceType.SELF,
            Task.AudienceType.ADMIN,
            Task.AudienceType.ALL_TEACHERS,
            Task.AudienceType.CLASS_STAFF,
            Task.AudienceType.ALL_STUDENTS_IN_CLASS,
            Task.AudienceType.RELATED_STUDENT,
        }

        self.fields["audience_type"].choices = [
            choice
            for choice in Task.AudienceType.choices
            if choice[0] in allowed_template_audiences
        ]

        self.fields["context_type"].label = "Task Belongs To"
        self.fields["audience_type"].label = "Who Completes This Task?"
        self.fields["due_rule"].label = "When Is It Due?"
        self.fields["due_rule"].choices = [
            (
                TaskTemplateItem.DueRule.NONE,
                "No due date",
            ),
            (
                TaskTemplateItem.DueRule.SAME_DAY,
                "Due the day this template runs",
            ),
            (
                TaskTemplateItem.DueRule.DAYS_AFTER,
                "Due a set number of days after this template runs",
            ),
        ]
        self.fields["due_offset_days"].label = "Days After Template Runs"
        self.fields["due_time"].label = "Due Time"
        self.fields["notify_assignees"].label = "Notify Assignees"

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs["class"] = (
                    "encore-checkbox"
                )
            else:
                field.widget.attrs["class"] = (
                    "encore-input"
                )


TaskTemplateItemFormSet = inlineformset_factory(
    TaskTemplate,
    TaskTemplateItem,
    form=TaskTemplateItemForm,
    extra=1,
    can_delete=True,
)


class TaskTemplateTriggerForm(forms.ModelForm):
    weekdays = forms.MultipleChoiceField(
        required=False,
        choices=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        widget=forms.CheckboxSelectMultiple,
    )

    run_date = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date"}
        ),
    )

    run_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            attrs={"type": "time"}
        ),
    )

    class Meta:
        model = TaskTemplateTrigger
        fields = [
            "trigger_type",
            "is_enabled",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config = (
            self.instance.configuration
            if self.instance and self.instance.pk
            else {}
        )

        self.fields["weekdays"].initial = [
            str(value)
            for value in config.get(
                "weekdays",
                [],
            )
        ]

        self.fields["run_date"].initial = (
            config.get("run_date")
        )

        self.fields["run_time"].initial = (
            config.get("run_time")
        )

        self.fields["trigger_type"].label = "When Should This Template Run?"
        self.fields["trigger_type"].choices = [
            (
                TaskTemplateTrigger.TriggerType.MANUAL,
                "Manual only — run it when I choose",
            ),
            (
                TaskTemplateTrigger.TriggerType.NEW_CLASS,
                "Automatically when a new class is created",
            ),
            (
                TaskTemplateTrigger.TriggerType.NEW_STUDENT,
                "Automatically when a new student is added",
            ),
            (
                TaskTemplateTrigger.TriggerType.NEW_INSTRUCTOR,
                "Automatically when a new instructor is added",
            ),
            (
                TaskTemplateTrigger.TriggerType.NEW_ENROLLMENT,
                "Automatically when a new enrollment is created",
            ),
            (
                TaskTemplateTrigger.TriggerType.SPECIFIC_DATETIME,
                "Automatically on a specific date and time",
            ),
            (
                TaskTemplateTrigger.TriggerType.RECURRING,
                "Automatically on selected days each week",
            ),
        ]
        self.fields["weekdays"].label = "Days of the Week"
        self.fields["run_date"].label = "Run Date"
        self.fields["run_time"].label = "Run Time"
        self.fields["is_enabled"].label = "Trigger Active"

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs["class"] = (
                    "encore-checkbox"
                )
            elif isinstance(
                field.widget,
                forms.CheckboxSelectMultiple,
            ):
                field.widget.attrs["class"] = (
                    "task-checkbox-list"
                )
            else:
                field.widget.attrs["class"] = (
                    "encore-input"
                )

    def clean(self):
        cleaned = super().clean()

        trigger_type = cleaned.get(
            "trigger_type"
        )

        if (
            trigger_type
            == TaskTemplateTrigger.TriggerType.SPECIFIC_DATETIME
            and (
                not cleaned.get("run_date")
                or not cleaned.get("run_time")
            )
        ):
            raise forms.ValidationError(
                "Specific Date / Time triggers require both a date and time."
            )

        if (
            trigger_type
            == TaskTemplateTrigger.TriggerType.RECURRING
            and (
                not cleaned.get("weekdays")
                or not cleaned.get("run_time")
            )
        ):
            raise forms.ValidationError(
                "Recurring triggers require at least one weekday and a time."
            )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False
        )

        instance.configuration = {
            "weekdays": [
                int(value)
                for value in self.cleaned_data.get(
                    "weekdays",
                    [],
                )
            ],
            "run_date": (
                self.cleaned_data["run_date"].isoformat()
                if self.cleaned_data.get("run_date")
                else None
            ),
            "run_time": (
                self.cleaned_data["run_time"].strftime("%H:%M")
                if self.cleaned_data.get("run_time")
                else None
            ),
        }

        if commit:
            instance.save()

        return instance


TaskTemplateTriggerFormSet = inlineformset_factory(
    TaskTemplate,
    TaskTemplateTrigger,
    form=TaskTemplateTriggerForm,
    extra=1,
    can_delete=True,
)
