from django import forms
from django.contrib.auth import get_user_model

from .models import CallRecord, Customer


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
        self.fields["assignee"].queryset = get_user_model().objects.filter(
            is_active=True
        ).order_by("username")
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

    def save(self, commit=True):
        call = super().save(commit=False)
        call.outcome_locked = True
        if commit:
            call.save()
        return call
