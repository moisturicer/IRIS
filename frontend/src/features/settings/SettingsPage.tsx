import { useEffect, useMemo, useState } from "react";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { DPA_SECTIONS } from "@/lib/dpaTerms";
import { cn, formatDate } from "@/lib/utils";
import { ROLE_CAPABILITIES } from "./roleCapabilities";

/**
 * Settings & Profile.
 *
 * Four tabs, not the six the mockup drew. The two that are missing were cut
 * because nothing backs them, and shipping a panel that cannot persist is the
 * dead-end IR-86's acceptance criteria forbid:
 *
 *  - **Notification preferences** — there is no preference, opt-in or opt-out
 *    model anywhere in `backend/apps/`. It also can't be a blanket switch:
 *    suppressing workflow notifications ("your disclosure was declined") would
 *    break the review loop, so it needs designed semantics, not a toggle.
 *  - **Active sessions** — `/users/sessions/` is `IsAdmin` and returns *every*
 *    user's live tokens. FR-M6-05 scopes session monitoring to administrators.
 *    A student would get a 403, and widening it would expose the whole
 *    institution's sessions. Self-service "your devices" is a different,
 *    per-user endpoint that does not exist yet.
 *
 * Both are filed rather than faked.
 */

type TabId = "profile" | "security" | "privacy" | "role";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "profile",  label: "Profile",                icon: "fa-user"         },
  { id: "security", label: "Account & security",     icon: "fa-shield-halved" },
  { id: "privacy",  label: "Data privacy & consent", icon: "fa-lock"         },
  { id: "role",     label: "Role & access",          icon: "fa-id-badge"     },
];

export default function SettingsPage() {
  const { user, updateUser } = useAuth();
  const [tab, setTab] = useState<TabId>("profile");

  if (!user) return null;

  return (
    <div className="p-4 sm:p-6 max-w-[1200px] mx-auto space-y-4">
      <header className="bg-white rounded-xl border border-stone-200 px-5 sm:px-6 py-5">
        <h1 className="text-2xl font-bold text-stone-900">Settings &amp; Profile</h1>
        <p className="text-[13px] text-stone-600 mt-1">
          {[user.first_name && `${user.first_name} ${user.last_name}`.trim(),
            user.role_name,
            user.college_name]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </header>

      <div className="flex flex-col lg:flex-row gap-4 items-start">
        <nav
          className="w-full lg:w-[260px] shrink-0 bg-white rounded-xl border border-stone-200 p-2
            flex lg:flex-col gap-1 overflow-x-auto scrollbar-thin"
          aria-label="Settings sections"
        >
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium",
                  "whitespace-nowrap transition-colors text-left",
                  active
                    ? "bg-brand-50 text-brand font-semibold"
                    : "text-stone-600 hover:bg-stone-50",
                )}
              >
                <i className={cn("fas", t.icon, "text-[12px] w-4 shrink-0")} aria-hidden />
                {t.label}
              </button>
            );
          })}
        </nav>

        <div className="flex-1 min-w-0 w-full">
          {tab === "profile"  && <ProfileTab user={user} onSaved={updateUser} />}
          {tab === "security" && <SecurityTab />}
          {tab === "privacy"  && <PrivacyTab user={user} />}
          {tab === "role"     && <RoleTab user={user} />}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Shared                                                                     */
/* -------------------------------------------------------------------------- */

