import unicodedata

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from core.enums import RequestStatus, RoleName
from . import profile
from .models import User, College, Department, Course, RoleRequest, SystemSetting
from .notice import answer_notice, require_current


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

    def get_college_name(self, obj):
        return profile.affiliation(obj).college

    def get_department_name(self, obj):
        return profile.affiliation(obj).department

    def get_course_name(self, obj):
        return profile.affiliation(obj).course


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


class ResearchInterestsField(serializers.ListField):
    """
    The tags on a profile, as a list of strings (IR-695).

    Read as the person's own tags in the order they gave them. Written as a
    whole list: it is tidied and checked by `profile.clean_interests`, and the
    spelling of an existing tag wins over the one typed (that happens when it
    is stored, in `profile.set_interests`).
    """
    child = serializers.CharField(allow_blank=True, trim_whitespace=False)

    def get_attribute(self, instance):
        return profile.interest_names(instance)

    def to_internal_value(self, data):
        return profile.clean_interests(super().to_internal_value(data))


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

    # The person's own optional profile (IR-695). Editable here and nowhere
    # else, so "only the person edits their own fields" holds by construction:
    # `/users/me/` acts on the signed-in user, and `UserSerializer`, which the
    # administrators' endpoints use, does not carry them. The photo is not a
    # field you PATCH: it is uploaded to `/users/me/photo/`, read as `photo_url`.
    bio = serializers.CharField(
        max_length=profile.BIO_MAX_LENGTH, allow_blank=True, required=False,
        error_messages={"max_length": profile.BIO_TOO_LONG},
    )
    research_interests = ResearchInterestsField(required=False)
    photo_url = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = [
            *UserSerializer.Meta.fields, "review_access", "role_request",
            "bio", "research_interests", "photo_url",
        ]

    def get_photo_url(self, obj):
        return profile.photo_url(obj)

    def update(self, instance, validated_data):
        interests = validated_data.pop("research_interests", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if interests is not None:
                profile.set_interests(instance, interests)
        return instance

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


class RegistrationNameField(serializers.CharField):
    """Trim only the edges; keep the spelling and spacing a person supplied."""

    def __init__(self, label):
        super().__init__(max_length=100, error_messages={
            "required": f"{label} is required.",
            "blank": f"{label} is required.",
            "null": f"{label} is required.",
            "invalid": f"{label} must be text.",
            "max_length": f"{label} must be 100 characters or fewer.",
        })
        self.name_label = label

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        value = super().to_internal_value(data)
        categories = [unicodedata.category(char)[0] for char in value]
        if "L" not in categories or any(
            category not in {"L", "M"} and char not in " '’‐‑-"
            for char, category in zip(value, categories)
        ):
            raise serializers.ValidationError(
                f"{self.name_label} must contain letters and may include spaces, apostrophes or hyphens."
            )
        return value


class NoDefaultBoolean(serializers.BooleanField):
    """A required Yes or No that is never filled in for the person.

    DRF reads a *missing* value in form-encoded input as False, which for a
    consent answer would turn "didn't answer" into "No". Declaring it empty
    makes `required=True` hold for every encoding.
    """

    default_empty_html = serializers.empty

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)


