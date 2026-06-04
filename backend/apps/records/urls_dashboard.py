from django.urls import path
from . import views_dashboard

urlpatterns = [
    path("stats/",                   views_dashboard.DashboardStatsView.as_view(),     name="dashboard-stats"),
    path("charts/classifications/",  views_dashboard.ClassificationChartView.as_view(), name="chart-classifications"),
    path("charts/psced/",            views_dashboard.PSCEDChartView.as_view(),          name="chart-psced"),
    # TODO (M07 — FR-M7-01): path("pipeline/<int:record_pk>/", views_dashboard.PipelineProgressView.as_view(), name="dashboard-pipeline"),
]
