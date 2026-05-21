from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class Role(models.Model):
    """
    Roles: Student, Adviser, KTTO, RDCO, ITSO, TBI.
    Seed via a data migration -- do not let users create roles freely.
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class College(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.code


class Department(models.Model):
    name    = models.CharField(max_length=200)
    code    = models.CharField(max_length=20, unique=True)
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name="departments")

    def __str__(self):
        return self.code


class Course(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="courses")

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user  = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model.
    username holds the student / employee ID number.
    """
    username    = models.CharField(max_length=50, unique=True)
    first_name  = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name   = models.CharField(max_length=100)
    email       = models.EmailField(unique=True)
    contact_no  = models.CharField(max_length=20, blank=True)
    role        = models.ForeignKey(
        Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="users"
    )

    is_verified = models.BooleanField(default=False)
    is_locked   = models.BooleanField(default=False)   # manual lock, separate from axes
    is_staff    = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD  = "username"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    def __str__(self):
        return f"{self.username} ({self.get_full_name()})"

    def get_full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)


class StudentProfile(models.Model):
    """Extended info for Student role users."""
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, related_name="students")

    def __str__(self):
        return f"Student: {self.user.username}"


class AdviserProfile(models.Model):
    """Extended info for Adviser role users."""
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="adviser_profile")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name="advisers")
    college    = models.ForeignKey(College, on_delete=models.SET_NULL, null=True, related_name="advisers")

    def __str__(self):
        return f"Adviser: {self.user.username}"


class RoleRequest(models.Model):
    """
    Created at signup when a user requests Student or Adviser role.
    An admin approves or declines.
    """
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("declined", "Declined"),
    ]
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_requests")
    requested_role = models.ForeignKey(Role, on_delete=models.CASCADE)
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    reviewed_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_role_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} -> {self.requested_role.name} ({self.status})"


class SystemSetting(models.Model):
    """
    Admin-configurable key/value pairs (e.g. landing page content, announcements).
    TODO: add a RichTextField (via a lightweight package) for HTML values if needed.
    """
    key        = models.CharField(max_length=100, unique=True)
    value      = models.TextField(blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key
