from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import generics, status
from django.utils.cache import add_never_cache_headers
from rest_framework.throttling import UserRateThrottle
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.enums import RequestStatus, RoleName, SessionEndReason
from rest_framework_simplejwt.tokens import RefreshToken
from core.permissions import (
    IsAccountAdmin,
    IsAdmin,
    IsSystemAdmin,
    is_system_admin,
    role_change_refusal,
)
from core.pagination import LargeResultsPagination
from apps.audit.services import create_audit_event
from apps.audit import retention
from apps.audit.models import AuditEvent
from . import profile, public_profile
from .models import User, College, Department, Course, RoleRequest, SystemSetting
from .serializers import (
    UserSerializer, AdviserOptionSerializer, MeSerializer, PhotoUploadSerializer, RegisterSerializer, ChangePasswordSerializer,
    CollegeSerializer, DepartmentSerializer, CourseSerializer,
    RoleRequestSerializer, SystemSettingSerializer, NoticeAnswerSerializer,
)
from .models import DataNotice
from .notice import answer_notice, answer_payload, notice_payload, requires_answer
from .models import RecoveryPurpose
from .recovery import service as recovery_service
from .recovery.views import INVALID_LINK
from .services import approve_role_request, decline_role_request

#: RDCO's account acts leave a System Admin's account alone (ADR-051 §5).
LEAVE_SYSTEM_ADMIN_ALONE = "A System Admin's account is managed only in Django's admin site."


def _refused(detail):
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _refuse_system_admin(user):
    """A 403 when `user` is a System Admin, whose account no API act touches; else None."""
    return _refused(LEAVE_SYSTEM_ADMIN_ALONE) if is_system_admin(user) else None
from .credentials import set_password_and_invalidate
from .sessions import (
    end_all_sessions, end_session, start_session, require_eligible_account, refuse_if_ended,
    revoke_token,
)
from .lockout import LOCKED_BY_ADMIN
from .throttles import LoginThrottle, PersonalDataExportThrottle, RegisterThrottle
from .personal_data import EXPORT_FORMAT, SECTIONS, build_export


class RegisterView(generics.CreateAPIView):
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [RegisterThrottle]

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

            # The verification email goes the resend's way (ADR-045 §6, IR-643):
            # an intent committed with the account, mailed by a worker after
            # commit, under the same limits. A rollback leaves no intent and
            # sends nothing.
            recovery_service.admit_request(RecoveryPurpose.EMAIL_VERIFICATION, user.email)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @transaction.atomic
    def post(self, request):
        from django.contrib.auth import authenticate
        email    = request.data.get("email")
        password = request.data.get("password")
        # The Django request, not DRF's wrapper: axes marks a lockout by setting
        # `axes_locked_out` on the request it is given, and its middleware reads
        # it from the Django one. Through the wrapper the mark was lost, so a
        # locked account was told "Invalid credentials." even with the right
        # password, and no 429 was ever sent (IR-555).
        user = authenticate(request._request, username=email, password=password)
        if user:
            # A password change or account lock may have committed since
            # authenticate read the credentials. Serialize that check and
            # token issuance with those actions on the account row.
            verified_hash = user.password
            user = User.objects.select_for_update().get(pk=user.pk)
            if user.password != verified_hash or not user.is_active:
                user = None
        if not user:
            create_audit_event("FAILED_LOGIN", None, metadata={"email": email})
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_verified:
            return Response({"detail": "Email not verified."}, status=status.HTTP_403_FORBIDDEN)
        if user.is_locked:
            # RDCO's lock: it lifts only when RDCO unlocks, so no `unlock_at` (IR-555).
            return Response(
                {"detail": "Account is locked.", "code": LOCKED_BY_ADMIN},
                status=status.HTTP_403_FORBIDDEN,
            )

        # A session the inactivity rule can end, its id inside both tokens (IR-166),
        # minted under the account's row lock (ADR-045 §4). A reset holds the
        # same lock, so this either finishes before it -- and the reset ends
        # this session -- or runs after it and sees the password hash this
        # request did not check, and refuses. It can never pair the old
        # password with the new credential version.
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=user.pk)
            if locked.password != user.password:
                return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
            refresh = start_session(locked)
        create_audit_event("LOGIN", user, metadata={"email": user.email})
        return Response({
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
            # The signed-in user's own payload, `review_access` included, so
            # the landing after sign-in needs no second request (IR-415).
            "user":    MeSerializer(user).data,
            # ADR-054 (IR-789): true means every other request will be refused
            # with `notice_acceptance_required` until the person answers, so the
            # client shows the notice instead of loading the app.
            "notice_answer_required": requires_answer(user),
        })


