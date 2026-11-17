from django.urls import path

from .views import HealthView, TripPlanView

urlpatterns = [
    path("route/", TripPlanView.as_view(), name="route-plan"),
    path("health/", HealthView.as_view(), name="health"),
]
