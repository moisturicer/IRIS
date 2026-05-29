# Module 1: Backend Optimization & Responsive UI

---

## FR-M1-01 — User Login and Session Management

### Use Case Diagram

```plantuml
@startuml
scale 0.75
left to right direction

actor "Guest / Unverified User" as Guest
actor "Registered User"         as User
actor "Admin"                   as Admin

rectangle "FR-M1-01 : User Login and Session Management" {
  usecase "Register Account"             as UC1
  usecase "Verify Email"                 as UC2
  usecase "Log In"                       as UC3
  usecase "View Pending Approval Screen" as UC4
  usecase "Access Protected Route"       as UC5
  usecase "Silent Token Refresh"         as UC6
  usecase "Log Out"                      as UC7
  usecase "Change Password"              as UC8
  usecase "List Active Sessions"         as UC9
  usecase "Force-Revoke Session"         as UC10
}

Guest --> UC1
UC1   ..> UC2 : include
User  --> UC3
UC3   ..> UC4 : extend (role not yet approved)
User  --> UC5
UC5   ..> UC6 : extend (access token expired)
User  --> UC7
User  --> UC8
Admin --> UC9
UC9   ..> UC10 : include
@enduml
```

### Use Case Descriptions

**Table M1-1: Register Account**

| Use Case | Register Account |
|---|---|
| Actors | Guest (Unregistered User) |
| Description | A new user creates an IRIS account by providing their institutional email, personal details, affiliated department or course, and data privacy consent. The system creates an unverified account with a pending role request and dispatches an activation email. |
| Preconditions | The user has a valid institutional email address and has not previously registered with IRIS. |
| Main Flow | 1. The user navigates to the registration page and fills in their email, full name, password, and selects a role (Student or Adviser). 2. The user selects their affiliated department or course and acknowledges the data privacy consent. 3. The system validates all fields, creates an unverified user account, and generates a pending role request. 4. The system sends a time-limited email verification link to the provided address. 5. The system displays a confirmation prompting the user to check their email. |
| Alternative Flow | **Validation Failure:** At Step 3, if the email is already registered, the password is too weak, consent is not acknowledged, or a required field is missing, the system returns inline field errors and the account is not created. |
| Postconditions | An unverified user account and a pending role request exist in the system. A verification email has been dispatched. |

**Table M1-2: Verify Email Address**

| Use Case | Verify Email Address |
|---|---|
| Actors | Registered (Unverified) User |
| Description | After registering, the user confirms ownership of their institutional email by clicking a time-limited activation link. Email verification is required before the user can log in. |
| Preconditions | The user has completed registration and received a verification email. |
| Main Flow | 1. The user opens the verification email and clicks the activation link. 2. The system validates the link's authenticity and checks that it has not expired (3-day window). 3. The system marks the account as email-verified. 4. The system displays an "Email verified — awaiting administrator role approval" confirmation. |
| Alternative Flow | **Expired or Invalid Link:** At Step 2, if the link has expired or has been tampered with, the system displays an error and the account remains unverified. |
| Postconditions | The user account is marked as verified. The user may log in once an administrator approves their role request. |

**Table M1-3: User Login and Session Management**

| Use Case | User Login and Session Management |
|---|---|
| Actors | Any System User |
| Description | The user accesses the IRIS platform to establish an authenticated session. The system validates credentials, issues a secure JSON Web Token (JWT), and routes the user to their role-specific dashboard using a responsive layout. |
| Preconditions | The IRIS system is online, and the user has a registered and email-verified institutional account. |
| Main Flow | 1. The user navigates to the IRIS login page via a web browser (mobile or desktop). 2. The user enters their institutional email and password. 3. The system validates the credentials and issues a JWT access token (30-minute validity) and a refresh token (7-day validity). 4. The system records a login event in the audit log. 5. The system redirects the user to their role-specific dashboard. |
| Alternative Flow | **Invalid Credentials and Account Lockout:** At Step 3, if the credentials do not match, the system increments the failed login counter and displays a generic "Invalid email or password" error. After 3 consecutive failures from the same account and IP address, the system locks the account for 10 minutes, displays an "Account Locked" notification, and logs a security event in the audit trail. The lockout lifts automatically after 10 minutes. **Unverified Account:** At Step 3, if the account has not completed email verification, the system returns an "Email not verified" error and does not issue tokens. **Admin-Locked Account:** At Step 3, if an administrator has manually locked the account, the system returns an "Account is locked" error. |
| Postconditions | A secure, authenticated session is started for the user. JWT tokens are stored in the browser. |

