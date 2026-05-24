from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from core.permissions import IsAdmin
from core.pagination import LargeResultsPagination
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
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_verified:
            return Response({"detail": "Email not verified."}, status=status.HTTP_403_FORBIDDEN)
        if user.is_locked:
            return Response({"detail": "Account is locked."}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        # TODO: create AuditEvent(LOGIN)
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
            # TODO: create AuditEvent(LOGOUT)
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
        # TODO: create Notification informing the user of their new role
        # TODO: create AuditEvent for role change
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
        action = "locked" if user.is_locked else "unlocked"
        # TODO: create AuditEvent for account lock/unlock
        return Response({"detail": f"Account {action}.", "is_locked": user.is_locked})


class LockedUsersView(generics.ListAPIView):
    """Lists accounts locked by django-axes."""
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        # TODO: query axes AccessAttempt to find locked usernames, return matching User objects
        return User.objects.filter(is_locked=True)


class UnlockUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        user = User.objects.get(pk=pk)
        user.is_locked = False
        user.save(update_fields=["is_locked"])
        # TODO: reset axes AccessAttempt for this username
        return Response({"detail": "Account unlocked."})


class RoleRequestListView(generics.ListAPIView):
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
