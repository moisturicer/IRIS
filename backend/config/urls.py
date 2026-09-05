from django.contrib import admin
from django.urls import path, include
from django.conf import settings

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/",          include("apps.accounts.urls.auth")),
    path("api/v1/users/",         include("apps.accounts.urls.users")),
    path("api/v1/",               include("apps.accounts.urls.reference")),  # colleges, depts, courses
    path("api/v1/records/",       include("apps.records.urls")),
    path("api/v1/reviews/",       include("apps.reviews.urls")),
    path("api/v1/documents/",     include("apps.documents.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/audit/",         include("apps.audit.urls")),
    path("api/v1/ai/",            include("apps.ai.urls")),
    path("api/v1/opportunities/", include("apps.opportunities.urls")),
    path("api/v1/dashboard/",     include("apps.records.urls_dashboard")),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

# MEDIA_URL is deliberately not routed, in DEBUG or anywhere else (IR-152 / S-01).
# Django's static() helper would serve every upload with no permission check, and
# "only in development" is not much comfort when development is where real theses
# get loaded to try the workflow out. Uploads go through
# RecordUploadDownloadView / RecordFileDownloadView, which check ownership.