**Table M1-4: Role Approval Gate**

| Use Case | Role Approval Gate |
|---|---|
| Actors | Registered User (pending role approval) |
| Description | After a successful login, a user whose role request has not yet been approved is shown a holding screen. The system blocks access to all application features until an administrator approves the role. |
| Preconditions | The user has logged in successfully but has no assigned role (role request is still pending). |
| Main Flow | 1. Login completes and JWT tokens are issued normally. 2. The application detects that the user has no assigned role and is not a staff member. 3. The system renders the Pending Approval page in place of all other content without changing the URL. 4. The user sees an "awaiting approval" notice on every route until their role is approved. |
| Alternative Flow | None — all routes display the Pending Approval page for an unapproved user regardless of the URL navigated to. |
| Postconditions | Once an administrator approves the role request, the user can log in and access the full application. |

**Table M1-5: Silent Token Refresh**

| Use Case | Silent Token Refresh |
|---|---|
| Actors | Authenticated User |
| Description | When the user's short-lived access token expires, the system transparently issues a new token pair using the stored refresh token, without interrupting the session or requiring a new login. |
| Preconditions | The user is logged in with a valid, non-expired refresh token stored in the browser. |
| Main Flow | 1. An API request receives an HTTP 401 response indicating the access token has expired. 2. The system reads the stored refresh token from the browser. 3. The system requests a new token pair from the server. 4. The server validates the refresh token, issues a new access and refresh token, and permanently invalidates the old refresh token. 5. The system saves both new tokens and transparently retries the original failed request. |
| Alternative Flow | **Missing or Invalid Refresh Token:** At Steps 2–3, if no refresh token is found or the token is expired, invalid, or already invalidated, the system clears all session data from the browser and redirects the user to the login page. |
| Postconditions | A new token pair is active. The old refresh token is permanently invalidated. The original request completes without user intervention. |

**Table M1-6: Log Out**

| Use Case | Log Out |
|---|---|
| Actors | Authenticated User |
| Description | The user ends their IRIS session. The system invalidates the refresh token server-side to prevent reuse and clears all local session data from the browser. |
| Preconditions | The user is authenticated with an active session. |
| Main Flow | 1. The user clicks the "Sign Out" button. 2. The system sends the current refresh token to the server for invalidation. 3. The server blacklists the refresh token and records a logout event in the audit log. 4. The system removes all tokens from the browser and redirects the user to the login page. |
| Alternative Flow | **Already-Invalidated Token:** If the refresh token has already expired or been blacklisted, the server discards the error and still returns success. The local session is cleared regardless. |
| Postconditions | The refresh token is permanently blacklisted. All local session data is cleared. A logout event is recorded in the audit log. |

**Table M1-7: Admin Session Revocation**

| Use Case | Admin Session Revocation |
|---|---|
| Actors | Admin |
| Description | An administrator force-terminates any active user session by revoking the associated JWT. The affected user is logged out on their next request. |
| Preconditions | The administrator is authenticated with staff privileges. At least one active session exists in the system. |
| Main Flow | 1. The administrator navigates to the Active Sessions management screen. 2. The administrator selects a session and confirms the revocation. 3. The system force-blacklists the JWT by its unique token identifier. 4. The system records the administrative action in the audit log. 5. The targeted user is redirected to the login page upon their next request. |
| Alternative Flow | **Session Not Found:** If the selected session token no longer exists or has already expired, the system returns a not-found error and no further action is taken. |
| Postconditions | The targeted user's JWT is permanently blacklisted. The user is effectively logged out upon their next API interaction. |

**Table M1-8: Change Password**

| Use Case | Change Password |
|---|---|
| Actors | Authenticated User |
| Description | An authenticated user updates their account password from within the application. The system verifies the current password before accepting the new one. |
| Preconditions | The user is logged in with an active session. |
| Main Flow | 1. The user navigates to their account settings and selects "Change Password." 2. The user enters their current password and a new password with confirmation. 3. The system verifies that the current password is correct and that the new password meets the minimum strength requirement. 4. The system updates the password and displays a confirmation. |
| Alternative Flow | **Incorrect Current Password:** At Step 3, if the current password does not match the stored credential, the system returns a validation error and the password is not changed. **Password Too Weak:** At Step 3, if the new password does not meet the minimum length requirement, the system returns a field-level error. |
| Postconditions | The user's password has been updated. Existing sessions remain active. |

