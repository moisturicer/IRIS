from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from core.permissions import IsAdmin
from core.pagination import LargeResultsPagination
from apps.audit.services import create_audit_event
from .models import User, College, Department, Course, RoleRequest, SystemSetting
from .serializers import (
    UserSerializer, RegisterSerializer, ChangePasswordSerializer,
    CollegeSerializer, DepartmentSerializer, CourseSerializer,
    RoleRequestSerializer, SystemSettingSerializer,
)
from .services import send_verification_email, activate_user, approve_role_request, decline_role_request


class RegisterView(generics.CreateAPIView):
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        from django.db import transaction
        with transaction.atomic():
            user = serializer.save()

            # Create a RoleRequest so admins can approve/decline
            role_name = getattr(serializer, "_role_name", None)
            if role_name:
                from .models import Role
                try:
                    role = Role.objects.get(name=role_name)
                    RoleRequest.objects.create(user=user, requested_role=role)
                except Role.DoesNotExist:
                    pass  # Unknown role — skip silently

            # Send email verification link (inside transaction so a crash rolls back the user)
            send_verification_email(user, self.request)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate
        email    = request.data.get("email")
        password = request.data.get("password")
        user = authenticate(request, username=email, password=password)
        if not user:
            create_audit_event("FAILED_LOGIN", None, metadata={"email": email})
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_verified:
            return Response({"detail": "Email not verified."}, status=status.HTTP_403_FORBIDDEN)
        if user.is_locked:
            return Response({"detail": "Account is locked."}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        create_audit_event("LOGIN", user, metadata={"email": user.email})
        return Response({
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
            "user":    UserSerializer(user).data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data["refresh"])
            token.blacklist()
            create_audit_event("LOGOUT", request.user, metadata={"email": request.user.email})
        except Exception:
            pass
        return Response({"detail": "Logged out."})


class ActivateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, uidb64, token):
        user = activate_user(uidb64, token)
        if user:
            return Response({"detail": "Account activated."})
        return Response({"detail": "Invalid or expired link."}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Password changed."})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserListView(generics.ListAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset           = User.objects.select_related("role").order_by("-date_joined")


class AdviserListView(generics.ListAPIView):
    """
    GET /users/advisers/
    Returns all active users whose role is "Adviser".
    Used by the record creation form so students can pick their adviser.
    Any authenticated user may call this endpoint.
    """
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = LargeResultsPagination  # advisers list is small; return them all at once

    def get_queryset(self):
        return (
            User.objects
            .filter(role__name="Adviser", is_active=True)
            .select_related("role")
            .order_by("last_name", "first_name")
        )


class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset           = User.objects.all()


class ChangeUserRoleView(APIView):
    """PATCH /users/<id>/role/ -- change a user's role by name or ID."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        from .models import Role
        user = User.objects.get(pk=pk)

        role_name = request.data.get("role_name")
        role_id   = request.data.get("role")

        if role_name:
            try:
                role = Role.objects.get(name=role_name)
            except Role.DoesNotExist:
                return Response({"detail": f"Role '{role_name}' not found."}, status=400)
        elif role_id:
            try:
                role = Role.objects.get(pk=role_id)
            except Role.DoesNotExist:
                return Response({"detail": "Role not found."}, status=400)
        else:
            return Response({"detail": "role_name or role is required."}, status=400)

        user.role = role
        user.save(update_fields=["role"])

        create_audit_event(
            "ROLE_CHANGE", request.user,
            metadata={"target_user": user.email, "new_role": role.name},
        )

        from core.utils import send_email_async
        from django.conf import settings
        send_email_async(
            subject="[IRIS] Your role has been updated",
            message=(
                f"Hello {user.first_name},\n\n"
                f"An administrator has updated your IRIS role to: {role.name}.\n\n"
                f"You may need to log out and back in for the change to take effect.\n\n"
                f"Log in at: {settings.FRONTEND_URL}/login\n\n"
                f"— The IRIS Team"
            ),
            recipient_list=[user.email],
        )

        return Response(UserSerializer(user).data)


class LockUserView(APIView):
    """PATCH /users/<id>/lock/ -- lock or unlock an account."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        user      = User.objects.get(pk=pk)
        is_locked = request.data.get("is_locked")
        if is_locked is None:
            return Response({"detail": "is_locked is required."}, status=400)
        user.is_locked = bool(is_locked)
        user.save(update_fields=["is_locked"])
        action     = "locked" if user.is_locked else "unlocked"
        event_type = "ACCOUNT_LOCKED" if user.is_locked else "ACCOUNT_UNLOCKED"

        create_audit_event(
            event_type, request.user,
            metadata={"target_user": user.email},
        )

        return Response({"detail": f"Account {action}.", "is_locked": user.is_locked})


class LockedUsersView(generics.ListAPIView):
    """
    Lists accounts that are locked.
    Combines manually locked accounts (is_locked=True) with any accounts
    that django-axes has flagged for repeated failed login attempts.
    """
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        from django.db.models import Q
        q = Q(is_locked=True)

        try:
            from axes.models import AccessAttempt
            axes_emails = AccessAttempt.objects.values_list("username", flat=True).distinct()
            q |= Q(email__in=axes_emails)
        except ImportError:
            pass   # axes not installed — fall back to manual locks only

        return User.objects.filter(q).select_related("role").distinct()


class UnlockUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        user = User.objects.get(pk=pk)
        user.is_locked = False
        user.save(update_fields=["is_locked"])

        # Clear django-axes brute-force attempt records for this email
        try:
            from axes.models import AccessAttempt
            AccessAttempt.objects.filter(username=user.email).delete()
        except ImportError:
            pass

        create_audit_event(
            "ACCOUNT_UNLOCKED", request.user,
            metadata={"target_user": user.email},
        )
        return Response({"detail": "Account unlocked."})


class RoleRequestListView(generics.ListAPIView):
    """
    Student and Adviser role requests are reviewed by RDCO. This said "Django
    Admin only (is_staff=True)", which under the accounts/0005 seeding meant all
    four offices -- the comment described an intent the code did not have (IR-165).
    Staff accounts (RDCO, KTTO, ITSO, IERC) are managed directly by Admin via the admin panel.
    """
    serializer_class   = RoleRequestSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset           = RoleRequest.objects.filter(status="pending").select_related("user", "requested_role")


class RoleRequestDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        role_request = RoleRequest.objects.get(pk=pk)
        action = request.data.get("action")  # "approve" or "decline"
        if action == "approve":
            approve_role_request(role_request, reviewed_by=request.user)
        elif action == "decline":
            decline_role_request(role_request, reviewed_by=request.user)
        return Response(RoleRequestSerializer(role_request).data)


# ---- Reference data views -----------------------------------------------

class CollegeListView(generics.ListAPIView):
    """Public — needed on the signup page before the user has a token."""
    serializer_class   = CollegeSerializer
    permission_classes = [AllowAny]
    pagination_class   = LargeResultsPagination
    queryset           = College.objects.all()


class DepartmentListView(generics.ListAPIView):
    """Public — needed on the signup page before the user has a token."""
    serializer_class   = DepartmentSerializer
    permission_classes = [AllowAny]
    pagination_class   = LargeResultsPagination

    def get_queryset(self):
        qs = Department.objects.select_related("college")
        college_id = self.request.query_params.get("college")
        if college_id:
            qs = qs.filter(college_id=college_id)
        return qs


class CourseListView(generics.ListAPIView):
    """Public — needed on the signup page before the user has a token."""
    serializer_class   = CourseSerializer
    permission_classes = [AllowAny]
    pagination_class   = LargeResultsPagination

    def get_queryset(self):
        qs = Course.objects.select_related("department")
        dept_id = self.request.query_params.get("department")
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        return qs


class ActiveSessionsView(APIView):
    """
    GET /users/sessions/
    Returns all non-expired, non-blacklisted JWT tokens — i.e. every session
    that could still be used to authenticate.  Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from django.utils import timezone

        sessions = (
            OutstandingToken.objects
            .filter(
                expires_at__gt=timezone.now(),
                blacklistedtoken__isnull=True,       # not yet revoked
            )
            .select_related("user")
            .order_by("-created_at")
        )

        data = [
            {
                "jti":        s.jti,
                "user_id":    s.user_id,
                "user_email": s.user.email           if s.user else None,
                "user_name":  s.user.get_full_name() if s.user else None,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
            }
            for s in sessions
        ]
        return Response(data)


class RevokeSessionView(APIView):
    """
    DELETE /users/sessions/<jti>/
    Blacklists a specific JWT by its JTI (JWT ID), forcing that session to
    log out on the next request.  Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, jti):
        from rest_framework_simplejwt.token_blacklist.models import (
            OutstandingToken, BlacklistedToken,
        )
        try:
            token = OutstandingToken.objects.get(jti=jti)
        except OutstandingToken.DoesNotExist:
            return Response({"detail": "Session not found."}, status=404)

        BlacklistedToken.objects.get_or_create(token=token)
        create_audit_event(
            "SESSION_REVOKE", request.user,
            metadata={"revoked_jti": jti},
        )
        return Response({"detail": "Session revoked."})


class SystemSettingView(APIView):
    """GET or PATCH a single setting by key."""
    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated()]

    def get(self, request, key):
        setting = SystemSetting.objects.filter(key=key).first()
        if not setting:
            return Response({"detail": "Not found."}, status=404)
        return Response(SystemSettingSerializer(setting).data)

    def patch(self, request, key):
        setting, _ = SystemSetting.objects.get_or_create(key=key)
        setting.value      = request.data.get("value", setting.value)
        setting.updated_by = request.user
        setting.save()
        return Response(SystemSettingSerializer(setting).data)
