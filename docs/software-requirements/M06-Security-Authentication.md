# Module 6: Security and Authentication

---

## FR-M6-01 — JWT Token Enforcement and Session Lifecycle

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "Authenticated User" as User
actor "Unauthenticated Client" as Guest
actor System

rectangle "Module 6 : Security and Authentication" {
  usecase "Access Protected API Endpoint" as UC1
  usecase "Validate JWT Access Token (30 min)" as UC2
  usecase "Allow Request" as UC3
  usecase "Return HTTP 401 Unauthorized" as UC4
  usecase "Refresh Access Token" as UC5
  usecase "Validate Refresh Token" as UC6
  usecase "Issue New Access Token" as UC7
  usecase "Blacklist Refresh Token on Logout" as UC8
  usecase "Prevent Reuse of Blacklisted Token" as UC9
}

User   --> UC1
UC1    ..> UC2 : include
UC2    ..> UC3 : extend (valid, not expired)
UC2    ..> UC4 : extend (invalid or expired)
Guest  --> UC5
UC5    ..> UC6 : include
UC6    ..> UC7 : extend (valid)
UC6    ..> UC4 : extend (invalid/blacklisted)
User   --> UC8
UC8    ..> UC9 : include
System --> UC2
System --> UC6
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-01 |
| **Name** | JWT Token Enforcement and Session Lifecycle |
| **Actors** | Authenticated User (primary), Unauthenticated Client, System |
| **Preconditions** | JWT tokens issued at login via djangorestframework-simplejwt |
| **Main Flow** | 1. Client includes JWT access token in `Authorization: Bearer <token>` header 2. DRF validates the token (signature, expiry — 30 minutes) 3. If valid, request proceeds 4. When access token expires, client sends refresh token to the refresh endpoint 5. System validates the refresh token (not blacklisted, not expired) 6. System issues a new access token 7. On logout, client sends refresh token to blacklist endpoint 8. System blacklists the token via simplejwt's token blacklist |
| **Alternative Flow A** | Access token expired/invalid → HTTP 401; client should refresh |
| **Alternative Flow B** | Refresh token is blacklisted → HTTP 401; user must log in again |
| **Postconditions** | Only valid, non-blacklisted tokens grant access; logout is permanent for that refresh token |

### Activity Diagram
```plantuml
@startuml
start
:Client sends API request with Authorization header;
:DRF extracts and validates JWT access token;
if (Token valid and not expired?) then (Yes)
  :Process request;
  stop
else (No)
endif
:Return HTTP 401 Unauthorized;
note right
  Client refresh flow:
  POST /token/refresh/ with refresh token
end note
:Client sends refresh token to /token/refresh/;
if (Refresh token valid and not blacklisted?) then (Yes)
  :Issue new 30-min access token;
  :Client retries original request;
else (No)
  :Return HTTP 401;
  :Force user to log in again;
endif
note right
  Logout flow:
  POST /logout/ with refresh token
  → Token blacklisted via simplejwt
end note
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{
  JWT Session Lifecycle — System-Level Enforcement
  ==
  Session Expired — shown to user
  {+
    ⚠ Session Expired
    --
    Your session has expired. Please log in again.
    .
    [           Go to Login           ]
  }
  .
  Token refresh is handled silently by the frontend.
  No user prompt unless the refresh token is also expired.
}
@endsalt
```

---

## FR-M6-02 — Role-Based Access Control Enforcement

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Student
actor Adviser
actor "KTTO Staff" as KTTO
actor "RDCO Staff" as RDCO
actor "ITSO Staff" as ITSO
actor "IERC Staff" as IERC
actor Admin
actor System

rectangle "Module 6 : Security and Authentication" {
  usecase "Request API Endpoint" as UC1
  usecase "Check User Role vs Required Permission" as UC2
  usecase "Allow Action" as UC3
  usecase "Return HTTP 403 Forbidden" as UC4
}

Student  --> UC1
Adviser  --> UC1
KTTO     --> UC1
RDCO     --> UC1
ITSO     --> UC1
IERC     --> UC1
Admin    --> UC1
UC1      ..> UC2 : include
UC2      ..> UC3 : extend (role permitted)
UC2      ..> UC4 : extend (role not permitted)
System   --> UC2
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-02 |
| **Name** | Role-Based Access Control Enforcement |
| **Actors** | All roles (primary), System |
| **Preconditions** | User is authenticated; role is assigned to the user account |
| **Main Flow** | 1. Authenticated user sends a request to any API endpoint 2. DRF permission class checks the user's assigned role against the endpoint's required permission 3. If the role is permitted, the request proceeds 4. Role checks are enforced server-side regardless of what the frontend renders |
| **Role Mapping** | Student: submit/view own records · Adviser: review Proposals · KTTO: review IP/commercialization · RDCO: intake + final review, manage users · ITSO: review Projects · IERC: ethics review · Admin: all operations |
| **Alternative Flow A** | User's role does not meet the required permission → HTTP 403 Forbidden |
| **Alternative Flow B** | User has no role assigned → Treated as lowest-privilege; most actions blocked |
| **Postconditions** | Only permitted actions succeed; all permission checks are server-side |

