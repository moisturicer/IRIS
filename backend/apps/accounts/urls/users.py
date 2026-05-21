from django.urls import path
from apps.accounts import views

urlpatterns = [
    path("",              views.UserListView.as_view(),        name="user-list"),
    path("me/",           views.MeView.as_view(),              name="user-me"),
    path("<int:pk>/",     views.UserDetailView.as_view(),      name="user-detail"),
    path("<int:pk>/role/",   views.ChangeUserRoleView.as_view(),  name="user-change-role"),
    path("<int:pk>/lock/",   views.LockUserView.as_view(),       name="user-lock"),
    path("locked/",          views.LockedUsersView.as_view(),    name="user-locked"),
    path("<int:pk>/unlock/", views.UnlockUserView.as_view(),     name="user-unlock"),
    path("role-requests/",   views.RoleRequestListView.as_view(),   name="role-request-list"),
    path("role-requests/<int:pk>/", views.RoleRequestDetailView.as_view(), name="role-request-detail"),
]
