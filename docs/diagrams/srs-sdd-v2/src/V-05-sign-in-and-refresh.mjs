const msg = (from, to, label) => ({ from, to, label });
const reply = (from, to, label) => ({ from, to, label, dash: true });

export default {
  kind: 'sequence',
  format: 'portrait',
  title: 'V-5  Sign in, stay signed in, and the inactivity limit',
  caption: 'From apps/accounts/views.py (LoginView, RefreshView, LogoutView), apps/accounts/refresh_cookie.py and apps/accounts/sessions.py at 2d8d4e4a (IR-1275). ADR-072, NFR-S2. The refresh token never appears in a response body or in browser storage.',
  participants: [
    { id: 'person', label: 'Person', tone: 'plain' },
    { id: 'spa', label: 'React', sub: 'access token in memory' },
    { id: 'dj', label: 'Django', sub: 'simplejwt + UserSession' },
    { id: 'db', label: 'PostgreSQL', sub: 'sessions, blacklist, audit' },
  ],
  steps: [
    msg('person', 'spa', 'email, password, optional "Keep me signed in"'),
    msg('spa', 'dj', 'POST /api/v1/auth/login/'),
    msg('dj', 'db', 'check axes lockout and throttles; verify credentials'),
    msg('dj', 'db', 'create UserSession (remembered: expires 30 days from sign-in); audit LOGIN'),
    reply('dj', 'spa', 'access token (30 min) + Set-Cookie iris_refresh (HttpOnly, Secure, SameSite=Strict, Path=/api/v1/auth/)'),
    msg('spa', 'dj', 'API calls with Authorization: Bearer <access>'),
    msg('dj', 'db', 'touch the session: last activity now'),
    msg('spa', 'dj', 'new tab or 401: POST /api/v1/auth/token/refresh/ (cookie sent by the browser, X-IRIS-Auth)'),
    msg('dj', 'db', 'check Origin; idle under 30 min, or remembered and not expired'),
    msg('dj', 'db', 'rotate: blacklist the old refresh token'),
    reply('dj', 'spa', 'new access token + rotated cookie'),
    msg('spa', 'dj', 'after 30 idle minutes (not remembered): any request or refresh'),
    msg('dj', 'db', 'end the session, reason idle'),
    reply('dj', 'spa', '401 session_idle: "Your session ended"'),
    msg('person', 'spa', 'Sign out'),
    msg('spa', 'dj', 'POST /api/v1/auth/logout/'),
    msg('dj', 'db', 'blacklist, end session (logout), audit LOGOUT'),
    reply('dj', 'spa', 'clear the cookie'),
  ],
  legend: [
    { line: 'arrow', text: 'request or write' }, { line: 'dash arrow', text: 'response' },
    'no cookie at all: 401 no_session, shown as signed out with no message',
  ],
};
