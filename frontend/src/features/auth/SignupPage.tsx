import { useState, useEffect, useId, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Input, Select } from "@/components/ui";
import { FOCUS_RING } from "@/components/ui/interaction";
import { DataNotice } from "./DataNotice";

// ── Types ──────────────────────────────────────────────────────────────────
type Role = "Student" | "Adviser";

interface College    { id: number; name: string; code: string; }
interface Department { id: number; name: string; college: number; }
interface Course     { id: number; name: string; department: number; }

interface FormState {
  first_name:     string;
  last_name:      string;
  middle_initial: string;
  email:          string;
  password:       string;
  password2:      string;
  college_id:     string;
  course_id:      string;
  dept_id:        string;
}

type FieldErrors = Partial<Record<keyof FormState, string>>;

const EMPTY: FormState = {
  first_name: "", last_name: "", middle_initial: "",
  email: "",
  password: "", password2: "",
  college_id: "", course_id: "", dept_id: "",
};

/**
 * The register serializer's error keys, onto the fields they mean (IR-540). Two
 * are named differently on the server; `consent_given` belongs to the consent
 * box. Anything else -- `non_field_errors`, `detail`, `role_name` -- is shown
 * as an alert, because no field here can own it.
 */
const SERVER_FIELD: Record<string, keyof FormState> = {
  email:            "email",
  first_name:       "first_name",
  last_name:        "last_name",
  middle_initial:   "middle_initial",
  password:         "password",
  confirm_password: "password2",
  college_id:       "college_id",
  course_id:        "course_id",
  department_id:    "dept_id",
};

interface FormAlert { title: string; message: string; }

/** A reply with nothing to say about the fields: none came, or the server failed. */
const UNREACHABLE: FormAlert = {
  title:   "IRIS can't be reached right now",
  message: "This is a connection or server problem, not a problem with what you typed. Try again shortly.",
};

const firstMessage = (val: unknown) => (Array.isArray(val) ? String(val[0]) : String(val));

/** Every message on a field, so a password refused for two reasons says both (IR-647). */
const allMessages = (val: unknown) => (Array.isArray(val) ? val.map(String).join(" ") : String(val));

/** The consent box's own error, shown on it when a submit arrives without it (IR-540). */
const CONSENT_REQUIRED = "Agree to the data notice to register.";

const ROLES: { value: Role; label: string }[] = [
  { value: "Student", label: "Student" },
  { value: "Adviser", label: "Faculty / Adviser" },
];

// ── Validation ─────────────────────────────────────────────────────────────
function validateAll(f: FormState, role: Role): FieldErrors {
  const e: FieldErrors = {};

  if (!f.first_name.trim()) e.first_name = "First name is required.";
  if (!f.last_name.trim())  e.last_name  = "Last name is required.";
  if (f.middle_initial.trim() && !f.middle_initial.trim().endsWith("."))
    e.middle_initial = "Missing (.).";

  if (!f.email.trim())      e.email = "Email is required.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email))
    e.email = "Enter a valid email address.";

  if (!f.password)          e.password = "Password is required.";
  else if (f.password.length < 8)
    e.password = "Password must be at least 8 characters.";

  if (!f.password2)         e.password2 = "Please confirm your password.";
  else if (f.password2 !== f.password)
    e.password2 = "Passwords do not match.";

  if (!f.college_id)        e.college_id = "Please select your college.";

  if (role === "Student" && !f.course_id)
    e.course_id = "Please select your program.";
  if (role === "Adviser" && !f.dept_id)
    e.dept_id = "Please select your department.";

  return e;
}

function validateLive(f: FormState, role: Role): FieldErrors {
  const e = validateAll(f, role);
  if (!f.password2) delete e.password2;
  return e;
}