class CurrentNoticeView(APIView):
    """
    GET /auth/notice/
    The current data notice (ADR-054, IR-789). Public, because registration
    shows it before there is an account. A signed-in caller also gets `answer`
    (their last answer, or null) and `answer_required`, which is what the
    frontend reads to decide whether to show the pop-up. Reachable while the
    notice is unanswered: it is what the person must read.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        notice = DataNotice.current()
        if notice is None:
            return Response({"detail": "No data notice has been published."}, status=status.HTTP_404_NOT_FOUND)
        data = notice_payload(notice)
        user = request.user
        if user and user.is_authenticated:
            data["answer"] = answer_payload(user)
            data["answer_required"] = requires_answer(user)
        return Response(data)


class AnswerNoticeView(APIView):
    """
    POST /auth/notice/answer/   {notice_version, agree_dpa, ai_consent}
    Answer the current notice (ADR-054 decisions 1-4). Everyone answers, office
    staff and the System Admin included. 409 `notice_stale` with the current
    notice when `notice_version` is not it. Saying No to AI is a complete answer.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = NoticeAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        answer_notice(request.user, notice_version=data["notice_version"], ai_consent=data["ai_consent"])
        return Response(
            {"answer": answer_payload(request.user), "answer_required": requires_answer(request.user)},
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Ended through the access token in hand, which is the one this request
        # was authenticated with; the refresh token in the body may be stale.
        sid = request.auth.get("sid") if request.auth else None
        if sid:
            end_session(sid, SessionEndReason.LOGOUT)
        try:
            token = RefreshToken(request.data["refresh"])
            token.blacklist()
            create_audit_event("LOGOUT", request.user, metadata={"email": request.user.email})
        except Exception:
            pass
        return Response({"detail": "Logged out."})


class ActivateView(APIView):
    """
    RETIRED (IR-643, ADR-045 §8): `GET /auth/activate/<uid>/<token>/`, the
    link shape emailed before IR-928. Verification links are single-use
    `RecoveryToken`s now, so this verifies no one: it gives the recovery
    contract's one "invalid link" answer, which points to a new email, and
    changes nothing. No Django default-generator token is accepted anywhere.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, uidb64, token):
        response = Response(INVALID_LINK, status=status.HTTP_400_BAD_REQUEST)
        response["Cache-Control"] = "no-store"
        return response


class ActivateConfirmView(APIView):
    """
    RETIRED (IR-643, ADR-045 §8): `POST /auth/activate/`, IR-928's body form
    of the same old link. Kept answering, rather than removed, so a page
    cached from before the change shows "request a new email" instead of a
    404. Reads nothing it is sent and changes nothing.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        response = Response(INVALID_LINK, status=status.HTTP_400_BAD_REQUEST)
        response["Cache-Control"] = "no-store"
        return response


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # The same invalidation as a reset (ADR-045 §4): every session ends,
        # this one included, and so does any outstanding reset link.
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            require_eligible_account(user)
            if user.credential_version != request.user.credential_version:
                from .authentication import CredentialsChanged
                raise CredentialsChanged()
            sid = request.auth.get("sid") if request.auth else None
            if sid:
                refuse_if_ended(sid)
            request.user = user
            serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            set_password_and_invalidate(user, serializer.validated_data["new_password"], timezone.now())
            create_audit_event(AuditEvent.PASSWORD_CHANGED, user)
        return Response({"detail": "Password changed. Sign in again with your new password.",
                         "code": SessionEndReason.PASSWORD_CHANGED})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class   = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class PersonalDataExportView(APIView):
    """One JSON file of the signed-in person's own data (ADR-051 decision 13, IR-786).

    There is no id in the address and none to guess: the data is always the
    caller's, so no role can read another person's through it (the System Admin
    and RDCO included). Each download is audited, counts against a budget of its
    own, and is never cached -- by the browser or by a proxy on the way.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle, PersonalDataExportThrottle]

    def get(self, request):
        payload = build_export(request.user)
        create_audit_event(
            AuditEvent.PERSONAL_DATA_EXPORTED,
            request.user,
            metadata={"format": EXPORT_FORMAT, "sections": sorted(SECTIONS)},
        )
        response = Response(payload)
        response["Content-Disposition"] = 'attachment; filename="iris-my-data.json"'
        add_never_cache_headers(response)
        response["Cache-Control"] = "no-store, private"
        return response


class MePhotoView(APIView):
    """
    `PUT /users/me/photo/` (multipart) and `DELETE /users/me/photo/` (IR-695).

    Both act on `request.user` and on nobody else, so there is no path or body
    that names another person's photo to change.
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser]

    def put(self, request):
        serializer = PhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile.set_photo(request.user, serializer.validated_data["photo"], serializer.crop)
        return Response({"photo_url": profile.photo_url(request.user)})

    def delete(self, request):
        profile.remove_photo(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPhotoView(APIView):
    """
    `GET /users/<id>/photo/`: a person's photo, for any signed-in user (IR-695).

    The only way to read one. The file lives under MEDIA_ROOT, which no URL
    serves, so reading it needs a valid token like every other route. A person
    with no photo, a deactivated account and an id that does not exist all
    answer the same 404.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        owner = User.objects.filter(pk=pk, is_active=True).only("id", "photo", "photo_version").first()
        if owner is None or not owner.photo:
            raise Http404
        try:
            stored = owner.photo.open("rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(stored, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        # `photo_url` carries `?v=`, which changes with the photo, so a copy
        # fetched under the current version is never stale. Private: a shared
        # cache must not keep a photo only signed-in users may read.
        current = request.query_params.get("v") == str(owner.photo_version)
        response["Cache-Control"] = "private, max-age=86400" if current else "private, no-cache"
        return response


class PublicProfileView(APIView):
    """
    `GET /users/<id>/profile/`: a person's public profile, for any signed-in
    user (IR-696).

    The person alone, with no lists: those are paged routes of their own. A
    suspended, inactive, unverified or unapproved account, a System Admin and
    a missing id all answer the same 404 (`public_profile.person_or_404`).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(public_profile.profile_payload(public_profile.person_or_404(pk)))


class PublicProfilePapersView(APIView):
    """
    A person's published papers, newest first, ten at a time (IR-696).

    Discover's visibility, so nothing unpublished is listed; each paper carries
    its view count and there are no totals. A subclass says which papers.
    """
    permission_classes = [IsAuthenticated]

    def papers(self, viewer, person):
        raise NotImplementedError

    def get(self, request, pk):
        person = public_profile.person_or_404(pk)
        rows = self.papers(request.user, person)
        return Response(public_profile.paginate(
            request, rows, public_profile.PAPERS_PAGE_SIZE, public_profile.paper_payload,
        ))


class PublicProfileResearchView(PublicProfilePapersView):
    """`GET /users/<id>/profile/research/`: the published papers the person owns."""

    def papers(self, viewer, person):
        return public_profile.research_papers(viewer, person)


class PublicProfileAdvisedView(PublicProfilePapersView):
    """`GET /users/<id>/profile/advised/`: the published papers they were the Adviser on."""

    def papers(self, viewer, person):
        return public_profile.advised_papers(viewer, person)


class PublicProfileCollaboratorsView(APIView):
    """
    `GET /users/<id>/profile/collaborators/`: other accounts that shared a
    published paper with the person, most papers shared first (IR-696).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        person = public_profile.person_or_404(pk)
        rows = public_profile.collaborators(request.user, person)
        return Response(public_profile.paginate(
            request, rows, public_profile.COLLABORATORS_PAGE_SIZE,
            lambda row: public_profile.collaborator_payload(*row),
        ))


class InterestSuggestionsView(APIView):
    """`GET /users/interests/?q=mach`: existing interests that contain `q` (IR-695)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(profile.suggest_interests(request.query_params.get("q", "")))


class UserListView(generics.ListAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAccountAdmin]
    # A deleted account leaves the Users page (ADR-051 §11, IR-785).
    queryset           = User.objects.filter(deleted_at__isnull=True).select_related("role").order_by("-date_joined")
    # The default SearchFilter matches nothing until a view names its fields,
    # so the Users page's search box listed everyone (IR-478).
    search_fields      = ["email", "first_name", "last_name"]


class AdviserListView(generics.ListAPIView):
    """
    GET /users/advisers/
    Returns all active users whose role is "Adviser".
    Used by the record creation form so students can pick their adviser.
    Any authenticated user may call this endpoint, which is why it serializes
    only the picker's fields and no account state (IR-587).
    """
    serializer_class   = AdviserOptionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = LargeResultsPagination  # advisers list is small; return them all at once

    def get_queryset(self):
        return (
            User.objects
            .filter(role__name=RoleName.ADVISER, is_active=True)
            .select_related("role")
            .order_by("last_name", "first_name")
        )


class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated, IsAccountAdmin]
    queryset           = User.objects.filter(deleted_at__isnull=True)

    def update(self, request, *args, **kwargs):
        return _refuse_system_admin(self.get_object()) or super().update(request, *args, **kwargs)


