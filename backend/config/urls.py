from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

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
    path("api/v1/dashboard/",     include("apps.records.urls_dashboard")),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