### Activity Diagrams

#### Sub-Flow A — Registration

```plantuml
@startuml
|Browser|
start
:Fill and submit registration form;
:POST /api/v1/auth/register/;

|Application|
if (Validation passes?) then (No)
  :HTTP 400 — field-level errors;
  |Browser|
  :Show inline field errors;
  stop
else (Yes)
endif
:Create user account (unverified) and pending role request;
:Generate time-limited HMAC verification link;
:Queue verification email (non-blocking);
:HTTP 201;

|Browser|
:Show "Check your email to verify your account";
stop
@enduml
```

#### Sub-Flow B — Email Verification

```plantuml
@startuml
|Browser|
start
:Click verification link in email;
:GET /api/v1/auth/activate/<uidb64>/<token>/;

|Application|
:Decode user ID from URL;
:Look up user account;
if (User found and HMAC token valid?) then (No)
  :HTTP 400 — invalid or expired link;
  |Browser|
  :Show error;
  stop
else (Yes)
endif
:Mark account as verified;
:HTTP 200 — Account activated;

|Browser|
:Show "Email verified — awaiting admin role approval";
stop
@enduml
```

#### Sub-Flow C — Login

```plantuml
@startuml
|Browser|
start
:Submit email + password;
:POST /api/v1/auth/login/;

|Application|
:Check brute-force counter for (email + IP);
if (failures >= 3?) then (Yes)
  :HTTP 403 — Account is locked;
  |Browser|
  :Show "Account is locked. Contact administrator.";
  stop
else (No)
endif
:Verify credentials;
if (Credentials valid?) then (No)
  :Increment failure counter;
  :HTTP 401 — Invalid credentials;
  |Browser|
  :Show "Invalid credentials";
  stop
else (Yes)
endif
:Reset failure counter;
if (Email verified AND account not locked?) then (No)
  :HTTP 403 — appropriate message;
  |Browser|
  :Show error;
  stop
else (Yes)
endif
:Issue access token (30 min) + refresh token (7 days);
:Record LOGIN event in audit log;
:HTTP 200 — token pair + user profile;

|Browser|
:Store both tokens in localStorage;
:Set isAuthenticated = true in Zustand;
if (user.role is null?) then (Yes)
  :AppShell renders PendingApprovalPage;
  :User sees "awaiting approval" on all routes;
  stop
else (No)
endif
:Render application;
stop
@enduml
```

#### Sub-Flow D — Pending Role Approval

```plantuml
@startuml
|Browser (AppShell)|
start
:Authenticated user navigates to any protected route;
if (user.role is null AND not staff?) then (Yes)
  :Render <PendingApprovalPage />;
  note right
    URL unchanged.
    User cannot navigate past
    this screen until an admin
    approves their role request.
  end note
  stop
else (No)
endif
:Render page content normally;
stop
@enduml
```

#### Sub-Flow E — Silent Token Refresh

```plantuml
@startuml
|Browser (Axios Interceptor)|
start
:API call returns HTTP 401 (access token expired);
if (_retry flag already set?) then (Yes)
  :Clear tokens from localStorage;
  :Redirect to /login;
  stop
else (No)
endif
:Read refresh token from localStorage;
if (Refresh token present?) then (No)
  :Clear tokens from localStorage;
  :Redirect to /login;
  stop
else (Yes)
endif
:POST /api/v1/auth/token/refresh/;

|Application|
:Validate refresh token signature and expiry;

|Database & Services|
:Check refresh token is not blacklisted;

|Application|
if (Refresh token valid?) then (No)
  :HTTP 401;
  |Browser (Axios Interceptor)|
  :Clear tokens from localStorage;
  :Redirect to /login;
  stop
else (Yes)
endif
:Issue new access token + new refresh token;
:Blacklist old refresh token;
:HTTP 200 — new token pair;

|Browser (Axios Interceptor)|
:Save new access + refresh tokens to localStorage;
:Retry original request with new access token;
stop
@enduml
```

#### Sub-Flow F — Logout

```plantuml
@startuml
|Browser|
start
:User clicks Sign Out;
:POST /api/v1/auth/logout/
  Authorization: Bearer <access_token>
  Body: { "refresh": "..." };

|Application|
:Validate access token;
:Blacklist refresh token;
:Record LOGOUT event in audit log;
:HTTP 200 — Logged out;

|Browser|
:Remove tokens from localStorage;
:Redirect to /login;
stop
@enduml
```