class ChangeUserRoleView(APIView):
    """
    PATCH /users/<id>/role/ -- change a user's role by name or ID.

    The System Admin gives office roles and RDCO gives Student or Adviser
    (ADR-051 §4, amended); `role_change_refusal` says who may give what.
    """
    permission_classes = [IsAuthenticated, IsAccountAdmin]

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

        refusal = role_change_refusal(request.user, user, role)
        if refusal is not None:
            return _refused(refusal)
        user.assign_role(role)

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


class OfficeCoordinatorView(APIView):
    """
    PATCH /users/<id>/coordinator/  {"is_office_coordinator": bool}

    ADR-032 §4: the System Admin grants or revokes the coordinator flag, as it
    gives office roles (ADR-051 §4, amended). A coordinator may assign, reassign
    and withdraw reviewer seats in the office their role staffs, so granting it
    to a user with no office role is refused rather than stored as a flag that
    means nothing.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def patch(self, request, pk):
        from core.permissions import office_parties_of

        user = User.objects.filter(pk=pk).select_related("role").first()
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        value = request.data.get("is_office_coordinator")
        if not isinstance(value, bool):
            return Response(
                {"detail": "`is_office_coordinator` must be true or false."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if value and not office_parties_of(user):
            return Response(
                {"detail": "Only a member of ITSO, IERC, KTTO or RDCO can coordinate an office."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_office_coordinator = value
        user.save(update_fields=["is_office_coordinator"])
        create_audit_event(
            "ROLE_CHANGE", request.user,
            metadata={"target_user": user.email, "is_office_coordinator": value},
        )
        return Response(UserSerializer(user).data)


class LockUserView(APIView):
    """PATCH /users/<id>/lock/ -- lock or unlock an account."""
    permission_classes = [IsAuthenticated, IsAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        user      = User.objects.select_for_update().get(pk=pk)
        if refused := _refuse_system_admin(user):
            return refused
        is_locked = request.data.get("is_locked")
        if is_locked is None:
            return Response({"detail": "is_locked is required."}, status=400)
        user.is_locked = bool(is_locked)
        user.save(update_fields=["is_locked"])
        if user.is_locked:
            end_all_sessions(user, SessionEndReason.LOCKED)
        event_type = "ACCOUNT_LOCKED" if user.is_locked else "ACCOUNT_UNLOCKED"

        create_audit_event(
            event_type, request.user,
            metadata={"target_user": user.email},
        )

        detail     = "Account locked." if user.is_locked else "Account unlocked."
        return Response({"detail": detail, "is_locked": user.is_locked})


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

        return User.objects.filter(q, deleted_at__isnull=True).select_related("role").distinct()


class UnlockUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        user = User.objects.get(pk=pk)
        if refused := _refuse_system_admin(user):
            return refused
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
    queryset           = RoleRequest.objects.filter(status=RequestStatus.PENDING).select_related("user", "requested_role")


class RoleRequestDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        role_request = RoleRequest.objects.get(pk=pk)
        if refused := _refuse_system_admin(role_request.user):
            return refused
        action = request.data.get("action")  # "approve" or "decline"
        if action == "approve":
            # Approving gives the role, so it follows the same rule as giving one:
            # RDCO gives Student or Adviser only (ADR-051 §4, amended).
            refusal = role_change_refusal(request.user, role_request.user, role_request.requested_role)
            if refusal is not None:
                return _refused(refusal)
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
    Ends the session of a specific JWT, found by its JTI (JWT ID), so its access
    and refresh tokens are both refused on their next use.  Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, jti):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        try:
            token = OutstandingToken.objects.get(jti=jti)
        except OutstandingToken.DoesNotExist:
            return Response({"detail": "Session not found."}, status=404)
        if refused := _refuse_system_admin(token.user):
            return refused

        revoke_token(token)
        create_audit_event(
            "SESSION_REVOKE", request.user,
            metadata={"revoked_jti": jti, "user_id": token.user_id},
        )
        return Response({"detail": "Session revoked."})


class SystemSettingView(APIView):
    """
    GET or PATCH a single setting by key. The System Admin alone (IR-667,
    ADR-051 §3).

    A PATCH changes an existing key and never creates one, and a change is
    audited with its old and new value. Settings hold no secrets, so neither
    value is masked.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request, key):
        setting = SystemSetting.objects.filter(key=key).first()
        if not setting:
            return Response({"detail": "Not found."}, status=404)
        return Response(SystemSettingSerializer(setting).data)

    def patch(self, request, key):
        value = request.data.get("value")
        if not isinstance(value, str):
            return Response({"value": ["A text value is required."]}, status=400)
        # A retention period is whole days, or blank to erase nothing (IR-794).
        if key in retention.setting_keys() and (error := retention.period_error(value)):
            return Response({"value": [error]}, status=400)
        with transaction.atomic():
            setting = SystemSetting.objects.select_for_update().filter(key=key).first()
            if not setting:
                return Response({"detail": "Not found."}, status=404)
            if setting.value != value:
                create_audit_event(
                    AuditEvent.SYSTEM_SETTING_CHANGED, request.user,
                    metadata={"key": key, "old_value": setting.value, "new_value": value},
                )
                setting.value      = value
                setting.updated_by = request.user
                setting.save()
        return Response(SystemSettingSerializer(setting).data)


