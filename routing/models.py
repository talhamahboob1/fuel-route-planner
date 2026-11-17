from django.db import models


class GeocodeCacheEntry(models.Model):
    query_key = models.CharField(max_length=255, unique=True)
    query = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "geocode cache entries"

    def __str__(self):
        return f"{self.query} -> {self.display_name}"
