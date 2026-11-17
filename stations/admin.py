from django.contrib import admin

from .models import FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("opis_id", "name", "city", "state", "retail_price", "price_samples", "has_coordinates")
    list_filter = ("state",)
    search_fields = ("name", "city", "address", "opis_id")
    ordering = ("state", "city", "name")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(boolean=True, description="Geocoded")
    def has_coordinates(self, station):
        return station.has_coordinates
