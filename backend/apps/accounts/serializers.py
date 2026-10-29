from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from core.enums import RequestStatus, RoleName
from .models import User, College, Department, Course, RoleRequest, SystemSetting


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)

    # Affiliation, read-only. A student's college is not stored on the student --
    # it is derived through StudentProfile.course -> Department -> College, while
    # an adviser carries college and department directly. Exposed for display on
    # the profile screen; changing an affiliation is an administrative act, not a
    # self-service one, so there is deliberately no write path here.
    college_name    = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    course_name     = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            "id", "email", "first_name", "middle_initial", "last_name",
            "role", "role_name",
            "is_staff", "is_superuser",
            "is_verified", "is_locked", "is_active", "consent_given", "date_joined",
            "is_office_coordinator",
            "college_name", "department_name", "course_name",
        ]
        # `email` is read-only, and that is a security boundary rather than a
        # nicety. It is USERNAME_FIELD -- the login identifier -- and the whole
        # system leans on institutional identity for authorship, clearance
        # attribution and citations. This endpoint (MeView) is a
        # RetrieveUpdateAPIView open to any authenticated user, so while `email`
        # was writable a student could PATCH their own address to any external
        # mailbox and keep `is_verified: True`, moving the account off CIT-U
        # identity entirely. Verified reproducible before the fix.
        # `is_office_coordinator` is read-only for the same reason as `role`:
        # coordinators assign other people's reviews (ADR-032 §4), so the grant
        # is an administrator's, through `PATCH /users/<id>/coordinator/`.
        read_only_fields = [
            "email", "role", "is_staff", "is_superuser",
            "is_verified", "is_locked", "is_active", "consent_given", "date_joined",
            "is_office_coordinator",
        ]

    def _profile_college(self, obj):
        adviser = getattr(obj, "adviser_profile", None)
        if adviser and adviser.college:
            return adviser.college
        student = getattr(obj, "student_profile", None)
        if student and student.course and student.course.department:
            return student.course.department.college
        return None

    def get_college_name(self, obj):
        college = self._profile_college(obj)
        return college.name if college else ""

    def get_department_name(self, obj):
        adviser = getattr(obj, "adviser_profile", None)
        if adviser and adviser.department:
            return adviser.department.name
        student = getattr(obj, "student_profile", None)
        if student and student.course and student.course.department:
            return student.course.department.name
        return ""

    def get_course_name(self, obj):
        student = getattr(obj, "student_profile", None)
        return student.course.name if student and student.course else ""


class AdviserOptionSerializer(UserSerializer):
    """
    One row of `GET /users/advisers/`, the adviser picker every signed-in user
    can read (IR-587).

    Exactly what the IR-540 data notice tells registrants an approved Adviser
    shows to signed-in users: name, email, college and department. The account
    state `UserSerializer` carries for RDCO -- `is_locked`, `is_verified`,
    `is_staff`, `date_joined` and the rest -- has no reason to reach a student.
    `college_name` has no reader in the picker today; it stays so the notice is
    exact and two advisers with one name can be told apart.
    """

    class Meta(UserSerializer.Meta):
        fields = [
            "id", "first_name", "middle_initial", "last_name", "email",
            "college_name", "department_name",
        ]
        read_only_fields = fields


class MeSerializer(UserSerializer):
    """
    `GET /users/me/`: the signed-in user, plus what only they may read about
    themselves.

    `review_access` (spec Appendix D · B3, IR-415) says whether the user has
    review work: My Reviews' sidebar entry, its route guard and the landing
    after sign-in all read it. It is never on another user's payload -- the
    adviser picker uses `AdviserOptionSerializer` and the admin list
    `UserSerializer` -- so nobody learns
    who else reviews what.

    `role_request` (IR-537) is the user's latest role request while they have
    no role, so the pending screen can tell an applicant still waiting from
    one RDCO declined: `{status: "pending" | "declined", requested_role}`, or
    `None` once a role is held or when nothing was asked for. Computed, so it
    is read-only and needs no migration.
    """
    review_access = serializers.SerializerMethodField()
    role_request  = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "review_access", "role_request"]

    def get_review_access(self, obj):
        from apps.reviews.seats import review_access

        return review_access(obj)

    def get_role_request(self, obj):
        if obj.role_id is not None:
            return None
        latest = (
            obj.role_requests.select_related("requested_role")
            .order_by("-created_at", "-id")
            .first()
        )
        # An approved request with no role means the role was later taken
        # away: there is no decision pending, and "declined" would be false.
        if latest is None or latest.status == RequestStatus.APPROVED:
            return None
        return {"status": latest.status, "requested_role": latest.requested_role.name}


