from django.contrib import admin

from .models import Holiday, Turnaround


@admin.register(Turnaround)
class TurnaroundAdmin(admin.ModelAdmin):
    list_display = ("party", "working_days")


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")
    ordering = ("date",)
