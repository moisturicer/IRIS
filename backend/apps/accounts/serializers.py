from rest_framework import serializers
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
            "is_verified", "is_locked", "consent_given", "date_joined",
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
        read_only_fields = [
            "email", "role", "is_staff", "is_superuser",
            "is_verified", "is_locked", "consent_given", "date_joined",
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


class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True, min_length=8)
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

        role_name = data.get("role_name")
        if role_name == "Student" and not data.get("course_id"):
            raise serializers.ValidationError({"course_id": "Course is required for students."})
        if role_name == "Adviser":
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
        if role_name == "Student" and course_id:
            from .models import StudentProfile
            StudentProfile.objects.create(user=user, course_id=course_id)
        elif role_name == "Adviser":
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
    new_password = serializers.CharField(min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


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
