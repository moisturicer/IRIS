import uuid

from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

from core.enums import RequestStatus, SessionEndReason


class Role(models.Model):
    """
    Roles: Student, Adviser, KTTO, RDCO, ITSO, IERC.
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
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model. Email is the login identifier.
    """
    email          = models.EmailField(unique=True)
    first_name     = models.CharField(max_length=100)
    middle_initial = models.CharField(max_length=20, blank=True)
    last_name      = models.CharField(max_length=100)
    role           = models.ForeignKey(
        Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="users"
    )

    is_verified    = models.BooleanField(default=False)
    is_locked      = models.BooleanField(default=False)   # manual lock, separate from axes
    is_staff       = models.BooleanField(default=False)
    is_active      = models.BooleanField(default=True)
    date_joined    = models.DateTimeField(auto_now_add=True)
    consent_given  = models.BooleanField(default=False)   # FR-M6-06: Data Privacy Act (RA 10173) consent recorded at signup
    #: ADR-032 §4: may assign, reassign and withdraw reviewer seats in the
    #: office their role staffs, and nowhere else. Granted by an administrator
    #: (`PATCH /users/<id>/coordinator/`), never by the user. Meaningless
    #: without an office role: `core.permissions.is_office_coordinator` asks both.
    is_office_coordinator = models.BooleanField(default=False)
    #: ADR-045 §4 (IR-642): every access and refresh token carries this as its
    #: `cv` claim, and authentication refuses one that does not match. A
    #: password change or reset increments it, which is what ends every
    #: sign-in on every device at once. Change it only through
    #: `apps.accounts.credentials.invalidate_credentials`.
    credential_version = models.PositiveIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def save(self, *args, **kwargs):
        # Admin edits use save(), unlike the read-only public email field.
        # Persist revocation so changing an address back cannot revive a link.
        fields = kwargs.get("update_fields")
        if not self._state.adding and (fields is None or "email" in fields):
            using = kwargs.get("using") or self._state.db or "default"
            with transaction.atomic(using=using):
                previous = type(self).objects.using(using).select_for_update().get(pk=self.pk)
                if fields is None and self.credential_version != previous.credential_version:
                    # An already-authorized profile/admin write may finish
                    # after reset, but cannot restore its earlier credentials.
                    self.password = previous.password
                    self.credential_version = previous.credential_version
                result = super().save(*args, **kwargs)
                if previous.email != self.email:
                    RecoveryToken.objects.using(using).filter(
                        user_id=self.pk, consumed_at__isnull=True, revoked_at__isnull=True,
                    ).update(revoked_at=timezone.now())
                return result
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"

    def get_full_name(self):
        parts = [self.first_name, self.middle_initial, self.last_name]
        return " ".join(p for p in parts if p)

    def assign_role(self, role):
        """
        Give the user `role`, and drop any office-coordinator grant (IR-415).

        The grant was for the office the *old* role staffed. Kept across a
        move, an ITSO coordinator moved to IERC would coordinate IERC without
        anyone granting it, so every role change goes through here.
        """
        self.role = role
        self.is_office_coordinator = False
        self.save(update_fields=["role", "is_office_coordinator"])


class StudentProfile(models.Model):
    """Extended info for Student role users."""
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, related_name="students")

    def __str__(self):
        return f"Student: {self.user.email}"


class AdviserProfile(models.Model):
    """Extended info for Adviser role users."""
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="adviser_profile")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name="advisers")
    college    = models.ForeignKey(College, on_delete=models.SET_NULL, null=True, related_name="advisers")

    def __str__(self):
        return f"Adviser: {self.user.email}"


class RoleRequest(models.Model):
    """
    Created at signup when a user requests Student or Adviser role.
    An admin approves or declines.
    """
    #: Values live in core.enums (IR-135) -- the same three outcomes as a
    #: download or delete request: asked, granted, refused.
    STATUS_CHOICES = RequestStatus.choices
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_requests")
    requested_role = models.ForeignKey(Role, on_delete=models.CASCADE)
    status         = models.CharField(
        max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reviewed_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_role_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} -> {self.requested_role.name} ({self.status})"


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


class UserSession(models.Model):
    """
    One sign-in, for the inactivity rule (IR-166, NFR-S2).

    Its id rides in every token of the sign-in as the `sid` claim; simplejwt
    copies claims through rotation and into each access token. `last_activity_at`
    is the last time the *user* did something -- see `apps.accounts.sessions` --
    and a session idle past `SESSION_IDLE_TIMEOUT_MINUTES` is ended for good.
    `ended_reason` says why it ended, so a refusal can (IR-645); it is null on
    sessions ended before that was recorded.
    """
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    created_at       = models.DateTimeField()
    last_activity_at = models.DateTimeField()
    ended_at         = models.DateTimeField(null=True, blank=True)
    ended_reason     = models.CharField(max_length=32, choices=SessionEndReason.choices, null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} session {self.id}"


# ---- Account recovery (ADR-045, IR-642) ---------------------------------


