from rest_framework import serializers
from .models import User, College, Department, Course, RoleRequest, SystemSetting


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model  = User
        fields = [
            "id", "email", "first_name", "middle_initial", "last_name",
            "role", "role_name",
            "is_staff", "is_superuser",
            "is_verified", "is_locked", "date_joined",
        ]
        read_only_fields = ["role", "is_staff", "is_superuser", "is_verified", "is_locked", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

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
            "role_name", "course_id", "college_id", "department_id",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email address is already registered.")
        return value

    def validate(self, data):
        if data["password"] != data.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        role_name = data.get("role_name")
        if role_name == "Student" and not data.get("course_id"):
            raise serializers.ValidationError({"course_id": "Course is required for students."})
        if role_name == "Faculty Adviser":
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
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        # Create role-specific profile rows immediately so data is not lost
        if role_name == "Student" and course_id:
            from .models import StudentProfile
            StudentProfile.objects.create(user=user, course_id=course_id)
        elif role_name == "Faculty Adviser":
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
