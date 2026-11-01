from django.urls import path
from . import views_dashboard

urlpatterns = [
    path("stats/", views_dashboard.DashboardStatsView.as_view(), name="dashboard-stats"),
]