### Activity Diagram
```plantuml
@startuml
start
:Authenticated user sends API request;
:DRF extracts user role from JWT / DB;
:Check endpoint permission class
  (IsAdmin / IsStaff / IsReviewer /
   IsOwnerOrStaff / IsAuthenticated);
if (Role satisfies permission?) then (Yes)
  :Process request;
else (No)
  :Return HTTP 403 Forbidden;
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{
  Role-Based Access Control — UI Reflects Server Permissions
  ==
  Student View — Record Detail
  {+
    [Edit]   [Request Deletion]
  }
  .
  RDCO View — Record Detail
  {+
    [Edit]   [Review]   [Tag IP]   [Approve]   [Decline]
  }
  .
  HTTP 403 Response (when role check fails)
  {+
    403 Forbidden
    --
    You do not have permission to perform this action.
  }
}
@endsalt
```

---

## FR-M6-03 — Role Request and Approval Flow

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor User
actor "Admin / Staff" as Admin
actor System

rectangle "Module 6 : Security and Authentication" {
  usecase "Submit Role Request at Registration" as UC1
  usecase "Hold Request in Pending State" as UC2
  usecase "Surface Request to Admin" as UC3
  usecase "Admin Approves Request" as UC4
  usecase "Admin Rejects Request" as UC5
  usecase "Assign Role to User" as UC6
  usecase "Notify User of Approval" as UC7
  usecase "Notify User of Rejection with Reason" as UC8
}

User   --> UC1
UC1    ..> UC2 : include
UC2    ..> UC3 : include
Admin  --> UC4
Admin  --> UC5
UC4    ..> UC6 : include
UC4    ..> UC7 : include
UC5    ..> UC8 : include
System --> UC6
System --> UC7
System --> UC8
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-03 |
| **Name** | Role Request and Approval Flow |
| **Actors** | User (primary), Django Admin (`is_staff = True`), System |
| **Preconditions** | User has registered and verified their email |
| **Main Flow** | 1. During registration, user selects Student or Adviser role (roles that require admin approval) 2. System creates a RoleRequest with `status = "pending"` 3. The request is surfaced on the Admin Portal Role Requests page (Django Admin only) 4. Admin approves → role assigned + user notified |
| **Approver by role** | Student and Adviser requests → approved by Django Admin (`is_staff = True`) only · Staff accounts (RDCO, KTTO, ITSO, IERC) → managed directly by Admin (superuser) |
| **Alternative Flow A** | Admin rejects → `RoleRequest.status = "declined"`; user notified with reason |
| **Alternative Flow B** | User logs in while request is pending → Redirected to Pending Approval screen |
| **Postconditions** | User's role updated (if approved); user notified of outcome |

### Activity Diagram
```plantuml
@startuml
start
:User registers and selects Student or Adviser role;
note right
  Staff accounts (RDCO, KTTO, ITSO, IERC)
  are provisioned directly by Admin —
  no role request required
end note
:System creates RoleRequest (status = "pending");
:User redirected to Pending Approval screen;
:Django Admin opens Role Requests page (/admin/role-requests);
:Admin reviews the request;
if (Admin approves?) then (Yes)
  :Set RoleRequest.status = "approved";
  :Assign requested role to user;
  :Send approval notification to user;
else (No)
  :Set RoleRequest.status = "declined";
  :Send rejection notification with reason;
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Admin > Role Requests
  ==
  Pending Role Requests
  {#
  Name       | Email       | Requested Role | Actions
  Ana Cruz   | ana@cit.edu | Adviser        | [✓] [✗]
  Ben Torres | ben@cit.edu | Student        | [✓] [✗]
  }
  .
  --
  Decline Modal
  {+
    Decline Role Request for: Ana Cruz
    --
    Reason: | "                                    "
    .
    [Cancel]   [Decline]
  }
}
@endsalt
```

---

## FR-M6-04 — Account Management (Lock, Unlock, Role Change)

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Admin
actor "Target User" as User
actor System