class RegisterSerializer(serializers.ModelSerializer):
    first_name = RegistrationNameField("First name")
    last_name = RegistrationNameField("Last name")
    password         = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    # ADR-054 decisions 1-3 (IR-789), replacing the single `consent_given`
    # box: agreeing to the data-privacy agreement is what having an account
    # requires; the Yes or No on AI is its own required answer, with no default
    # on either side (`NoDefaultBoolean`), and No still gives a normal account.
    # `notice_version` is the version the person was shown.
    agree_dpa        = NoDefaultBoolean(write_only=True)
    ai_consent       = NoDefaultBoolean(write_only=True)
    notice_version   = serializers.IntegerField(write_only=True, min_value=1)

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
            "agree_dpa", "ai_consent", "notice_version",
            "role_name", "course_id", "college_id", "department_id",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email address is already registered.")
        return value

    def validate_agree_dpa(self, value):
        if not value:
            raise serializers.ValidationError("You must agree to the data-privacy agreement to register.")
        return value

    def validate_notice_version(self, value):
        # A newer notice published since the form loaded: refuse with it (409),
        # so the person reads it before agreeing to anything.
        require_current(value)
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
        # Sign-up asks only for an author's role. Office accounts are the System
        # Admin's to make, and the System Admin role is given in Django's admin
        # site (ADR-051 §4-5, amended).
        if role_name and role_name not in (RoleName.STUDENT, RoleName.ADVISER):
            raise serializers.ValidationError({"role_name": "Sign up as a Student or an Adviser."})
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
        validated_data.pop("agree_dpa")
        ai_consent     = validated_data.pop("ai_consent")
        notice_version = validated_data.pop("notice_version")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        # The first answer, in the same transaction as the account (the view's).
        answer_notice(user, notice_version=notice_version, ai_consent=ai_consent)

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


class PhotoUploadSerializer(serializers.Serializer):
    """`PUT /users/me/photo/`: the file, and optionally the square to keep (IR-695)."""

    photo = serializers.FileField(
        allow_empty_file=False,
        error_messages={key: profile.NOT_AN_IMAGE for key in ("required", "invalid", "empty", "no_name")},
    )
    #: Pixels of the image as the person sees it, from its top-left corner.
    #: A negative or zero value is a square that is not inside the image, so it
    #: says what the contract says for one that runs past the edge.
    crop_x    = serializers.IntegerField(required=False, min_value=0,
                                         error_messages={"min_value": profile.CROP_OUTSIDE})
    crop_y    = serializers.IntegerField(required=False, min_value=0,
                                         error_messages={"min_value": profile.CROP_OUTSIDE})
    crop_size = serializers.IntegerField(required=False, min_value=1,
                                         error_messages={"min_value": profile.CROP_OUTSIDE})

    CROP_FIELDS = ("crop_x", "crop_y", "crop_size")

    def validate(self, attrs):
        given = [name for name in self.CROP_FIELDS if name in attrs]
        if given and len(given) != len(self.CROP_FIELDS):
            raise serializers.ValidationError({
                name: [profile.CROP_INCOMPLETE] for name in self.CROP_FIELDS if name not in attrs
            })
        return attrs

    @property
    def crop(self):
        """`(x, y, side)`, or None when the person sent none."""
        data = self.validated_data
        if "crop_size" not in data:
            return None
        return data["crop_x"], data["crop_y"], data["crop_size"]


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


class NoticeAnswerSerializer(serializers.Serializer):
    """The body of ``POST /auth/notice/answer/`` (ADR-054, IR-789).

    Both answers are required with no default: agreeing to the data-privacy
    agreement (which having an account requires, so it must be true) and a
    Yes or No on AI. `notice_version` is the version the person was shown; a
    stale one is refused with the current notice by `require_current`, which
    runs again under the lock in `answer_notice`.
    """

    notice_version = serializers.IntegerField(min_value=1)
    agree_dpa      = NoDefaultBoolean()
    ai_consent     = NoDefaultBoolean()

    def validate_agree_dpa(self, value):
        if not value:
            raise serializers.ValidationError("You must agree to the data-privacy agreement to use IRIS.")
        return value

    # Which papers a No-to-Yes answer covers (ADR-054 decision 13): neither is
    # assumed, so it is optional here and required by `ai_answer` for that one
    # change.
    papers         = serializers.ChoiceField(choices=("all", "from_now"), required=False)

    def validate_notice_version(self, value):
        require_current(value)
        return value


class AiAnswerChangeSerializer(serializers.Serializer):
    """The body of ``POST /users/me/ai-answer/`` (ADR-054 decisions 11-13, IR-791).

    The new answer is required with no default, so nothing is ever changed by
    omission. `papers` is optional here because only a No becoming a Yes asks
    about papers; `apps.accounts.ai_answer` refuses that change without it, and
    ignores it for every other.
    """

    ai_consent = NoDefaultBoolean()
    papers     = serializers.ChoiceField(choices=("all", "from_now"), required=False)