def enforce_password_policy(password, user, field):
    """Refuse ``password`` unless it passes `AUTH_PASSWORD_VALIDATORS` (IR-647).

    The settings are the one definition of the policy; this is how the API
    applies it. Every validator's message is reported on ``field`` together,
    so the person can fix them all in one try.
    """
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({field: list(exc.messages)})


class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    consent_given    = serializers.BooleanField(write_only=True)

    # Role-selection fields (not model fields — popped before user creation)
    role_name     = serializers.CharField(write_only=True, required=False, allow_blank=True)
    course_id     = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    college_id    = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    department_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model  = User
        fields = [
            "email", "first_name", "middle_initial", "last_name",
            "password", "confirm_password",
            "consent_given",
            "role_name", "course_id", "college_id", "department_id",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email address is already registered.")
        return value

    def validate_consent_given(self, value):
        if not value:
            raise serializers.ValidationError("You must agree to the Data Privacy Notice to register.")
        return value

    def validate(self, data):
        if data["password"] != data.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        # An unsaved user, so validators that compare against the person's own
        # name or email have something to compare with.
        candidate = User(
            email=data.get("email", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        enforce_password_policy(data["password"], candidate, "password")

        role_name = data.get("role_name")
        if role_name == RoleName.STUDENT and not data.get("course_id"):
            raise serializers.ValidationError({"course_id": "Course is required for students."})
        if role_name == RoleName.ADVISER:
            if not data.get("college_id"):
                raise serializers.ValidationError({"college_id": "College is required for advisers."})
            if not data.get("department_id"):
                raise serializers.ValidationError({"department_id": "Department is required for advisers."})

        return data

    def create(self, validated_data):
        # Pop non-model / profile fields before creating the User row
        role_name     = validated_data.pop("role_name",     None)
        course_id     = validated_data.pop("course_id",     None)
        college_id    = validated_data.pop("college_id",    None)
        department_id = validated_data.pop("department_id", None)

        password = validated_data.pop("password")
        user = User(**validated_data)   # consent_given stays in validated_data → persisted to model
        user.set_password(password)
        user.save()

        # Create role-specific profile rows immediately so data is not lost
        if role_name == RoleName.STUDENT and course_id:
            from .models import StudentProfile
            StudentProfile.objects.create(user=user, course_id=course_id)
        elif role_name == RoleName.ADVISER:
            from .models import AdviserProfile
            AdviserProfile.objects.create(
                user=user,
                college_id=college_id,
                department_id=department_id,
            )

        # Stash for the view's perform_create to pick up
        self._role_name = role_name
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        enforce_password_policy(attrs["new_password"], self.context["request"].user, "new_password")
        return attrs


class CollegeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = College
        fields = ["id", "name", "code"]


class DepartmentSerializer(serializers.ModelSerializer):
    college_name = serializers.CharField(source="college.name", read_only=True)

    class Meta:
        model  = Department
        fields = ["id", "name", "code", "college", "college_name"]


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Course
        fields = ["id", "name", "department"]


class RoleRequestSerializer(serializers.ModelSerializer):
    user_name      = serializers.CharField(source="user.get_full_name", read_only=True)
    role_name      = serializers.CharField(source="requested_role.name", read_only=True)

    class Meta:
        model  = RoleRequest
        fields = ["id", "user", "user_name", "requested_role", "role_name", "status", "created_at"]
        read_only_fields = ["status", "reviewed_by", "reviewed_at"]


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SystemSetting
        fields = ["key", "value", "updated_by", "updated_at"]
        read_only_fields = ["updated_by", "updated_at"]
