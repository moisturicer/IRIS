import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { useUIStore } from "@/store/ui.store";

// ΓöÇΓöÇ Types ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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
  college_id:     string;   // used by both roles
  course_id:      string;   // student only
  dept_id:        string;   // adviser only
}

type FieldErrors = Partial<Record<keyof FormState, string>>;

const EMPTY: FormState = {
  first_name: "", last_name: "", middle_initial: "",
  email: "",
  password: "", password2: "",
  college_id: "", course_id: "", dept_id: "",
};

// ΓöÇΓöÇ Validation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

// ΓöÇΓöÇ Component ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
export default function SignupPage() {
  const navigate     = useNavigate();
  const { addToast } = useUIStore();

  const [role, setRole]         = useState<Role>("Student");
  const [form, setForm]         = useState<FormState>(EMPTY);
  const [errors, setErrors]     = useState<FieldErrors>({});
  const [touched, setTouched]   = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [terms, setTerms]       = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // ΓöÇΓöÇ Reference data from API ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const [colleges,    setColleges]    = useState<College[]>([]);
  const [allDepts,    setAllDepts]    = useState<Department[]>([]);
  const [allCourses,  setAllCourses]  = useState<Course[]>([]);
  const [loadingRef,  setLoadingRef]  = useState(true);

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
  }, []);

  // ΓöÇΓöÇ Derived dropdowns ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const collegeNum = Number(form.college_id);

  // Adviser: departments filtered by selected college
  const filteredDepts = allDepts.filter((d) => d.college === collegeNum);

  // Student: courses filtered by selected college (via dept join)
  const deptIdsForCollege = new Set(filteredDepts.map((d) => d.id));
  const filteredCourses   = allCourses.filter((c) => deptIdsForCollege.has(c.department));

  // Group filtered courses by department name for <optgroup>
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

  // ΓöÇΓöÇ Field change ΓÇö instant validation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const handleChange = (name: keyof FormState, value: string) => {
    const next = { ...form, [name]: value };
    // Reset dependent dropdowns when college changes
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

  // ΓöÇΓöÇ Submit ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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
        role_name:        role === "Adviser" ? "Faculty Adviser" : role,
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

  // ΓöÇΓöÇ Role tab switch ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const switchRole = (r: Role) => {
    setRole(r);
    setForm((prev) => ({ ...prev, course_id: "", dept_id: "" }));
    setErrors((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
    setTouched((prev) => { const n = { ...prev }; delete n.course_id; delete n.dept_id; return n; });
  };

  // ΓöÇΓöÇ Style helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const cls = (name: keyof FormState) => {
    const isError = touched[name] && errors[name];
    const isValid = touched[name] && !errors[name] && form[name];
    return [
      "w-full border rounded-lg px-3.5 py-2.5 text-[14px] outline-none",
      "transition-colors placeholder:text-gray-400 bg-gray-50 font-[inherit]",
      isError ? "border-red-400 bg-red-50 focus:border-red-500"
        : isValid ? "border-green-400 bg-white focus:border-green-500"
        : "border-gray-300 focus:border-[#6B0F12] focus:bg-white",
    ].join(" ");
  };

  const errMsg = (name: keyof FormState) =>
    touched[name] && errors[name]
      ? <p className="text-[11px] text-red-600 mt-1">{errors[name]}</p>
      : null;

  const chevron = (
    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none text-[13px]">Γû╛</span>
  );

  // ΓöÇΓöÇ Render ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'Inter', sans-serif" }}>

      {/* ΓöÇΓöÇ Left panel ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      <div className="hidden md:flex md:w-[38%] bg-[#6B0F12] flex-col justify-between relative overflow-hidden"
           style={{ padding: "60px 48px", minHeight: "100vh" }}>
        <div className="absolute rounded-full bg-white/[0.04]" style={{ width: 340, height: 340, top: -80, right: -100 }} />
        <div className="absolute rounded-full bg-white/[0.06]" style={{ width: 260, height: 260, bottom: 60, left: -80 }} />
        <div className="absolute rounded-full bg-white/[0.04]" style={{ width: 180, height: 180, bottom: 200, right: 20 }} />
        <div className="relative z-10">
          <h1 className="text-[52px] font-extrabold text-white leading-tight">Join the<br />Network</h1>
          <p className="text-[14px] mt-3 leading-relaxed" style={{ color: "rgba(255,255,255,0.65)" }}>
            Secure your innovations with IRIS.
          </p>
        </div>
        <div className="relative z-10 text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
          <div>Intelligent Research &amp; IP System</div>
          <div>┬⌐ 2026 Cebu Institute of Technology - University</div>
        </div>
      </div>

      {/* ΓöÇΓöÇ Right panel ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      <div className="flex-1 flex items-start justify-center overflow-y-auto" style={{ padding: "48px 40px" }}>
        <div style={{ width: "100%", maxWidth: 480, paddingBottom: 48 }}>

          <div className="text-center mb-6">
            <div className="text-[38px] font-extrabold tracking-[6px] text-[#6B0F12]">IRIS</div>
            <p className="text-[13px] text-gray-500 mt-1">Intelligent Research &amp; IP System</p>
          </div>

          <h2 className="text-[22px] font-bold text-gray-900 text-center mb-5">Create Account</h2>

          {/* Role tabs */}
          <div className="flex gap-2 mb-5">
            {(["Student", "Adviser"] as Role[]).map((r) => (
              <button key={r} type="button" onClick={() => switchRole(r)}
                className={`flex-1 py-2 border rounded-lg text-[13px] font-medium transition-all
                  ${role === r
                    ? "border-[#6B0F12] text-[#6B0F12] bg-red-50"
                    : "border-gray-300 text-gray-500 bg-gray-50 hover:border-[#6B0F12] hover:text-[#6B0F12]"}`}>
                {r === "Adviser" ? "Faculty / Adviser" : r}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>

            {/* ΓöÇΓöÇ Name row ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr 76px" }}>
              <div>
                <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                  First Name <span className="text-red-500">*</span>
                </label>
                <input value={form.first_name} onChange={(e) => handleChange("first_name", e.target.value)}
                  onBlur={() => handleBlur("first_name")} placeholder="Juan" className={cls("first_name")} />
                {errMsg("first_name")}
              </div>
              <div>
                <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                  Last Name <span className="text-red-500">*</span>
                </label>
                <input value={form.last_name} onChange={(e) => handleChange("last_name", e.target.value)}
                  onBlur={() => handleBlur("last_name")} placeholder="Dela Cruz" className={cls("last_name")} />
                {errMsg("last_name")}
              </div>
              <div>
                <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">M.I.</label>
                <input value={form.middle_initial} onChange={(e) => handleChange("middle_initial", e.target.value)}
                  onBlur={() => handleBlur("middle_initial")} placeholder="S." maxLength={10}
                  className={cls("middle_initial")} />
                {errMsg("middle_initial")}
              </div>
            </div>

            {/* ΓöÇΓöÇ Email ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                CIT-U Email <span className="text-red-500">*</span>
              </label>
              <input type="email" value={form.email} onChange={(e) => handleChange("email", e.target.value)}
                onBlur={() => handleBlur("email")} placeholder="you@cit.edu" className={cls("email")} />
              {errMsg("email")}
            </div>

            {/* ΓöÇΓöÇ College (both roles) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                College <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <select value={form.college_id} onChange={(e) => handleChange("college_id", e.target.value)}
                  onBlur={() => handleBlur("college_id")}
                  disabled={loadingRef}
                  className={`${cls("college_id")} appearance-none pr-9 disabled:opacity-50`}>
                  <option value="">{loadingRef ? "LoadingΓÇª" : "Select college"}</option>
                  {colleges.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                {chevron}
              </div>
              {errMsg("college_id")}
            </div>

            {/* ΓöÇΓöÇ Program (Student) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            {role === "Student" && (
              <div>
                <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                  Program <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <select value={form.course_id} onChange={(e) => handleChange("course_id", e.target.value)}
                    onBlur={() => handleBlur("course_id")}
                    disabled={!form.college_id}
                    className={`${cls("course_id")} appearance-none pr-9 disabled:opacity-50 disabled:cursor-not-allowed`}>
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
                  {chevron}
                </div>
                {errMsg("course_id")}
              </div>
            )}

            {/* ΓöÇΓöÇ Department (Adviser) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            {role === "Adviser" && (
              <div>
                <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                  Department <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <select value={form.dept_id} onChange={(e) => handleChange("dept_id", e.target.value)}
                    onBlur={() => handleBlur("dept_id")}
                    disabled={!form.college_id}
                    className={`${cls("dept_id")} appearance-none pr-9 disabled:opacity-50 disabled:cursor-not-allowed`}>
                    <option value="">
                      {!form.college_id ? "Select college first" : filteredDepts.length === 0 ? "No departments available" : "Select department"}
                    </option>
                    {filteredDepts.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                  {chevron}
                </div>
                {errMsg("dept_id")}
              </div>
            )}

            {/* ΓöÇΓöÇ Password ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                Password <span className="text-red-500">*</span>
              </label>
              <input type="password" value={form.password} onChange={(e) => handleChange("password", e.target.value)}
                onBlur={() => handleBlur("password")} placeholder="At least 8 characters" className={cls("password")} />
              {form.password && !errors.password && (
                <p className="text-[11px] text-green-600 mt-1">Γ£ô Password looks good.</p>
              )}
              {errMsg("password")}
            </div>

            {/* ΓöÇΓöÇ Confirm password ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                Confirm Password <span className="text-red-500">*</span>
              </label>
              <input type="password" value={form.password2} onChange={(e) => handleChange("password2", e.target.value)}
                onBlur={() => handleBlur("password2")} placeholder="Re-enter password" className={cls("password2")} />
              {form.password2 && !errors.password2 && (
                <p className="text-[11px] text-green-600 mt-1">Γ£ô Passwords match.</p>
              )}
              {errMsg("password2")}
            </div>

            {/* ΓöÇΓöÇ Terms ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div className="flex items-start gap-2.5 mt-1">
              <input type="checkbox" id="terms" checked={terms} onChange={(e) => setTerms(e.target.checked)}
                className="mt-0.5 w-4 h-4 shrink-0 accent-[#6B0F12] cursor-pointer" />
              <label htmlFor="terms" className="text-[12px] text-gray-500 leading-relaxed cursor-pointer">
                I agree to the IRIS{" "}
                <a href="#" className="text-[#6B0F12] font-medium hover:underline">Terms of Service</a>
                {" "}and{" "}
                <a href="#" className="text-[#6B0F12] font-medium hover:underline">Data Privacy Policy</a>.
              </label>
            </div>

            <button type="submit" disabled={submitting || !terms}
              className="w-full py-3 rounded-lg text-[15px] font-semibold text-white transition-colors
                bg-[#6B0F12] hover:bg-[#7d1215] disabled:bg-gray-300 disabled:cursor-not-allowed mt-1">
              {submitting ? "Creating accountΓÇª" : "Create Account"}
            </button>
          </form>

          <p className="text-[13px] text-gray-500 text-center mt-5">
            Already have an account?{" "}
            <Link to="/login" className="text-[#6B0F12] font-semibold hover:underline">Sign in</Link>
          </p>

        </div>
      </div>
    </div>
  );
}
