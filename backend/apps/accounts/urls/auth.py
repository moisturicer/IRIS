from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from apps.accounts import views
from apps.accounts.recovery import views as recovery

urlpatterns = [
    path("register/",             views.RegisterView.as_view(),       name="auth-register"),
    path("login/",                views.LoginView.as_view(),          name="auth-login"),
    # ADR-054 (IR-789): the data notice and a person's answer to it. Both stay
    # reachable while the current notice is unanswered (`notice.ALLOWED_WHILE_UNANSWERED`).
    path("notice/",               views.CurrentNoticeView.as_view(),  name="notice-current"),
    path("notice/answer/",        views.AnswerNoticeView.as_view(),   name="notice-answer"),
    path("logout/",               views.LogoutView.as_view(),         name="auth-logout"),
    path("token/refresh/",        TokenRefreshView.as_view(),         name="token-refresh"),
    path("activate/<uidb64>/<token>/", views.ActivateView.as_view(), name="auth-activate"),
    path("password/change/",      views.ChangePasswordView.as_view(), name="password-change"),
    # ADR-045 (IR-642): anonymous, JSON only, one fixed answer per outcome.
    path("password/reset/request/", recovery.PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", recovery.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