class RecoveryPurpose(models.TextChoices):
    """What a recovery token or email is for. Immutable once written.

    `email_verification` is ADR-045's second journey (IR-643): the schema
    carries it so both journeys share one contract, and nothing in IR-642
    issues it. `password_changed` is the non-secret notice sent after a reset;
    it never has a token.
    """
    PASSWORD_RESET     = "password_reset", "Password reset"
    EMAIL_VERIFICATION = "email_verification", "Email verification"
    PASSWORD_CHANGED   = "password_changed", "Password changed notice"


class RecoveryToken(models.Model):
    """One emailed single-use link (ADR-045 §3).

    Only the SHA-256 digest of the 32 random bytes is stored, so a database
    read cannot sign anyone in. The token is bound to the address and the
    `credential_version` it was issued against: a changed email or password
    makes it unusable without anything having to remember to revoke it.
    """
    digest             = models.CharField(max_length=64, unique=True)
    user               = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_tokens")
    purpose            = models.CharField(max_length=32, choices=RecoveryPurpose.choices)
    email              = models.EmailField()
    credential_version = models.PositiveIntegerField()
    issued_at          = models.DateTimeField()
    expires_at         = models.DateTimeField()
    consumed_at        = models.DateTimeField(null=True, blank=True)
    revoked_at         = models.DateTimeField(null=True, blank=True)
    #: The intent that issued it. One-to-one is what makes a duplicate or
    #: concurrent worker reuse the token instead of issuing a second (§6).
    intent             = models.OneToOneField(
        "RecoveryIntent", on_delete=models.SET_NULL, null=True, blank=True, related_name="token"
    )

    class Meta:
        indexes = [models.Index(fields=["user", "purpose"])]

    def __str__(self):
        return f"{self.purpose} token {self.pk}"


class RecoveryIntent(models.Model):
    """A request to send one recovery email, durable from the moment it is
    admitted (ADR-045 §6).

    Written in the request's own transaction and enqueued only after it
    commits; the periodic dispatcher finds any whose broker message was lost.
    The recipient address and the raw token are stored only encrypted
    (`apps.accounts.recovery.crypto`), and both are deleted once the intent
    reaches a terminal state. The broker sees nothing but this row's id.
    """

    class Status(models.TextChoices):
        PENDING    = "pending"     # admitted; no token yet
        ISSUED     = "issued"      # token issued; mail owed
        SENT       = "sent"        # SMTP accepted it
        FAILED     = "failed"      # permanent rejection, or attempts exhausted
        SUPERSEDED = "superseded"  # a newer request for this recipient won
        EXPIRED    = "expired"     # not issued within RECOVERY_INTENT_TTL_SECONDS
        INELIGIBLE = "ineligible"  # no eligible account: nothing is sent
        WITHDRAWN  = "withdrawn"   # its token stopped being usable before sending

    TERMINAL = (Status.SENT, Status.FAILED, Status.SUPERSEDED, Status.EXPIRED,
                Status.INELIGIBLE, Status.WITHDRAWN)

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose           = models.CharField(max_length=32, choices=RecoveryPurpose.choices)
    #: Keyed HMAC of the normalized address; empty for a notice, which names
    #: its user instead.
    recipient         = models.CharField(max_length=64, blank=True, default="")
    generation        = models.PositiveIntegerField(default=0)
    #: Fernet ciphertext of the normalized address the request named.
    address_encrypted = models.TextField(blank=True, default="")
    #: Fernet ciphertext of the raw token, held only while mail is owed.
    payload_encrypted = models.TextField(blank=True, default="")
    user              = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="recovery_intents"
    )
    status            = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    #: Correlates this intent's audit events without naming the recipient.
    correlation_id    = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at        = models.DateTimeField()
    expires_at        = models.DateTimeField()
    attempts          = models.PositiveSmallIntegerField(default=0)
    next_attempt_at   = models.DateTimeField()
    #: A worker sending this intent holds it until then; another skips it.
    lease_until       = models.DateTimeField(null=True, blank=True)
    finished_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["recipient", "purpose", "status"]),
        ]

    def __str__(self):
        return f"{self.purpose} intent {self.pk} ({self.status})"


class RecoveryGeneration(models.Model):
    """The newest admitted request per recipient and purpose (ADR-045 §6).

    Kept for unknown addresses too, so admission takes the same path whether
    or not an account exists. Only the intent holding `current` may issue.
    """
    recipient = models.CharField(max_length=64)
    purpose   = models.CharField(max_length=32, choices=RecoveryPurpose.choices)
    current   = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipient", "purpose"], name="recovery_generation_unique"),
        ]


class RecoveryBucket(models.Model):
    """One limit counter's lock row (ADR-045 §5).

    The counter is the `RecoveryAttempt` rows that share its key; this row
    exists so every worker serialises on it before counting. In Postgres
    rather than Redis on purpose: an admission and the intent it admits commit
    together, and the counters are shared across workers by construction.
    """
    key = models.CharField(max_length=96, primary_key=True)


class RecoveryAttempt(models.Model):
    """One counted attempt in a sliding window. Purged after a day."""
    bucket = models.ForeignKey(RecoveryBucket, on_delete=models.CASCADE, related_name="attempts")
    at     = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["bucket", "at"])]
