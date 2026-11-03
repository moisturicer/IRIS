"""
Users in Django's admin site (ADR-051 §5-6, amended 2026-11-03, IR-781).

The one place the System Admin role is given: by a Django superuser, never
through IRIS's API. A System Admin is a named person's account and not a Django
superuser, so the forms refuse the role together with either Django flag. Only
`seed_demo`'s demo login holds both, and it isn't made here.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from core.enums import RoleName

from .models import User

NOT_A_SUPERUSER = (
    "A System Admin is a named person's account, not a Django superuser or staff "
    "member. Clear those flags, or give another role."
)


class SystemAdminIsNotASuperuserMixin:
    """Refuses the System Admin role together with either Django flag (ADR-051 §6)."""

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role is not None and role.name == RoleName.SYSTEM_ADMIN and (
            cleaned.get("is_superuser") or cleaned.get("is_staff")
        ):
            raise forms.ValidationError(NOT_A_SUPERUSER)
        return cleaned


class IrisUserCreationForm(SystemAdminIsNotASuperuserMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "middle_initial", "last_name", "role")


class IrisUserChangeForm(SystemAdminIsNotASuperuserMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = IrisUserChangeForm
    add_form = IrisUserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_superuser")
    list_filter = ("role", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("first_name", "middle_initial", "last_name")}),
        ("IRIS", {"fields": ("role", "is_verified", "is_active", "is_locked", "is_office_coordinator")}),
        ("Django admin site", {"fields": ("is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "first_name", "middle_initial", "last_name", "role",
                           "password1", "password2")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # A role change goes through `assign_role`, as everywhere, so the
        # coordinator grant for the old role's office goes with it (IR-415).
        if change and "role" in form.changed_data:
            obj.assign_role(obj.role)