function Panel({
  title, caption, children,
}: { title: string; caption: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-xl border border-stone-200 p-5 sm:p-6">
      <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-500">{title}</h2>
      <p className="text-[12px] text-stone-500 mt-1">{caption}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Field({
  label, children, hint,
}: { label: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-bold uppercase tracking-wider text-stone-500 mb-1.5">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[11px] text-stone-500 mt-1.5">{hint}</span>}
    </label>
  );
}

const inputClass =
  "w-full px-3 py-2 rounded-lg border border-stone-200 text-[13px] text-stone-900 " +
  "focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/40";

const readOnlyClass =
  "w-full px-3 py-2 rounded-lg border border-stone-200 bg-stone-50 text-[13px] text-stone-500";

function Notice({ tone, children }: { tone: "ok" | "error"; children: React.ReactNode }) {
  return (
    <p
      role="status"
      className={cn(
        "text-[12px] rounded-lg px-3 py-2 border",
        tone === "ok"
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : "bg-red-50 text-red-700 border-red-200",
      )}
    >
      {children}
    </p>
  );
}

/* -------------------------------------------------------------------------- */
/* Profile                                                                    */
/* -------------------------------------------------------------------------- */

function ProfileTab({ user, onSaved }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; onSaved: (u: typeof user) => void }) {
  const [firstName, setFirstName] = useState(user.first_name);
  const [middle,    setMiddle]    = useState(user.middle_initial ?? "");
  const [lastName,  setLastName]  = useState(user.last_name);
  const [saving,    setSaving]    = useState(false);
  const [ok,        setOk]        = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const dirty = useMemo(
    () =>
      firstName !== user.first_name ||
      middle !== (user.middle_initial ?? "") ||
      lastName !== user.last_name,
    [firstName, middle, lastName, user],
  );

  const reset = () => {
    setFirstName(user.first_name);
    setMiddle(user.middle_initial ?? "");
    setLastName(user.last_name);
    setError(null);
    setOk(false);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(false);
    if (!firstName.trim() || !lastName.trim()) {
      setError("First and last name are required.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await authApi.updateMe({
        first_name: firstName.trim(),
        middle_initial: middle.trim(),
        last_name: lastName.trim(),
      });
      onSaved(data);
      setOk(true);
    } catch {
      setError("Could not save your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  // Affiliation reaches a student and an adviser by different routes, so the
  // label has to change with the role rather than pretend it is one field.
  const affiliation = [user.college_name, user.department_name, user.course_name]
    .filter(Boolean)
    .join(" · ");

  return (
    <form onSubmit={save}>
      <Panel
        title="Profile — shown on records you author"
        caption="This identity is attached to disclosures, paper citations and clearances."
      >
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_120px_1fr] gap-4">
          <Field label="First name">
            <input className={inputClass} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </Field>
          <Field label="M.I.">
            <input className={inputClass} value={middle} onChange={(e) => setMiddle(e.target.value)} maxLength={20} />
          </Field>
          <Field label="Last name">
            <input className={inputClass} value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </Field>
        </div>

        <div className="mt-4">
          <Field
            label="Institutional email"
            hint={
              <span className="flex items-center gap-1.5">
                <i className="fas fa-circle-check text-emerald-600 text-[11px]" aria-hidden />
                {user.is_verified ? "Verified · " : ""}
                Managed by CIT-U. Your email is your sign-in identity and the name attached to
                every clearance decision, so it cannot be changed here.
              </span>
            }
          >
            <input className={readOnlyClass} value={user.email} readOnly aria-readonly />
          </Field>
        </div>

        <div className="mt-4">
          <Field
            label={user.course_name ? "College · Department · Course" : "College · Department"}
            hint="Recorded by the university. Ask RDCO if this is wrong — it is not self-service, because it determines how your disclosures are routed."
          >
            <input
              className={readOnlyClass}
              value={affiliation || "Not recorded for this account"}
              readOnly
              aria-readonly
            />
          </Field>
        </div>

        <div className="flex items-center gap-2 mt-5 pt-4 border-t border-stone-100">
          {ok && <Notice tone="ok">Profile saved.</Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={reset}
              disabled={!dirty || saving}
              className="px-3.5 py-2 rounded-lg text-[12px] font-semibold text-stone-600
                border border-stone-200 hover:bg-stone-50 disabled:opacity-40"
            >
              Discard
            </button>
            <button
              type="submit"
              disabled={!dirty || saving}
              className="px-4 py-2 rounded-lg text-[12px] font-bold uppercase tracking-wider
                bg-brand text-white hover:bg-brand-light disabled:opacity-40"
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
          </div>
        </div>
      </Panel>
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* Account & security                                                         */
/* -------------------------------------------------------------------------- */

function SecurityTab() {
  const [oldPassword,     setOldPassword]     = useState("");
  const [newPassword,     setNewPassword]     = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [ok,     setOk]     = useState(false);
  const [error,  setError]  = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setOk(false);
    setError(null);

    if (newPassword !== confirmPassword) return setError("New passwords do not match.");
    if (newPassword.length < 8)          return setError("New password must be at least 8 characters.");
    if (newPassword === oldPassword)     return setError("New password must differ from your current password.");

    setSaving(true);
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword });
      setOk(true);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const res = (err as { response?: { data?: { detail?: string; old_password?: string[] } } })?.response;
      setError(
        res?.data?.detail ??
          res?.data?.old_password?.[0] ??
          "Failed to change password. Please check your current password.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <Panel title="Account & security" caption="Change the password you use to sign in to IRIS.">
        <div className="space-y-4 max-w-md">
          <Field label="Current password">
            <input type="password" className={inputClass} value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          <Field label="New password" hint="At least 8 characters.">
            <input type="password" className={inputClass} value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
          </Field>
          <Field label="Confirm new password">
            <input type="password" className={inputClass} value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password" />
          </Field>
        </div>

        <div className="flex items-center gap-2 mt-5 pt-4 border-t border-stone-100">
          {ok && <Notice tone="ok">Password changed.</Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          <button
            type="submit"
            disabled={saving || !oldPassword || !newPassword}
            className="ml-auto px-4 py-2 rounded-lg text-[12px] font-bold uppercase tracking-wider
              bg-brand text-white hover:bg-brand-light disabled:opacity-40"
          >
            {saving ? "Changing..." : "Change password"}
          </button>
        </div>
      </Panel>
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* Data privacy & consent                                                     */
/* -------------------------------------------------------------------------- */

function PrivacyTab({ user }: { user: NonNullable<ReturnType<typeof useAuth>["user"]> }) {
  return (
    <div className="space-y-4">
      <Panel
        title="Data privacy & consent"
        caption="The consent recorded against your account under the Data Privacy Act of 2012 (RA 10173)."
      >
        <div className="flex items-start gap-3 rounded-lg border border-stone-200 p-4">
          <i
            className={cn(
              "fas text-[14px] mt-0.5",
              user.consent_given ? "fa-circle-check text-emerald-600" : "fa-circle-exclamation text-amber-600",
            )}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-stone-900">
              {user.consent_given ? "Consent on record" : "No consent recorded"}
            </p>
            <p className="text-[12px] text-stone-600 mt-0.5">
              {user.consent_given
                ? `Recorded when your account was created on ${formatDate(user.date_joined)}.`
                : "This account has no consent recorded against it."}
            </p>
          </div>
        </div>

        {/* Read-only by design. `consent_given` is read-only server-side and
            FR-M6-06 records it at registration; there is no withdrawal
            mechanism, so offering a toggle here would be a control that
            silently does nothing. The terms below say who to contact instead. */}
        <p className="text-[12px] text-stone-500 mt-3">
          Consent is recorded once, when your account is created, and cannot be changed from this
          screen. To withdraw it, contact the Research and Development Coordinating Office.
        </p>
      </Panel>

      <Panel title="What you agreed to" caption="The full notice, as shown at registration.">
        <div className="space-y-5 max-h-[420px] overflow-y-auto scrollbar-thin pr-1">
          {DPA_SECTIONS.map((section) => (
            <div key={section.title}>
              <h3 className="text-[13px] font-bold text-stone-900">{section.title}</h3>
              {"body" in section && section.body && (
                <p className="text-[12px] text-stone-600 leading-relaxed mt-1">{section.body}</p>
              )}
              {"list" in section && section.list && (
                <ul className="mt-2 space-y-1.5">
                  {section.list.map((item) => (
                    <li key={item} className="text-[12px] text-stone-600 leading-relaxed flex gap-2">
                      <span className="text-stone-300 mt-0.5" aria-hidden>—</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Role & access                                                              */
/* -------------------------------------------------------------------------- */

function RoleTab({ user }: { user: NonNullable<ReturnType<typeof useAuth>["user"]> }) {
  const capabilities = ROLE_CAPABILITIES[user.role_name ?? ""] ?? [];

  return (
    <div className="space-y-4">
      <Panel title="Role & access" caption="What your role lets you do in IRIS.">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="px-3 py-1.5 rounded-lg bg-brand text-white text-[12px] font-bold uppercase tracking-wider">
            {user.role_name ?? "No role assigned"}
          </span>
          {user.is_superuser && (
            <span className="px-2.5 py-1 rounded-md border border-stone-200 text-[11px] font-semibold text-stone-600">
              Superuser
            </span>
          )}
          {user.is_staff && !user.is_superuser && (
            <span className="px-2.5 py-1 rounded-md border border-stone-200 text-[11px] font-semibold text-stone-600">
              Django admin
            </span>
          )}
          <span className="text-[12px] text-stone-500">
            Member since {formatDate(user.date_joined)}
          </span>
        </div>

        {capabilities.length > 0 && (
          <ul className="mt-5 space-y-2">
            {capabilities.map((c) => (
              <li key={c} className="flex items-start gap-2.5 text-[12px] text-stone-700">
                <i className="fas fa-check text-emerald-600 text-[11px] mt-0.5 shrink-0" aria-hidden />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Role changes are an administrative act: RoleRequest rows are created
            at signup, and both the list and decide endpoints are Django-staff
            only. There is no self-service request endpoint to call, so this
            says who to ask rather than rendering a button that has no API. */}
        <p className="text-[12px] text-stone-500 mt-5 pt-4 border-t border-stone-100">
          Roles are assigned by a system administrator. If your role is wrong, or you need adviser
          or office access, contact the Research and Development Coordinating Office — it cannot be
          changed from this screen.
        </p>
      </Panel>
    </div>
  );
}