rectangle "Module 6 : Security and Authentication" {
  usecase "View User in Admin Interface" as UC1
  usecase "Lock User Account" as UC2
  usecase "Unlock User Account" as UC3
  usecase "Change User Role" as UC4
  usecase "Record State Change in Audit Log" as UC5
  usecase "Notify User of Role Change" as UC6
  usecase "Show Clear Error on Locked Login" as UC7
}

Admin --> UC1
UC1   ..> UC2 : extend
UC1   ..> UC3 : extend
UC1   ..> UC4 : extend
UC2   ..> UC5 : include
UC3   ..> UC5 : include
UC4   ..> UC5 : include
UC4   ..> UC6 : include
User  --> UC7
System --> UC5
System --> UC6
System --> UC7
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-04 |
| **Name** | Account Management (Lock, Unlock, Role Change) |
| **Actors** | Admin (primary), Target User, System |
| **Preconditions** | Admin is authenticated; target user account exists |
| **Main Flow — Lock** | 1. Admin navigates to user detail 2. Admin clicks "Lock Account" 3. System sets `is_locked = true` 4. State change recorded in audit log 5. Locked user attempting to login receives "Account is locked" error |
| **Main Flow — Unlock** | 1. Admin clicks "Unlock Account" 2. System sets `is_locked = false` 3. System clears django-axes AccessAttempt records for the email 4. State change recorded in audit log |
| **Main Flow — Role Change** | 1. Admin selects a new role 2. System updates `user.role` 3. System sends role change notification email 4. State change recorded in audit log |
| **Postconditions** | Account state reflects the change; all changes recorded in audit log |

### Activity Diagram
```plantuml
@startuml
start
:Admin opens User Management interface;
if (Action = Lock?) then (Yes)
  :Set user.is_locked = true;
  :Log "account_locked" in AuditEvent;
  :Return confirmation;
else if (Action = Unlock?) then (Yes)
  :Set user.is_locked = false;
  :Delete AccessAttempt records for email;
  :Log "account_unlocked" in AuditEvent;
  :Return confirmation;
else (Action = Role Change)
  :Update user.role to selected role;
  :Log "role_changed" in AuditEvent;
  :Send role update notification email;
  :Return updated user data;
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Admin > Users > Ana Cruz
  ==
  Name:   Ana Cruz
  Email:  ana@cit.edu
  Status: 🔒 Locked
  .
  Role:  | ^Adviser           ^ |  [Change Role]
  .
  [🔓 Unlock Account]
  ==
  Account State Changes
  {#
  Date       | Action         | By
  2026-05-27 | account_locked | admin@cit.edu
  2026-05-20 | role_changed   | admin@cit.edu
  }
}
@endsalt
```

---

## FR-M6-05 — Active Session Monitoring and Revocation

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Admin
actor "Affected User" as User
actor System

rectangle "Module 6 : Security and Authentication" {
  usecase "View List of Active Sessions" as UC1
  usecase "Identify Session by User / JTI" as UC2
  usecase "Revoke Session (Blacklist JWT)" as UC3
  usecase "Force User Re-authentication" as UC4
  usecase "Log Revocation in Audit Log" as UC5
}

Admin --> UC1
UC1   ..> UC2 : include
Admin --> UC3
UC3   ..> UC4 : include
UC3   ..> UC5 : include
System --> UC3
System --> UC5
User  ..> UC4 : affected by
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-05 |
| **Name** | Active Session Monitoring and Revocation |
| **Actors** | Admin (primary), Affected User, System |
| **Preconditions** | Admin is authenticated; JWT refresh tokens exist in OutstandingToken |
| **Main Flow** | 1. Admin navigates to Active Sessions page 2. System returns all non-expired, non-blacklisted JWT refresh tokens with associated user info 3. Admin identifies a session to revoke 4. Admin clicks "Revoke" 5. System creates a `BlacklistedToken` entry 6. System logs a LOGOUT audit event with `action = "admin_revoke"` 7. Affected user's next request returns HTTP 401 |
| **Alternative Flow A** | JTI not found → HTTP 404 "Session not found" |
| **Postconditions** | Token blacklisted; user forced to re-authenticate; revocation in audit log |

