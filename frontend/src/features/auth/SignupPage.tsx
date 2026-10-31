import { useState, useEffect, useId, useRef, useCallback, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { EntryFrame } from "@/components/auth/EntryFrame";
import { EntrySteps, type EntryStep } from "@/components/auth/EntrySteps";
import { Button, ButtonLink, Input, Select } from "@/components/ui";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
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

type FieldName   = keyof FormState;
type FieldErrors = Partial<Record<FieldName, string>>;

const EMPTY: FormState = {
  first_name: "", last_name: "", middle_initial: "",
  email: "",
  password: "", password2: "",
  college_id: "", course_id: "", dept_id: "",
};

/** The three steps, in order, and the fields each one owns (IR-704). */
const STEPS: { name: string; shortName?: string; fields: FieldName[] }[] = [
  { name: "Identity",             fields: ["first_name", "last_name", "middle_initial", "email"] },
  { name: "Affiliation",          fields: ["college_id", "course_id", "dept_id"] },
  { name: "Security & agreement", shortName: "Security", fields: ["password", "password2"] },
];
const LAST_STEP = STEPS.length - 1;

/**
 * The register serializer's error keys, onto the fields they mean (IR-540). Two
 * are named differently on the server; `consent_given` belongs to the consent
 * box. Anything else -- `non_field_errors`, `detail`, `role_name` -- is shown
 * as an alert, because no field here can own it.
 */
const SERVER_FIELD: Record<string, FieldName> = {
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

/** "Adviser", not "Faculty / Adviser": the role's name, not a job title (CONTEXT.md). */
const ROLES: Role[] = ["Student", "Adviser"];

const LEDE = {
  headline: <>Begin with your <span className="text-brand">research identity.</span></>,
  sentence: "Register once with your CIT-U email. You verify the address, then RDCO reviews the role you ask for.",
};

const CROSS_LINK = { prompt: "Already have an account?", label: "Sign in", to: "/login" };

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

/** Only the errors on one step's fields. */
function stepErrors(all: FieldErrors, step: number): FieldErrors {
  const e: FieldErrors = {};
  for (const name of STEPS[step].fields) if (all[name]) e[name] = all[name];
  return e;
}

const hasAny = (e: FieldErrors) => Object.values(e).some(Boolean);

// ── Component ──────────────────────────────────────────────────────────────
export default function SignupPage() {

  const [role, setRole]             = useState<Role>("Student");
  const [form, setForm]             = useState<FormState>(EMPTY);
  const [step, setStep]             = useState(0);
  const [errors, setErrors]         = useState<FieldErrors>({});
  const [touched, setTouched]       = useState<Partial<Record<FieldName, boolean>>>({});
  const [consented, setConsented]   = useState(false);
  const [consentError, setConsentError] = useState<string>();
  const [formAlert, setFormAlert]   = useState<FormAlert | null>(null);
  // The server's refusals, kept apart from the screen's own checks (IR-708): a
  // blur re-runs those, and must not erase a message only the server can give.
  // Each one stays on its field, and keeps its step open, until that field changes.
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  // The step a refusal brought the registrant back to, which says so while open.
  const [returnedTo, setReturnedTo] = useState<number | null>(null);
  // Set when the role changes after an affiliation was chosen, and said on
  // Affiliation until the new program or department is picked (IR-704 story 28).
  const [roleChangedTo, setRoleChangedTo] = useState<Role | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const noticeTriggerId = useId();
  const noticeId        = useId();
  const consentErrorId  = useId();
  const nextStepsId     = useId();
  const summaryId       = useId();
  const { pathname }    = useLocation();
  // Set once the account exists: the screen then confirms in place instead of
  // leaving on a toast (IR-540), naming the address exactly as it was entered.
  const [registered, setRegistered] = useState<{ email: string; role: Role } | null>(null);
  const confirmationRef = useRef<HTMLHeadingElement>(null);
  const stepHeadingRef  = useRef<HTMLHeadingElement>(null);
  // Focus follows a step change, never the first render: arriving on the page
  // must not pull focus past the masthead.
  const stepChanged = useRef(false);

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
  useEffect(() => {
    if (stepChanged.current) stepHeadingRef.current?.focus();
  }, [step]);

  const goTo = (next: number) => {
    stepChanged.current = true;
    setReturnedTo(null);
    setStep(next);
  };

  // Completion is derived from the answers every render, never stored, so a
  // change that invalidates a step reopens it at once (IR-704).
  const allErrors = validateAll(form, role);
  const complete = STEPS.map((_, i) =>
    !hasAny(stepErrors(allErrors, i)) && (i !== LAST_STEP || consented),
  );
  // A server refusal reopens only its own step (IR-708): the steps after it
  // were answered and checked, so they stay completed and reachable.
  const refused = STEPS.map((_, i) => hasAny(stepErrors(serverErrors, i)));

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

  const handleChange = (name: FieldName, value: string) => {
    const next = { ...form, [name]: value };
    if (name === "college_id") { next.course_id = ""; next.dept_id = ""; }
    if ((name === "course_id" || name === "dept_id") && value) setRoleChangedTo(null);
    setServerErrors((prev) => {
      const n = { ...prev };
      delete n[name];
      if (name === "college_id") { delete n.course_id; delete n.dept_id; }
      return n;
    });
    setForm(next);
    setTouched((prev) => ({ ...prev, [name]: true }));
    const liveErrs = validateLive(next, role);
    const patch: FieldErrors = { [name]: liveErrs[name] };
    if (name === "password" && next.password2) patch.password2 = liveErrs.password2;
    setErrors((prev) => ({ ...prev, ...patch }));
  };

  const handleBlur = (name: FieldName) => {
    setTouched((prev) => ({ ...prev, [name]: true }));
    const errs = validateAll(form, role);
    setErrors((prev) => ({ ...prev, [name]: errs[name] }));
  };

  /** Shows one step's errors, as Continue and Register do. */
  const revealStep = (i: number, errs: FieldErrors) => {
    const fields = STEPS[i].fields;
    setTouched((prev) => ({ ...prev, ...Object.fromEntries(fields.map((k) => [k, true])) }));
    setErrors((prev) => ({ ...prev, ...Object.fromEntries(fields.map((k) => [k, errs[k]])) }));
  };

  /** Continue checks the step on screen and nothing after it (IR-704 story 18). */
  const handleContinue = () => {
    const errs = validateAll(form, role);
    revealStep(step, errs);
    if (hasAny(stepErrors(errs, step)) || refused[step]) return;
    goTo(step + 1);
  };

  const handleRegister = async () => {
    const errs = validateAll(form, role);
    // Consent is checked with the fields, not after them, so one press of
    // Register shows everything that is missing at once (IR-540).
    setConsentError(consented ? undefined : CONSENT_REQUIRED);
    revealStep(LAST_STEP, errs);
    // The tabs never reach Security past an incomplete step, so this is a
    // guard: whatever got here, an incomplete form is never sent, and the
    // registrant is taken to the earliest step that needs them.
    // A refusal not yet answered by a change counts too: the same request
    // would only be refused again.
    const earliest = STEPS.findIndex((_, i) => hasAny(stepErrors(errs, i)) || refused[i]);
    if (earliest !== -1 && earliest < LAST_STEP) {
      revealStep(earliest, errs);
      goTo(earliest);
      return;
    }
    if (earliest !== -1 || !consented) return;

    setFormAlert(null);
    setReturnedTo(null);
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
      setServerErrors(onFields);
      // Anything no field owns stays here on Security, as an alert above Register.
      if (elsewhere.length) setFormAlert({ title: "Registration failed", message: elsewhere.join(" ") });
      // The registrant goes to the earliest step a refusal names (IR-708);
      // every answer is kept, and the steps after it stay completed.
      const owning = STEPS.findIndex((s) => s.fields.some((name) => onFields[name]));
      if (owning !== -1 && owning < LAST_STEP) {
        goTo(owning);
        setReturnedTo(owning);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (step < LAST_STEP) handleContinue();
    else void handleRegister();
  };

  const switchRole = (r: Role) => {
    if (form.college_id || form.course_id || form.dept_id) setRoleChangedTo(r);
    setRole(r);
    setForm((prev) => ({ ...prev, course_id: "", dept_id: "" }));
    setServerErrors((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
    setErrors((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
    setTouched((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
  };

  // An error shows once its field has been touched, as before IR-539; the
  // primitives then make it the field's description and mark it invalid. A
  // server refusal shows until the field changes (IR-708).
  const field = (name: FieldName) => ({
    value:    form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      handleChange(name, e.target.value),
    onBlur:   () => handleBlur(name),
    error:    serverErrors[name] ?? (touched[name] && errors[name] ? errors[name] : undefined),
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
      <EntryFrame
        crossLink={CROSS_LINK}
        lede={LEDE}
        wide
        tabs={<EntrySteps steps={STEPS.map(({ name, shortName }) => ({ name, shortName, state: "completed" }))} />}
      >
        <div className="max-w-2xl">
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
          <ButtonLink to="/login" size="full" className="mt-section-lg">
            Go to sign in
          </ButtonLink>
        </div>
      </EntryFrame>
    );
  }

  // A step counts as completed only when every step before it is too: a later
  // step finished earlier cannot be reached past one an answer has reopened
  // (IR-704 story 17).
  const tabs: EntryStep[] = STEPS.map(({ name, shortName }, i) => ({
    name,
    shortName,
    state: i === step
      ? "current"
      : complete.slice(0, i + 1).every(Boolean) && !refused[i] ? "completed" : "not-started",
  }));

  const roleArticle = role === "Adviser" ? "an Adviser" : "a Student";
  const fullName = [form.first_name.trim(), form.middle_initial.trim(), form.last_name.trim()]
    .filter(Boolean).join(" ");

  // What sits under the step heading in the left column, beside the fields.
  const aside: ReactNode = [
    <>Use the email you were given by CIT-U. We send a verification link to it.</>,
    <>
      Registering as <strong className="font-semibold text-stone-900">{roleArticle}</strong>
      {fullName && <>: {fullName}</>}{form.email.trim() && <>, {form.email.trim()}</>}.
    </>,
    null,
  ][step];

  // Step 3's summary (IR-708): what will be sent, minus the passwords, each
  // line with a way back to the step that asked for it. Names, not ids.
  const affiliationName = role === "Student"
    ? allCourses.find((c) => String(c.id) === form.course_id)?.name
    : allDepts.find((d) => String(d.id) === form.dept_id)?.name;
  const summary: { term: string; value: string; owner: number }[] = [
    { term: "Role",    value: role,            owner: 0 },
    { term: "Name",    value: fullName,        owner: 0 },
    { term: "Email",   value: form.email.trim(), owner: 0 },
    { term: "College", value: colleges.find((c) => String(c.id) === form.college_id)?.name ?? "", owner: 1 },
    { term: role === "Student" ? "Program" : "Department", value: affiliationName ?? "", owner: 1 },
  ];

  return (
    <EntryFrame
      crossLink={CROSS_LINK}
      lede={LEDE}
      wide
      tabs={<EntrySteps steps={tabs} onSelect={goTo} />}
    >
      <form onSubmit={handleSubmit} noValidate className="grid gap-section lg:grid-cols-5 lg:gap-12">
        <div className="lg:col-span-2">
          <h2 className="text-balance font-display text-display font-semibold text-stone-900">
            Create an Account
          </h2>
          <h3
            ref={stepHeadingRef}
            tabIndex={-1}
            className="mt-1 text-small font-semibold text-brand outline-none"
          >
            Step {step + 1} of {STEPS.length} · {STEPS[step].name}
          </h3>
          {aside && (
            <p className="mt-section border-t border-stone-200 pt-section text-body text-stone-700">
              {aside}
            </p>
          )}
          {step === LAST_STEP && (
            <section aria-labelledby={summaryId} className="mt-section border-t border-stone-200 pt-section">
              <h4 id={summaryId} className="text-small font-semibold text-stone-900">Check your details</h4>
              <dl className="mt-2 divide-y divide-stone-200">
                {summary.map(({ term, value, owner }) => (
                  // dt and dd sit directly in the div, as a dl group must; the
                  // Change link rides in the dd beside the value it changes.
                  <div key={term} className="py-1">
                    <dt className="text-label font-semibold uppercase tracking-wide text-stone-600">{term}</dt>
                    <dd className="flex items-center gap-3">
                      <span className="min-w-0 flex-1 break-words text-small text-stone-900">{value}</span>
                      <Link
                        to={pathname}
                        onClick={(e) => { e.preventDefault(); goTo(owner); }}
                        className={cn(
                          "inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded text-small font-semibold text-brand hover:underline",
                          FOCUS_RING,
                        )}
                      >
                        {/* The space sits outside the hidden part: a name computed
                            from a child's text trims the child's own leading space. */}
                        Change{" "}<span className="sr-only">{term.toLowerCase()}</span>
                      </Link>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>

        <div key={step} className="flex flex-col gap-5 motion-safe:animate-step-fade lg:col-span-3">
          {returnedTo === step && (
            <AuthAlert variant="error" title={`We brought you back to ${STEPS[step].name}`}>
              IRIS couldn&apos;t register you with what&apos;s marked below. Change it and register
              again; everything else you entered is kept.
            </AuthAlert>
          )}

          {loadFailed && step === 1 && (
            <AuthAlert variant="error" title="Some of this form didn't load">
              IRIS couldn&apos;t load the colleges, programs and departments to choose from.
              <div className="mt-3">
                <Button type="button" variant="outline" size="full" onClick={loadOptions}>
                  Try again
                </Button>
              </div>
            </AuthAlert>
          )}

          {step === 0 && (
            <>
              {/* A real radio group (IR-539): it announces its question, both
                  choices and which one is chosen, and the arrow keys move
                  between them. */}
              <fieldset role="radiogroup">
                <legend className="mb-1 text-sm font-medium text-stone-700">I am registering as</legend>
                <div className="grid grid-cols-2 gap-2">
                  {ROLES.map((value) => (
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
                      {value}
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="grid gap-5 sm:grid-cols-5 sm:gap-3">
                <div className="sm:col-span-2">
                  <Input id="signup-first-name" label="First Name" required
                    autoComplete="given-name" {...field("first_name")} />
                </div>
                <div className="sm:col-span-2">
                  <Input id="signup-last-name" label="Last Name" required
                    autoComplete="family-name" {...field("last_name")} />
                </div>
                <Input id="signup-middle-initial" label="M.I." maxLength={10}
                  {...field("middle_initial")} />
              </div>

              <Input id="signup-email" label="CIT-U Email" required type="email"
                autoComplete="email" {...field("email")} />
            </>
          )}

          {step === 1 && (
            <>
              {roleChangedTo && (
                <div role="status" className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3 text-stone-800">
                  <p className="font-semibold">Your role changed to {roleChangedTo}</p>
                  <p className="mt-1 text-small">
                    Your college is kept. Choose a {roleChangedTo === "Adviser" ? "department" : "program"} instead
                    of a {roleChangedTo === "Adviser" ? "program" : "department"}.
                  </p>
                </div>
              )}

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
            </>
          )}

          {step === LAST_STEP && (
            <>
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

              {/* Consent against a notice on this page (IR-540), in place of
                  links to a Terms of Service and a Data Privacy Policy that do
                  not exist yet (IR-214). The notice opens in place, so reading
                  it clears nothing. */}
              <div className="border-t border-stone-200 pt-5">
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
                  <label htmlFor="signup-consent" className="flex min-h-11 items-center cursor-pointer text-small text-stone-600">
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
            </>
          )}

          {/* The forward action first in the source, so a phone reads it
              first; from `sm` up Back sits on its left. `size="full"` carries
              the 44px step. */}
          <div className="flex flex-col gap-3 sm:flex-row-reverse">
            <div className="sm:flex-1">
              {step < LAST_STEP ? (
                <Button type="submit" variant="primary" size="full">
                  {step === 0 ? "Continue to affiliation" : "Continue to security"}
                </Button>
              ) : (
                <Button type="submit" variant="primary" size="full" loading={submitting}>
                  {submitting ? "Creating account…" : "Register"}
                </Button>
              )}
            </div>
            {step > 0 && (
              <div className="sm:w-28 sm:shrink-0">
                <Button type="button" variant="outline" size="full" onClick={() => goTo(step - 1)}>
                  Back
                </Button>
              </div>
            )}
          </div>
        </div>
      </form>

      <div className="mt-section-lg border-t border-stone-200 pt-section">
        <p className="text-center text-sm text-stone-600">
          Already have an account?{" "}
          <Link
            to="/login"
            className={cn(
              "inline-flex min-h-11 min-w-11 items-center justify-center rounded font-semibold text-brand hover:underline",
              FOCUS_RING,
            )}
          >
            Sign in
          </Link>
        </p>
      </div>
    </EntryFrame>
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
