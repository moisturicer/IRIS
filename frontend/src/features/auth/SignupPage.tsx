import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { useUIStore } from "@/store/ui.store";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Input, Select } from "@/components/ui";

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
  const navigate     = useNavigate();
  const { addToast } = useUIStore();

  const [role, setRole]             = useState<Role>("Student");
  const [form, setForm]             = useState<FormState>(EMPTY);
  const [errors, setErrors]         = useState<FieldErrors>({});
  const [touched, setTouched]       = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [terms, setTerms]           = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword]   = useState(false);
  const [showPassword2, setShowPassword2] = useState(false);

  const [colleges,   setColleges]   = useState<College[]>([]);
  const [allDepts,   setAllDepts]   = useState<Department[]>([]);
  const [allCourses, setAllCourses] = useState<Course[]>([]);
  const [loadingRef, setLoadingRef] = useState(true);

  useEffect(() => {
    Promise.all([
      accountsApi.colleges(),
      accountsApi.departments(),
      accountsApi.courses(),
    ]).then(([colRes, deptRes, courseRes]) => {
      setColleges(colRes.data.results);
      setAllDepts(deptRes.data.results);
      setAllCourses(courseRes.data.results);
    }).catch(() => {
      addToast({ type: "error", message: "Failed to load form options. Please refresh." });
    }).finally(() => setLoadingRef(false));
  }, [addToast]);

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
    if (Object.values(errs).some(Boolean)) return;
    if (!terms) {
      addToast({ type: "error", message: "Please agree to the Terms of Service." });
      return;
    }

    setSubmitting(true);
    try {
      await authApi.register({
        email:            form.email.trim(),
        first_name:       form.first_name.trim(),
        middle_initial:   form.middle_initial.trim() || undefined,
        last_name:        form.last_name.trim(),
        password:         form.password,
        confirm_password: form.password2,
        role_name:        role,
        ...(role === "Student"
          ? { course_id: Number(form.course_id) }
          : { college_id: Number(form.college_id), department_id: Number(form.dept_id) }),
      });
      addToast({ type: "success", message: "Account created! Check your email to verify your account." });
      navigate("/login");
    } catch (err: unknown) {
      const data = (err as { response?: { data?: Record<string, unknown> } }).response?.data;
      if (data && typeof data === "object") {
        const mapped: FieldErrors = {};
        for (const [key, val] of Object.entries(data)) {
          mapped[key as keyof FormState] = Array.isArray(val) ? (val[0] as string) : String(val);
        }
        setErrors((prev) => ({ ...prev, ...mapped }));
        const first = Object.values(mapped)[0];
        if (first) addToast({ type: "error", message: first });
      } else {
        addToast({ type: "error", message: "Registration failed. Please try again." });
      }
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

  return (
    <AuthLayout variant="signup" wide>
      <h2 className="text-balance font-display text-display font-semibold text-stone-900">
        Create an Account
      </h2>
      <p className="mt-2 mb-section text-body text-stone-600">
        Enter your details to register for IRIS.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
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

        {/* The consent line's wording and links are IR-540's to replace. */}
        <div className="flex items-start gap-2.5 pt-1">
          <input
            type="checkbox"
            id="terms"
            checked={terms}
            onChange={(e) => setTerms(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-brand"
          />
          <label htmlFor="terms" className="cursor-pointer text-small text-stone-600">
            I agree to the IRIS{" "}
            <a href="#" className="font-semibold text-brand hover:underline">Terms of Service</a>
            {" "}and{" "}
            <a href="#" className="font-semibold text-brand hover:underline">Data Privacy Policy</a>.
          </label>
        </div>

        {/* `size="full"` carries the width and the 44px step. Maroon under
            white is 12.3:1 at rest and 9.5:1 on hover; gold was 2.76:1. */}
        <Button type="submit" variant="primary" size="full" loading={submitting} disabled={!terms}>
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