# ---- Account deletion (ADR-051 §8-§12, IR-785) ----------------------------

def _deletion_refused(refused):
    body = {"detail": refused.detail}
    if refused.blockers:
        body["blockers"] = [b.as_dict() for b in refused.blockers]
    return Response(body, status=refused.status)


class MyDeletionRequestView(APIView):
    """
    GET    /users/me/deletion-request/  the caller's latest request, or null
    POST   /users/me/deletion-request/  ask for the caller's account to be deleted
    DELETE /users/me/deletion-request/  cancel the pending one

    Only ever the caller's own account, so there is no object to look up.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import AccountDeletionRequest
        from .serializers import MyDeletionRequestSerializer

        latest = AccountDeletionRequest.objects.filter(user=request.user).order_by("-created_at", "-pk").first()
        return Response({"request": MyDeletionRequestSerializer(latest).data if latest else None})

    def post(self, request):
        from .deletion import service
        from .serializers import MyDeletionRequestSerializer

        try:
            made = service.request_deletion(request.user)
        except service.Refused as refused:
            return _deletion_refused(refused)
        return Response({"request": MyDeletionRequestSerializer(made).data}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        from .deletion import service
        from .serializers import MyDeletionRequestSerializer

        try:
            cancelled = service.cancel_deletion(request.user)
        except service.Refused as refused:
            return _deletion_refused(refused)
        return Response({"request": MyDeletionRequestSerializer(cancelled).data})


class AccountDeletionRequestListView(generics.ListAPIView):
    """GET /users/deletion-requests/ -- pending requests, each with its blockers. System Admin only."""
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    pagination_class   = LargeResultsPagination

    def get_serializer_class(self):
        from .serializers import AccountDeletionRequestSerializer
        return AccountDeletionRequestSerializer

    def get_queryset(self):
        from .models import AccountDeletionRequest
        return (
            AccountDeletionRequest.objects.filter(status=RequestStatus.PENDING)
            .select_related("user", "user__role").order_by("created_at", "pk")
        )


class AccountDeletionDecisionView(APIView):
    """
    POST /users/deletion-requests/<id>/confirm/
    POST /users/deletion-requests/<id>/reject/  {"reason": "..."}

    System Admin only, never on their own request. A request no longer pending
    gets 409, and confirmation is refused with its blockers while any remain.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    action = None

    def post(self, request, pk):
        from .deletion import service
        from .serializers import AccountDeletionRequestSerializer

        try:
            if self.action == "confirm":
                decided = service.confirm_deletion(pk, request.user)
            else:
                decided = service.reject_deletion(pk, request.user, request.data.get("reason"))
        except service.Refused as refused:
            return _deletion_refused(refused)
        return Response(AccountDeletionRequestSerializer(decided, context={"request": request}).data)