### Activity Diagram
```plantuml
@startuml
start
:Admin opens Active Sessions page;
:System fetches OutstandingTokens
  WHERE expires_at > now() AND not blacklisted;
:Display session table (user, email, created, expires, JTI);
:Admin clicks Revoke on a session;
:System sends DELETE /users/sessions/<jti>/;
if (JTI exists in OutstandingToken?) then (No)
  :Return HTTP 404 "Session not found";
  stop
else (Yes)
endif
:Create BlacklistedToken entry for the JTI;
:Log LOGOUT audit event (admin_revoke, revoked_jti);
:Session removed from list;
:Next request from affected user returns HTTP 401;
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Admin > Active Sessions                  Total: 12
  ==
  {#
  User           | Email         | Created    | Expires    | Action
  Juan Dela Cruz | juan@cit.edu  | 2026-05-27 | 2026-06-03 | [Revoke]
  Maria Santos   | maria@cit.edu | 2026-05-26 | 2026-06-02 | [Revoke]
  Ana Cruz       | ana@cit.edu   | 2026-05-25 | 2026-06-01 | [Revoke]
  }
  .
  ⚠ Revoking forces that user to log in again.
}
@endsalt
```

---

## FR-M6-06 — Data Privacy Consent and Audit Logging

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "New User" as User
actor System
actor Admin

rectangle "Module 6 : Security and Authentication" {
  usecase "Accept Data Privacy Notice (RA 10173)" as UC1
  usecase "Record Consent at Registration" as UC2
  usecase "Security Event Occurs" as UC3
  usecase "Write AuditEvent (actor, type,\ntimestamp, record_id)" as UC4
  usecase "View Audit Log (Admin only)" as UC5
  usecase "Block Non-Admin from Audit Log" as UC6
}

User   --> UC1
UC1    ..> UC2 : include
System --> UC3
UC3    ..> UC4 : include
Admin  --> UC5
System --> UC6
UC6    ..> UC5 : precedes
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M6-06 |
| **Name** | Data Privacy Consent and Audit Logging |
| **Actors** | New User (primary), System, Admin |
| **Preconditions** | RA 10173 (Data Privacy Act) compliance required |
| **Main Flow — Consent** | 1. During registration, user is shown the Data Privacy Notice 2. User checks "I agree" before submitting 3. System records consent in the user account |
| **Main Flow — Audit Logging** | 1. A security-relevant event occurs 2. System writes an `AuditEvent` with: actor identity, event type, timestamp, associated record ID (if applicable) 3. Audit log is read-only to all roles except Admin |
| **Tracked Events** | LOGIN · LOGOUT · FAILED_LOGIN · PIN_GENERATED · PIN_VERIFIED · UPLOAD · DOWNLOAD · DELETE · RENAME · ACCESS · ROLE_CHANGE · ACCOUNT_LOCKED · ACCOUNT_UNLOCKED · SESSION_REVOKE |
| **Postconditions** | Consent recorded; all security events in the immutable audit trail; only Django Admin (IT administration, `is_staff = True`) can read the log — IRIS role users including RDCO and KTTO cannot access it |

### Activity Diagram
```plantuml
@startuml
start
partition "Consent at Registration" {
  :User views Data Privacy Notice;
  :User checks "I agree to the terms";
  :System records consent with timestamp;
}
partition "Audit Event Logging" {
  :Security-relevant event occurs in IRIS;
  :System creates AuditEvent:
    actor = request.user
    event_type = LOGIN / LOGOUT / ACCESS / etc.
    timestamp = now()
    record_id = (if applicable);
  :AuditEvent written to AuditEvent table;
}
partition "Audit Log Access" {
  :User requests audit log;
  if (User is Django Admin? (is_staff = True)) then (Yes)
    :Return paginated AuditEvent list;
  else (No)
    :Return HTTP 403 Forbidden;
  endif
}
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  Sign Up — Data Privacy Consent
  ==
  {SI
In compliance with RA 10173 (Data Privacy Act of 2012),
IRIS collects and processes your personal data for
institutional research management purposes only.
}
  .
  [X] I have read and agree to the Data Privacy Notice.
  .
  [            Create Account            ]
}
@endsalt
```

```plantuml
@startsalt
{+
  IRIS > Admin > Audit Log
  ==
  {#
  Event Type     | Actor           | Timestamp        | Record
  LOGIN          | juan@cit.edu    | 2026-05-27 09:01 | —
  UPLOAD         | juan@cit.edu    | 2026-05-27 09:15 | #142
  DOWNLOAD       | maria@cit.edu   | 2026-05-27 09:22 | #138
  ROLE_CHANGE    | admin@cit.edu   | 2026-05-27 10:00 | —
  SESSION_REVOKE | admin@cit.edu   | 2026-05-27 10:05 | —
  }
  .
  [< Prev]   Page 1 of 48   [Next >]   [Export]
}
@endsalt
```