// ── Component ──────────────────────────────────────────────────────────────
export default function SignupPage() {

  const [role, setRole]             = useState<Role>("Student");
  const [form, setForm]             = useState<FormState>(EMPTY);
  const [errors, setErrors]         = useState<FieldErrors>({});
  const [touched, setTouched]       = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [consented, setConsented]   = useState(false);
  const [consentError, setConsentError] = useState<string>();
  const [formAlert, setFormAlert]   = useState<FormAlert | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const noticeTriggerId = useId();
  const noticeId        = useId();
  const consentErrorId  = useId();
  const nextStepsId     = useId();
  // Set once the account exists: the screen then confirms in place instead of
  // leaving on a toast (IR-540), naming the address exactly as it was entered.
  const [registered, setRegistered] = useState<{ email: string; role: Role } | null>(null);
  const confirmationRef = useRef<HTMLHeadingElement>(null);

  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword]   = useState(false);
  const [showPassword2, setShowPassword2] = useState(false);

  const [colleges,   setColleges]   = useState<College[]>([]);
  const [allDepts,   setAllDepts]   = useState<Department[]>([]);
  const [allCourses, setAllCourses] = useState<Course[]>([]);
  const [loadingRef, setLoadingRef] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  // A failure is said inside the form, with a retry that keeps what was typed
  // (IR-540), in place of a toast that left three empty selects behind it.
  const loadOptions = useCallback(() => {
    setLoadingRef(true);
    setLoadFailed(false);
    Promise.all([
      accountsApi.colleges(),
      accountsApi.departments(),
      accountsApi.courses(),
    ]).then(([colRes, deptRes, courseRes]) => {
      setColleges(colRes.data.results);
      setAllDepts(deptRes.data.results);
      setAllCourses(courseRes.data.results);
    }).catch(() => {
      setLoadFailed(true);
    }).finally(() => setLoadingRef(false));
  }, []);

  useEffect(loadOptions, [loadOptions]);
  // The form a screen-reader user was in has just gone, so their focus goes
  // to what replaced it.
  useEffect(() => {
    if (registered) confirmationRef.current?.focus();
  }, [registered]);

  const collegeNum = Number(form.college_id);
  const filteredDepts = allDepts.filter((d) => d.college === collegeNum);
  const deptIdsForCollege = new Set(filteredDepts.map((d) => d.id));
  const filteredCourses   = allCourses.filter((c) => deptIdsForCollege.has(c.department));

  const deptMap = new Map(allDepts.map((d) => [d.id, d]));
  const courseGroups: { deptName: string; courses: Course[] }[] = [];
  const seenDepts = new Set<number>();
  for (const c of filteredCourses) {
    if (!seenDepts.has(c.department)) {
      seenDepts.add(c.department);
      courseGroups.push({
        deptName: deptMap.get(c.department)?.name ?? `Dept ${c.department}`,
        courses:  filteredCourses.filter((x) => x.department === c.department),
      });
    }
  }

  const handleChange = (name: keyof FormState, value: string) => {
    const next = { ...form, [name]: value };
    if (name === "college_id") { next.course_id = ""; next.dept_id = ""; }
    setForm(next);
    setTouched((prev) => ({ ...prev, [name]: true }));
    const liveErrs = validateLive(next, role);
    const patch: FieldErrors = { [name]: liveErrs[name] };
    if (name === "password" && next.password2) patch.password2 = liveErrs.password2;
    setErrors((prev) => ({ ...prev, ...patch }));
  };

  const handleBlur = (name: keyof FormState) => {
    setTouched((prev) => ({ ...prev, [name]: true }));
    const errs = validateAll(form, role);
    setErrors((prev) => ({ ...prev, [name]: errs[name] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const allKeys = Object.keys(EMPTY) as (keyof FormState)[];
    setTouched(allKeys.reduce((acc, k) => ({ ...acc, [k]: true }), {}));
    const errs = validateAll(form, role);
    setErrors(errs);
    // Consent is checked with the fields, not after them, so one press of
    // Register shows everything that is missing at once (IR-540).
    setConsentError(consented ? undefined : CONSENT_REQUIRED);
    if (Object.values(errs).some(Boolean) || !consented) return;

    setFormAlert(null);
    setSubmitting(true);
    try {
      await authApi.register({
        email:            form.email.trim(),
        first_name:       form.first_name.trim(),
        middle_initial:   form.middle_initial.trim() || undefined,
        last_name:        form.last_name.trim(),
        password:         form.password,
        confirm_password: form.password2,
        // Required by the register serializer, and never sent before IR-540:
        // every registration from this screen was refused until it was.
        consent_given:    true,
        role_name:        role,
        ...(role === "Student"
          ? { course_id: Number(form.course_id) }
          : { college_id: Number(form.college_id), department_id: Number(form.dept_id) }),
      });
      setRegistered({ email: form.email.trim(), role });
    } catch (err: unknown) {
      const response = (err as { response?: { status?: number; data?: unknown } }).response;
      const data = response?.data;
      if (!response || (response.status ?? 0) >= 500 || !data || typeof data !== "object") {
        setFormAlert(UNREACHABLE);
        return;
      }
      const onFields: FieldErrors = {};
      const elsewhere: string[] = [];
      for (const [key, val] of Object.entries(data as Record<string, unknown>)) {
        if (key === "consent_given") setConsentError(firstMessage(val));
        else if (SERVER_FIELD[key]) onFields[SERVER_FIELD[key]] = allMessages(val);
        else elsewhere.push(firstMessage(val));
      }
      setErrors((prev) => ({ ...prev, ...onFields }));
      if (elsewhere.length) setFormAlert({ title: "Registration failed", message: elsewhere.join(" ") });
    } finally {
      setSubmitting(false);
    }
  };

  const switchRole = (r: Role) => {
    setRole(r);
    setForm((prev) => ({ ...prev, course_id: "", dept_id: "" }));
    setErrors((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
    setTouched((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
  };

  // An error shows once its field has been touched, as before IR-539; the
  // primitives then make it the field's description and mark it invalid.
  const field = (name: keyof FormState) => ({
    value:    form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      handleChange(name, e.target.value),
    onBlur:   () => handleBlur(name),
    error:    touched[name] && errors[name] ? errors[name] : undefined,
    size:     "lg" as const,
  });

  // Feedback in words, with the check as decoration (IR-539): the hint says
  // the same thing whether or not its colour or its glyph is seen.
  const passwordHint = form.password.length >= 8
    ? <><i className="fas fa-check mr-1.5" aria-hidden />At least 8 characters</>
    : "At least 8 characters";
  const password2Hint = form.password2 && form.password2 === form.password
    ? <><i className="fas fa-check mr-1.5" aria-hidden />Passwords match</>
    : undefined;

  if (registered) {
    return (
      <AuthLayout variant="signup" wide>
        <h2
          ref={confirmationRef}
          tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none"
        >
          Check your email
        </h2>
        <p className="mt-3 text-pretty text-body text-stone-700">
          Your account was created. We sent a verification link to{" "}
          <strong className="font-semibold text-stone-900">{registered.email}</strong>.
        </p>
        <ol className="mt-section list-decimal space-y-2 pl-5 text-body text-stone-700">
          <li>Open the link in that email to verify your address.</li>
          <li>
            RDCO reviews your request to join as {registered.role === "Adviser" ? "an Adviser" : "a Student"}, and
            emails you when they decide.
          </li>
        </ol>
        {/* Not "contact RDCO": an email is read-only to every IRIS screen,
            RDCO's included, so the only fix IRIS offers is a fresh registration. */}
        <p className="mt-section text-small text-stone-600">
          If that address is wrong, register again with the right one.
        </p>
        <Link
          to="/login"
          // Drawn as the primary action, since it is the only one left. Button
          // cannot render as a link yet (IR-538 adds that); until then this
          // copies its `primary` + `full` look, in type-role sizes.
          className={`mt-section-lg flex min-h-11 w-full items-center justify-center rounded-lg bg-brand px-5 py-3.5 text-heading font-medium text-white transition-colors hover:bg-brand-light ${FOCUS_RING}`}
        >
          Go to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout variant="signup" wide>
      <h2 className="text-balance font-display text-display font-semibold text-stone-900">
        Create an Account
      </h2>
      <p className="mt-2 mb-section text-body text-stone-600">
        Enter your details to register for IRIS.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        {loadFailed && (
          <AuthAlert variant="error" title="Some of this form didn't load">
            IRIS couldn&apos;t load the colleges, programs and departments to choose from.
            <div className="mt-3">
              <Button type="button" variant="outline" size="full" onClick={loadOptions}>
                Try again
              </Button>
            </div>
          </AuthAlert>
        )}

        {/* A real radio group (IR-539): it announces its question, both
            choices and which one is chosen, and the arrow keys move between
            them. The two buttons it replaces announced no state at all. */}
        <fieldset role="radiogroup">
          <legend className="mb-1 text-sm font-medium text-stone-700">I am registering as</legend>
          <div className="grid grid-cols-2 gap-2">
            {ROLES.map(({ value, label }) => (
              <label
                key={value}
                className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-lg border px-4 py-2.5
                  text-sm font-semibold transition-colors
                  ${role === value
                    ? "border-brand bg-brand-50 text-brand"
                    : "border-stone-300 bg-surface text-stone-700 hover:border-stone-400"}`}
              >
                <input
                  type="radio"
                  name="register-role"
                  value={value}
                  checked={role === value}
                  onChange={() => switchRole(value)}
                  className="h-4 w-4 shrink-0 cursor-pointer accent-brand"
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-5 sm:grid-cols-5 sm:gap-3">
          <div className="sm:col-span-2">
            <Input id="signup-first-name" label="First Name" required placeholder="Juan"
              autoComplete="given-name" {...field("first_name")} />
          </div>
          <div className="sm:col-span-2">
            <Input id="signup-last-name" label="Last Name" required placeholder="Dela Cruz"
              autoComplete="family-name" {...field("last_name")} />
          </div>
          <Input id="signup-middle-initial" label="M.I." placeholder="S." maxLength={10}
            {...field("middle_initial")} />
        </div>

        <Input id="signup-email" label="CIT-U Email" required type="email" placeholder="you@cit.edu"
          autoComplete="email" {...field("email")} />

        <Select id="signup-college" label="College" required disabled={loadingRef} {...field("college_id")}>
          <option value="">{loadingRef ? "Loading…" : "Select college"}</option>
          {colleges.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </Select>

        {role === "Student" && (
          <Select id="signup-program" label="Program" required disabled={!form.college_id} {...field("course_id")}>
            <option value="">
              {!form.college_id ? "Select college first" : filteredCourses.length === 0 ? "No programs available" : "Select program"}
            </option>
            {courseGroups.map(({ deptName, courses }) => (
              <optgroup key={deptName} label={deptName}>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </optgroup>
            ))}
          </Select>
        )}

        {role === "Adviser" && (
          <Select id="signup-department" label="Department" required disabled={!form.college_id} {...field("dept_id")}>
            <option value="">
              {!form.college_id ? "Select college first" : filteredDepts.length === 0 ? "No departments available" : "Select department"}
            </option>
            {filteredDepts.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </Select>
        )}

        <Input
          id="signup-password"
          label="Password"
          required
          type={showPassword ? "text" : "password"}
          autoComplete="new-password"
          // No placeholder: the hint below already says it, and says it while typing.
          hint={passwordHint}
          {...field("password")}
          trailing={
            <PasswordToggle
              shown={showPassword}
              onToggle={() => setShowPassword((v) => !v)}
              what="password"
            />
          }
        />

        <Input
          id="signup-password2"
          label="Confirm Password"
          required
          type={showPassword2 ? "text" : "password"}
          autoComplete="new-password"
          placeholder="Re-enter password"
          hint={password2Hint}
          {...field("password2")}
          trailing={
            <PasswordToggle
              shown={showPassword2}
              onToggle={() => setShowPassword2((v) => !v)}
              what="confirmed password"
            />
          }
        />

        {/* Consent against a notice on this page (IR-540), in place of links to
            a Terms of Service and a Data Privacy Policy that do not exist yet
            (IR-214). The notice opens in place, so reading it clears nothing. */}
        <div className="pt-1">
          <div className="flex items-start gap-2.5">
            <input
              type="checkbox"
              id="signup-consent"
              checked={consented}
              onChange={(e) => {
                setConsented(e.target.checked);
                if (e.target.checked) setConsentError(undefined);
              }}
              aria-invalid={consentError ? true : undefined}
              aria-describedby={consentError ? consentErrorId : undefined}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-brand"
            />
            <label htmlFor="signup-consent" className="cursor-pointer text-small text-stone-600">
              I have read the data notice and agree to IRIS using my details as it describes.
            </label>
          </div>
          {consentError && (
            <p id={consentErrorId} className="mt-1.5 flex items-start gap-1.5 text-small text-brand">
              <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
              {consentError}
            </p>
          )}
          <button
            type="button"
            id={noticeTriggerId}
            aria-expanded={noticeOpen}
            aria-controls={noticeId}
            onClick={() => setNoticeOpen((v) => !v)}
            // 44px tall, as sign-in's "Forgot password?" is (2.5.5).
            className={`mt-1 inline-flex min-h-11 items-center gap-1.5 rounded text-small font-semibold text-brand hover:underline ${FOCUS_RING}`}
          >
            <i className={`fas ${noticeOpen ? "fa-chevron-up" : "fa-chevron-down"} text-label`} aria-hidden />
            Read the data notice
          </button>
          {noticeOpen && (
            <div
              id={noticeId}
              role="region"
              aria-labelledby={noticeTriggerId}
              className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3"
            >
              <DataNotice />
            </div>
          )}
        </div>

        {formAlert && (
          <AuthAlert variant="error" title={formAlert.title}>
            {formAlert.message}
          </AuthAlert>
        )}

        {/* Said before anything is sent, so the wait after it surprises no one (IR-533). */}
        <div>
          <p id={nextStepsId} className="text-small font-semibold text-stone-700">What happens next</p>
          <ol aria-labelledby={nextStepsId} className="mt-1 list-decimal space-y-0.5 pl-5 text-small text-stone-600">
            <li>You verify your email with the link we send you.</li>
            <li>RDCO reviews your request, and emails you when they decide.</li>
          </ol>
        </div>

        {/* `size="full"` carries the width and the 44px step. Maroon under
            white is 12.3:1 at rest and 9.5:1 on hover; gold was 2.76:1. */}
        <Button type="submit" variant="primary" size="full" loading={submitting}>
          {submitting ? "Creating account…" : "Register"}
        </Button>
      </form>

      <div className="mt-section-lg border-t border-stone-200 pt-section">
        <p className="text-center text-sm text-stone-600">
          Already have an account?{" "}
          <Link to="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}

/**
 * The show/hide toggle in a password field's trailing slot, as on sign in
 * (IR-204). Its accessible name begins with the word it shows, so "click Show"
 * still matches for a voice user (2.5.3), and its box is 44 by 44 (2.5.5).
 */
function PasswordToggle({ shown, onToggle, what }: { shown: boolean; onToggle: () => void; what: string }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={`${shown ? "Hide" : "Show"} ${what}`}
      className="flex min-h-11 min-w-11 items-center justify-center px-1 text-sm font-semibold text-brand hover:underline"
    >
      {shown ? "Hide" : "Show"}
    </button>
  );
}
