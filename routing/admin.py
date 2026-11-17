from django.contrib import admin

from .models import GeocodeCacheEntry


@admin.register(GeocodeCacheEntry)
class GeocodeCacheEntryAdmin(admin.ModelAdmin):
    list_display = ("query", "display_name", "latitude", "longitude", "created_at")
    search_fields = ("query", "display_name")
    readonly_fields = ("created_at",)
