from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import CallRecord, Customer


ROLE_CHOICES = (
    ("", "انتخاب نقش"),
    ("CRM Manager", "مدیر"),
    ("CRM Marketer", "بازاریاب"),
)


class TeamUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        label="نقش",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)
        labels = {"username": "نام کاربری"}
        widgets = {"username": forms.TextInput(attrs={"autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
            if name.startswith("password"):
                field.widget.attrs["autocomplete"] = "new-password"
        self.fields["password1"].label = "گذرواژهٔ اولیه"
        self.fields["password2"].label = "تکرار گذرواژه"

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            role, _ = Group.objects.get_or_create(name=self.cleaned_data["role"])
            user.groups.add(role)
            self.save_m2m()
        return user


class TeamUserUpdateForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput)
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="نقش")
    is_active = forms.BooleanField(required=False, label="حساب فعال باشد")
    confirm = forms.BooleanField(required=True, label="تغییر این حساب را تأیید می‌کنم")

    def __init__(self, *args, user=None, actor=None, **kwargs):
        self.user = user
        self.actor = actor
        initial = kwargs.pop("initial", {})
        if user is not None:
            crm_roles = set(
                user.groups.filter(name__in=[choice[0] for choice in ROLE_CHOICES])
                .values_list("name", flat=True)
            )
            initial.update({
                "user_id": user.pk,
                "role": next(iter(crm_roles)) if len(crm_roles) == 1 else "",
                "is_active": user.is_active,
            })
        super().__init__(*args, initial=initial, **kwargs)
        for name, field in self.fields.items():
            if name in {"is_active", "confirm"}:
                field.widget.attrs["class"] = "form-control form-check-input"
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_role(self):
        return self.cleaned_data["role"]

    def clean(self):
        cleaned_data = super().clean()
        if self.user is not None and cleaned_data.get("user_id") != self.user.pk:
            raise ValidationError("درخواست حساب معتبر نیست.")
        if self.user is None or self.actor is None or "role" not in cleaned_data:
            return cleaned_data

        will_remain_manager = (
            cleaned_data["role"] == "CRM Manager"
            and cleaned_data.get("is_active", self.user.is_active)
        )
        if self.user.pk == self.actor.pk and not will_remain_manager:
            self.add_error(
                "role", "نمی‌توانید دسترسی مدیریتی حساب خود را حذف یا غیرفعال کنید."
            )
        currently_manager = self.user.groups.filter(name="CRM Manager").exists()
        if currently_manager and not will_remain_manager:
            other_managers = get_user_model().objects.filter(
                is_active=True, groups__name="CRM Manager"
            ).exclude(pk=self.user.pk).distinct().exists()
            if not other_managers:
                self.add_error("role", "حداقل یک مدیر فعال باید باقی بماند.")
        return cleaned_data


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            "name", "business_type", "business_name", "category", "phone",
            "phone_secondary", "phone_tertiary", "status", "source", "address",
            "notes", "assignee",
        )
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "business_type": forms.TextInput(),
            "business_name": forms.TextInput(),
            "phone": forms.TextInput(attrs={"inputmode": "tel"}),
            "phone_secondary": forms.TextInput(attrs={"inputmode": "tel"}),
            "phone_tertiary": forms.TextInput(attrs={"inputmode": "tel"}),
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assignee_queryset = get_user_model().objects.filter(is_active=True)
        if self.instance.pk and self.instance.assignee_id:
            assignee_queryset = assignee_queryset.filter(
                Q(is_active=True) | Q(pk=self.instance.assignee_id)
            )
        self.fields["assignee"].queryset = assignee_queryset.order_by("username")
        self.fields["assignee"].required = False
        self.fields["category"].required = True
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("status"):
            cleaned_data["status"] = Customer.Status.NO_CONTACT
        return cleaned_data


class CallOutcomeForm(forms.ModelForm):
    class Meta:
        model = CallRecord
        fields = ("outcome",)
        widgets = {"outcome": forms.Select(attrs={"class": "form-control"})}
