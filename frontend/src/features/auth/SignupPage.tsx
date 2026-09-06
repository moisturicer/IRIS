import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { useUIStore } from "@/store/ui.store";
import { AuthLayout } from "@/components/auth/AuthLayout";

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

const INPUT_BASE =
  "w-full rounded-lg px-4 py-3 text-[14px] bg-[#F3F3F3] outline-none transition-colors placeholder:text-gray-500 text-gray-900 border font-[inherit]";

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

  const cls = (name: keyof FormState) => {
    const isError = touched[name] && errors[name];
    const isValid = touched[name] && !errors[name] && form[name];
    return [
      INPUT_BASE,
      isError
        ? "border-brand bg-red-50/50 focus:border-brand focus:bg-white"
        : isValid
          ? "border-green-400/60 bg-white focus:border-brand"
          : "border-transparent focus:border-brand focus:bg-white",
    ].join(" ");
  };

  const errMsg = (name: keyof FormState) =>
    touched[name] && errors[name]
      ? <p className="text-[12px] text-red-600 mt-1.5">{errors[name]}</p>
      : null;

  const labelCls = "block text-[13px] font-semibold text-gray-900 mb-2";

  return (
    <AuthLayout variant="signup" wide>
      <h2 className="text-[28px] font-bold text-gray-900">Create an Account</h2>
      <p className="mt-2 text-[14px] text-gray-500 mb-6">
        Enter your details to register for IRIS.
      </p>

      {/* Role tabs */}
      <div className="flex gap-2 mb-6">
        {(["Student", "Adviser"] as Role[]).map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => switchRole(r)}
            className={`flex-1 py-2.5 rounded-lg text-[13px] font-semibold transition-all border ${
              role === r
                ? "border-brand text-brand bg-cream"
                : "border-gray-200 text-gray-500 bg-[#F3F3F3] hover:border-brand/40 hover:text-brand"
            }`}
          >
            {r === "Adviser" ? "Faculty / Adviser" : r}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_76px]">
          <div>
            <label className={labelCls}>
              First Name <span className="text-red-500">*</span>
            </label>
            <input
              value={form.first_name}
              onChange={(e) => handleChange("first_name", e.target.value)}
              onBlur={() => handleBlur("first_name")}
              placeholder="Juan"
              className={cls("first_name")}
            />
            {errMsg("first_name")}
          </div>
          <div>
            <label className={labelCls}>
              Last Name <span className="text-red-500">*</span>
            </label>
            <input
              value={form.last_name}
              onChange={(e) => handleChange("last_name", e.target.value)}
              onBlur={() => handleBlur("last_name")}
              placeholder="Dela Cruz"
              className={cls("last_name")}
            />
            {errMsg("last_name")}
          </div>
          <div>
            <label className={labelCls}>M.I.</label>
            <input
              value={form.middle_initial}
              onChange={(e) => handleChange("middle_initial", e.target.value)}
              onBlur={() => handleBlur("middle_initial")}
              placeholder="S."
              maxLength={10}
              className={cls("middle_initial")}
            />
            {errMsg("middle_initial")}
          </div>
        </div>

        <div>
          <label className={labelCls}>
            CIT-U Email <span className="text-red-500">*</span>
          </label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => handleChange("email", e.target.value)}
            onBlur={() => handleBlur("email")}
            placeholder="you@cit.edu"
            className={cls("email")}
          />
          {errMsg("email")}
        </div>

        <div>
          <label className={labelCls}>
            College <span className="text-red-500">*</span>
          </label>
          <select
            value={form.college_id}
            onChange={(e) => handleChange("college_id", e.target.value)}
            onBlur={() => handleBlur("college_id")}
            disabled={loadingRef}
            className={`${cls("college_id")} appearance-none disabled:opacity-50`}
          >
            <option value="">{loadingRef ? "Loading…" : "Select college"}</option>
            {colleges.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          {errMsg("college_id")}
        </div>

        {role === "Student" && (
          <div>
            <label className={labelCls}>
              Program <span className="text-red-500">*</span>
            </label>
            <select
              value={form.course_id}
              onChange={(e) => handleChange("course_id", e.target.value)}
              onBlur={() => handleBlur("course_id")}
              disabled={!form.college_id}
              className={`${cls("course_id")} appearance-none disabled:opacity-50 disabled:cursor-not-allowed`}
            >
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
            </select>
            {errMsg("course_id")}
          </div>
        )}

        {role === "Adviser" && (
          <div>
            <label className={labelCls}>
              Department <span className="text-red-500">*</span>
            </label>
            <select
              value={form.dept_id}
              onChange={(e) => handleChange("dept_id", e.target.value)}
              onBlur={() => handleBlur("dept_id")}
              disabled={!form.college_id}
              className={`${cls("dept_id")} appearance-none disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              <option value="">
                {!form.college_id ? "Select college first" : filteredDepts.length === 0 ? "No departments available" : "Select department"}
              </option>
              {filteredDepts.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            {errMsg("dept_id")}
          </div>
        )}

        <div>
          <label className={labelCls}>
            Password <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={form.password}
              onChange={(e) => handleChange("password", e.target.value)}
              onBlur={() => handleBlur("password")}
              placeholder="At least 8 characters"
              className={`${cls("password")} pr-16`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[13px] font-semibold text-brand hover:underline"
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          {form.password && !errors.password && (
            <p className="text-[11px] text-green-600 mt-1.5">Password looks good.</p>
          )}
          {errMsg("password")}
        </div>

        <div>
          <label className={labelCls}>
            Confirm Password <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <input
              type={showPassword2 ? "text" : "password"}
              value={form.password2}
              onChange={(e) => handleChange("password2", e.target.value)}
              onBlur={() => handleBlur("password2")}
              placeholder="Re-enter password"
              className={`${cls("password2")} pr-16`}
            />
            <button
              type="button"
              onClick={() => setShowPassword2((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[13px] font-semibold text-brand hover:underline"
            >
              {showPassword2 ? "Hide" : "Show"}
            </button>
          </div>
          {form.password2 && !errors.password2 && (
            <p className="text-[11px] text-green-600 mt-1.5">Passwords match.</p>
          )}
          {errMsg("password2")}
        </div>

        <div className="flex items-start gap-2.5 pt-1">
          <input
            type="checkbox"
            id="terms"
            checked={terms}
            onChange={(e) => setTerms(e.target.checked)}
            className="mt-0.5 w-4 h-4 shrink-0 accent-brand cursor-pointer"
          />
          <label htmlFor="terms" className="text-[12px] text-gray-500 leading-relaxed cursor-pointer">
            I agree to the IRIS{" "}
            <a href="#" className="text-brand font-semibold hover:underline">Terms of Service</a>
            {" "}and{" "}
            <a href="#" className="text-brand font-semibold hover:underline">Data Privacy Policy</a>.
          </label>
        </div>

        <button
          type="submit"
          disabled={submitting || !terms}
          className="w-full py-3.5 rounded-lg text-[15px] font-semibold text-white transition-colors bg-gold hover:bg-gold-dark disabled:bg-gray-300 disabled:cursor-not-allowed mt-1"
        >
          {submitting ? "Creating account…" : "Register"}
        </button>
      </form>

      <div className="mt-8 pt-6 border-t border-gray-100">
        <p className="text-[13px] text-gray-500 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-brand font-semibold hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
