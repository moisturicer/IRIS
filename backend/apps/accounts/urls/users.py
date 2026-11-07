from django.urls import path
from apps.accounts import views

urlpatterns = [
    path("",              views.UserListView.as_view(),        name="user-list"),
    path("advisers/",     views.AdviserListView.as_view(),     name="user-advisers"),
    path("me/",           views.MeView.as_view(),              name="user-me"),
    path("me/photo/",     views.MePhotoView.as_view(),         name="user-me-photo"),
    path("interests/",    views.InterestSuggestionsView.as_view(), name="user-interest-suggestions"),
    path("<int:pk>/photo/", views.UserPhotoView.as_view(),     name="user-photo"),
    # IR-696: a person's public profile, for any signed-in user.
    path("<int:pk>/profile/", views.PublicProfileView.as_view(), name="user-profile"),
    path("<int:pk>/profile/research/", views.PublicProfileResearchView.as_view(), name="user-profile-research"),
    path("<int:pk>/profile/advised/",  views.PublicProfileAdvisedView.as_view(),  name="user-profile-advised"),
    path("<int:pk>/profile/collaborators/",
         views.PublicProfileCollaboratorsView.as_view(), name="user-profile-collaborators"),
    path("<int:pk>/",     views.UserDetailView.as_view(),      name="user-detail"),
    path("<int:pk>/role/",   views.ChangeUserRoleView.as_view(),  name="user-change-role"),
    path("<int:pk>/coordinator/", views.OfficeCoordinatorView.as_view(), name="user-coordinator"),
    path("<int:pk>/lock/",   views.LockUserView.as_view(),       name="user-lock"),
    path("locked/",          views.LockedUsersView.as_view(),    name="user-locked"),
    path("<int:pk>/unlock/", views.UnlockUserView.as_view(),     name="user-unlock"),
    path("role-requests/",   views.RoleRequestListView.as_view(),   name="role-request-list"),
    path("role-requests/<int:pk>/", views.RoleRequestDetailView.as_view(), name="role-request-detail"),
    # Active session management
    path("sessions/",            views.ActiveSessionsView.as_view(), name="user-sessions"),
    path("sessions/<str:jti>/",  views.RevokeSessionView.as_view(),  name="user-session-revoke"),
]
