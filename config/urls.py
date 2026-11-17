from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from trips.views import MapPageView

urlpatterns = [
    path("", MapPageView.as_view(), name="map"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("trips.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