#### Sub-Flow G — Protected Route Guard

```plantuml
@startuml
|Browser (React Router)|
start
:Navigate to a protected route;
if (isAuthenticated in Zustand?) then (No)
  :Redirect to /login;
  stop
else (Yes)
endif
:AppShell checks role approval (→ Sub-Flow D);
:Component makes API call;
:Attach Authorization: Bearer <access_token>;

|Application (DRF)|
:Validate JWT signature and expiry;

|Database & Services|
:Check token is not blacklisted;

|Application (DRF)|
if (Token valid?) then (No)
  :HTTP 401;
  |Browser (React Router)|
  :Axios interceptor attempts silent refresh (→ Sub-Flow E);
  stop
else (Yes)
endif
:Evaluate permission classes;
if (Permission granted?) then (No)
  :HTTP 403;
  |Browser (React Router)|
  :Display "Access denied";
  stop
else (Yes)
endif
:Return data;

|Browser (React Router)|
:Render page;
stop
@enduml
```

### Wireframes

#### Login Page
```plantuml
@startsalt
{+
  IRIS                                         | [Sign Up]
  ==
  .
  {+
    Institutional Research Information System
    ==
    Email:    | "juan@cit.edu                    "
    Password: | "••••••••••••••••                "
    .
    [                Log In                ]
    .
    Don't have an account? | [Sign Up]
  }
  .
  --
  ⚠ Invalid credentials.                   (HTTP 401)
  ⚠ Email not verified.                    (HTTP 403)
  ⚠ Account is locked. Contact admin.      (HTTP 403)
}
@endsalt
```

#### Pending Approval Page (AppShell gate — no sidebar, URL unchanged)
```plantuml
@startsalt
{+
  IRIS · CIT-U Research Hub
  ==
  .
  ⏳
  .
  Account Pending Approval
  --
  Your registration was received and your
  email has been verified. An administrator
  will review and approve your account shortly.
  .
  Registered as
  {+
    Juan Dela Cruz
    juan@cit.edu
  }
  .
  What happens next
  ✉ You will receive an email once approved.
  → Log back in after approval to access IRIS.
  🕐 Approvals processed within 1-2 business days.
  .
  [              Sign out              ]
}
@endsalt
```

#### Admin — Active Sessions
```plantuml
@startsalt
{+
  IRIS > Admin > Active Sessions            [🔄 Refresh]
  ==
  Active Sessions (non-expired · non-revoked)
  {#
  User                      | JTI (short) | Created      | Expires      | Action
  juan@cit.edu · Student    | a3f9...12bc | 05-27 08:30  | 06-03 08:30  | [Revoke]
  maria@cit.edu · Adviser   | b7c1...44ef | 05-26 14:15  | 06-02 14:15  | [Revoke]
  rdco@cit.edu · RDCO       | c8d2...77ab | 05-27 07:00  | 06-03 07:00  | [Revoke]
  }
  .
  Revoke → force-blacklists the JWT by JTI.
  The user is logged out on their next request.
}
@endsalt
```

---

## FR-M1-02 — API Request Throttling and Rate Limiting

### Use Case Diagram

```plantuml
@startuml
scale 0.75
left to right direction

actor "Authenticated User" as User
actor "Anonymous Client"   as Anon
actor "Admin"              as Admin

rectangle "FR-M1-02 : API Request Throttling and Rate Limiting" {
  usecase "Make API Request"             as UC1
  usecase "Request Allowed"              as UC2
  usecase "HTTP 429 — Rate Limit Hit"    as UC3
  usecase "Failed Login Attempt"         as UC4
  usecase "HTTP 403 — Account Locked"    as UC5
  usecase "Unlock Account"               as UC6
}

User  --> UC1
Anon  --> UC1
UC1   ..> UC2 : extend (within limit)
UC1   ..> UC3 : extend (limit exceeded)
User  --> UC4
UC4   ..> UC5 : extend (3rd failure)
Admin --> UC6
@enduml
```

### Use Case Description

**Table M1-9: API Request Throttling and Rate Limiting**

| Use Case | API Request Throttling and Rate Limiting |
|---|---|
| Actors | Authenticated User, Anonymous Client, Admin |
| Description | The system enforces rate limits on all API requests to prevent abuse and ensure service availability. Anonymous requests are limited by IP address, authenticated requests by user identity, and repeated login failures trigger a temporary account lockout. |
| Preconditions | The IRIS API is running and available to clients. |
| Main Flow | 1. A client sends a request to any IRIS API endpoint. 2. The system evaluates the client's request count against the applicable daily limit — 100 requests per day for anonymous clients, or 1,000 requests per day for authenticated users. 3. If the limit has not been reached, the request counter is incremented and the request proceeds normally. 4. The system returns the requested resource. |
| Alternative Flow | **Rate Limit Exceeded:** At Step 2, if the client has reached their daily limit, the system rejects the request with an HTTP 429 Too Many Requests response and includes a Retry-After header indicating when the client may resume. **Brute-Force Lockout:** If a user fails to authenticate 3 consecutive times from the same email and IP combination, the system locks the account for 10 minutes and returns an HTTP 403 Forbidden response. An administrator may manually unlock the account before the window expires. |
| Postconditions | Valid requests within the limit are served. Clients that exceed the limit are informed of the retry window. Accounts subjected to brute-force attempts are temporarily locked. |

### Activity Diagrams

#### Sub-Flow A — DRF Rate Throttle Check

```plantuml
@startuml
|Application|
start
:Incoming API request;
if (Request is authenticated?) then (Yes)
  :Look up daily request counter for this user (Redis);
  if (Counter < 1 000?) then (Yes)
    :Increment counter;
    :Allow request to proceed;
    stop
  else (No)
    :HTTP 429 — Too Many Requests;
    :Header: Retry-After: <seconds>;
    stop
  endif
else (Anonymous)
  :Look up daily request counter for this IP (Redis);
  if (Counter < 100?) then (Yes)
    :Increment counter;
    :Allow request to proceed;
    stop
  else (No)
    :HTTP 429 — Too Many Requests;
    :Header: Retry-After: <seconds>;
    stop
  endif
endif
@enduml
```

#### Sub-Flow B — django-axes Login Brute-Force Protection

```plantuml
@startuml
|Browser|
start
:Submit login credentials;
:POST /api/v1/auth/login/;

|Application|
:Check failure counter for (email + IP);
if (failures >= 3?) then (Yes)
  :HTTP 403 — Account is locked;
  |Browser|
  :Show "Account is locked. Contact administrator.";
  stop
else (No)
endif
:Attempt credential verification;
if (Credentials valid?) then (No)
  :Increment failure counter;

  |Database & Services|
  :Update failure count for (email + IP);

  |Application|
  :HTTP 401 — Invalid credentials;
  |Browser|
  :Show error; display remaining attempts (optional);
  stop
else (Yes)
endif
:Reset failure counter;
:Continue to login success flow;
stop
@enduml
```

### Wireframe

```plantuml
@startsalt
{+
  API Throttling — System-Level Enforcement
  ==
  HTTP 429 — DRF Rate Limit
  {+
    429 Too Many Requests
    --
    "Request was throttled.
     Expected available in 86313 seconds."
    .
    Response Header: Retry-After: 86313
  }
  ==
  HTTP 403 — Brute-Force Lock (login page)
  {+
    ⚠ Account is locked.
    --
    Too many failed login attempts.
    Please contact the IRIS administrator to unlock.
  }
  ==
  Active Configuration
  {#
  Setting                                  | Value
  DEFAULT_THROTTLE_RATES.anon              | 100 / day
  DEFAULT_THROTTLE_RATES.user              | 1 000 / day
  AXES_FAILURE_LIMIT                       | 3
  AXES_COOLOFF_TIME_MINUTES                | 10
  AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP | True
  Throttle counter store                   | Redis
  }
}
@endsalt
```

---

## FR-M1-03 — Mobile-Responsive Interface

### Use Case Diagram

```plantuml
@startuml
scale 0.75
left to right direction

actor "Desktop User (≥1280px)"   as Desktop
actor "Tablet User (768-1279px)" as Tablet
actor "Mobile User (<768px)"     as Mobile

rectangle "FR-M1-03 : Mobile-Responsive Interface" {
  usecase "View Full Sidebar with Labels" as UC1
  usecase "View Icon-Only Sidebar Rail"   as UC2
  usecase "Open Sidebar Drawer"           as UC3
  usecase "Close Sidebar"                 as UC4
}

Desktop --> UC1
Tablet  --> UC2
Mobile  --> UC3
UC3     ..> UC4 : extend (NavLink tap / backdrop tap / ✕ button)
@enduml
```

### Use Case Description

**Table M1-10: Mobile-Responsive Interface**

| Use Case | Mobile-Responsive Interface |
|---|---|
| Actors | Desktop User (≥1280px), Tablet User (768–1279px), Mobile User (<768px) |
| Description | The IRIS interface adapts its navigation layout to the user's viewport size without horizontal scrolling or content overflow. Desktop users see a full labeled sidebar, tablet users see a compact icon-only rail, and mobile users access navigation through a collapsible drawer. |
| Preconditions | The user is accessing IRIS through a supported web browser at any viewport width. |
| Main Flow | 1. The user opens IRIS in their web browser. 2. The application detects the viewport width and applies the appropriate layout automatically. 3a. On desktop (≥1280px): the full sidebar with labels and section headings is always visible alongside the content area. 3b. On tablet (768–1279px): a compact icon-only navigation rail is permanently visible; labels, section headings, and notification badges are hidden. 3c. On mobile (<768px): the sidebar is hidden off-screen, the content occupies the full width, and a hamburger button is visible in the header. |
| Alternative Flow | **Mobile Drawer Interaction:** On mobile, tapping the hamburger button slides the sidebar drawer into view with a backdrop overlay. The drawer closes when the user taps a navigation link, taps the backdrop, or taps the close button. |
| Postconditions | The user can navigate to all application destinations at any supported viewport width. No horizontal scrollbar appears at any supported screen size. |

### Activity Diagram

```plantuml
@startuml
|Browser|
start
:Page loads — Tailwind CSS applied;
:Measure viewport width;

if (≥ 1280px — Desktop?) then (Yes)
  :Full sidebar (230px) always visible;
  :Content: ml-[230px];
  :Hamburger hidden;
else if (≥ 768px — Tablet?) then (Yes)
  :Icon-only rail (60px) always visible;
  :Labels, headings, badges hidden;
  :Content: ml-[60px];
  :Hamburger hidden;
else (< 768px — Mobile)
  :Sidebar off-screen;
  :Hamburger ☰ visible in header;
  :Content: full width;
endif

if (User taps hamburger ☰?) then (Yes)
  :Sidebar slides in (translate-x-0);
  :Backdrop overlay appears;
  if (User taps NavLink, backdrop, or ✕?) then (Yes)
    :closeSidebar() — sidebar slides out, backdrop removed;
  endif
else (No)
endif

:No horizontal overflow (min-w-0 on flex children);
stop
@enduml
```

### Wireframes

#### Desktop — Full Sidebar (≥1280px)
```plantuml
@startsalt
{
  {+
    IRIS
    CIT-U Research Hub
    --
    Research Exploration
    🧭 Discover
    🧠 Ask IRIS
    🗂 Browse Collections
    🔖 My Library
    --
    IP Management
    📝 Submit Disclosure
    💼 My Workspace
    --
    Tools
    🔔 Notifications
    📁 Storage
    ⚙ Settings & Profile
  }
  |
  {+
    (content — xl:ml-[230px])
    .
    Page content renders here
  }
}
@endsalt
```

#### Tablet — Icon-Only Rail (768–1279px)
```plantuml
@startsalt
{
  {+
    🖼
    --
    🧭
    🧠
    🗂
    🔖
    --
    📝
    💼
    --
    🔔
    📁
    ⚙
  }
  |
  {+
    (content — md:ml-[60px])
    .
    Page content renders here
  }
}
@endsalt
```

#### Mobile — Sidebar Closed (<768px)
```plantuml
@startsalt
{+
  [☰]  IRIS
  ==
  (content — full width, no left offset)
  .
  My Records Overview
  --
  {
    {+
      Draft
      --
      2
    }
    |
    {+
      Published
      --
      5
    }
  }
  .
  Recent Records
  {#
  Title                   | Status
  Smart Irrigation...     | RDCO Intake
  Blockchain Credentials  | Published
  }
}
@endsalt
```

#### Mobile — Sidebar Open (drawer + backdrop)
```plantuml
@startsalt
{
  {+
    IRIS
    CIT-U Research Hub  [✕]
    --
    🧭 Discover
    🧠 Ask IRIS
    🗂 Browse Collections
    🔖 My Library
    --
    📝 Submit Disclosure
    💼 My Workspace
    --
    🔔 Notifications
    📁 Storage
    ⚙ Settings & Profile
  }
  |
  {
    .
    fixed inset-0 bg-black/40
    (backdrop — tap to close)
    .
  }
}
@endsalt
```
