import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useUIStore } from "@/store/ui.store";
import irisLogo from "@/assets/images/iris_logo.png";

const schema = z
  .object({
    fullName: z.string().min(1, "Full name is required."),
    email:    z.string().min(1, "Email is required.").email("Enter a valid email address."),
    password: z.string().min(8, "Password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Please confirm your password."),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  })
  .refine((d) => d.fullName.trim().split(/\s+/).length >= 2, {
    message: "Enter your first and last name.",
    path: ["fullName"],
  });

type FormData = z.infer<typeof schema>;

const inputBase =
  "w-full rounded-lg px-4 py-3 text-[14px] bg-[#F3F3F3] outline-none transition-colors placeholder:text-gray-400 text-gray-900 border border-transparent focus:border-brand focus:bg-white";

function parseFullName(full: string): { first_name: string; last_name: string } {
  const parts = full.trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) {
    return { first_name: parts[0] ?? "", last_name: "" };
  }
  return { first_name: parts[0], last_name: parts.slice(1).join(" ") };
}

export default function SignupPage() {
  const navigate     = useNavigate();
  const { addToast } = useUIStore();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    const { first_name, last_name } = parseFullName(data.fullName);
    const email = data.email.trim();

    try {
      await authApi.register({
        username:         email,
        first_name,
        last_name,
        email,
        password:         data.password,
        confirm_password: data.confirmPassword,
        role_name:        "Student",
      });

      addToast({
        type:    "success",
        message: "Account created! Check your email to verify your account.",
      });
      navigate("/login");
    } catch (err: unknown) {
      const res = (err as { response?: { data?: Record<string, unknown> } }).response?.data;
      if (res && typeof res === "object") {
        const fieldMap: Record<string, keyof FormData> = {
          username: "email",
          email:    "email",
          first_name: "fullName",
          last_name:  "fullName",
          password: "password",
          confirm_password: "confirmPassword",
        };
        for (const [key, val] of Object.entries(res)) {
          const formKey = fieldMap[key];
          const message = Array.isArray(val) ? (val[0] as string) : String(val);
          if (formKey) setError(formKey, { message });
        }
        const first = Object.values(res)[0];
        const msg = Array.isArray(first) ? (first[0] as string) : String(first);
        if (msg) addToast({ type: "error", message: msg });
      } else {
        addToast({ type: "error", message: "Registration failed. Please try again." });
      }
    }
  };

  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans">

      {/* ── Left: branding ─────────────────────────────────────────── */}
      <div className="relative lg:w-1/2 bg-cream flex flex-col justify-between overflow-hidden px-8 py-10 sm:px-12 lg:px-14 lg:py-12 min-h-[360px] lg:min-h-screen">

        <div className="absolute rounded-full bg-white/60 pointer-events-none"
             style={{ width: 280, height: 280, top: -60, right: -40 }} />
        <div className="absolute rounded-full bg-white/40 pointer-events-none"
             style={{ width: 200, height: 200, bottom: 100, left: -50 }} />
        <div className="absolute rounded-full bg-white/50 pointer-events-none"
             style={{ width: 160, height: 160, top: "45%", right: 30 }} />

        <div className="relative z-10 flex-1 flex flex-col">
          <div className="flex items-center gap-3">
            <img src={irisLogo} alt="" className="h-11 w-11 object-contain shrink-0" />
            <span className="text-[22px] font-extrabold text-brand tracking-wide">IRIS</span>
          </div>

          <h1 className="mt-10 sm:mt-14 font-serif leading-[1.05]">
            <span className="block text-[42px] sm:text-[48px] font-bold text-gold">The</span>
            <span className="block text-[42px] sm:text-[48px] font-bold text-brand">
              Academic
            </span>
            <span className="block text-[42px] sm:text-[48px] font-bold text-brand">
              Curator.
            </span>
          </h1>

          <p className="mt-6 text-[14px] sm:text-[15px] text-brand/90 leading-relaxed max-w-md">
            Welcome to the Digital Vault of CIT-U Intellectual Property. A prestigious archive
            for students and researchers to safeguard and manage their academic assets.
          </p>

          <blockquote className="mt-8 pl-5 border-l-4 border-gold max-w-md">
            <p className="font-serif italic text-[15px] sm:text-[16px] text-brand leading-relaxed">
              &ldquo;Transforming complex IP data into a high-end editorial experience that feels
              as permanent as a physical archive.&rdquo;
            </p>
            <footer className="mt-3 text-[11px] font-semibold tracking-[0.1em] text-gold uppercase">
              Cebu Institute of Technology – University
            </footer>
          </blockquote>
        </div>

        <p className="relative z-10 text-[11px] text-gray-400 mt-10">
          © 2026 Cebu Institute of Technology - University
        </p>
      </div>

      {/* ── Right: signup form ─────────────────────────────────────── */}
      <div className="flex-1 lg:w-1/2 bg-white flex items-center justify-center px-8 py-12 sm:px-12 lg:px-16">
        <div className="w-full max-w-[400px]">

          <h2 className="text-[28px] font-bold text-gray-900">Create an Account</h2>
          <p className="mt-2 text-[14px] text-gray-500 mb-8">
            Enter your details to register for IRIS.
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>

            <div>
              <label htmlFor="signup-fullname" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Full Name
              </label>
              <input
                id="signup-fullname"
                {...register("fullName")}
                autoComplete="name"
                placeholder="e.g. Juan Dela Cruz"
                className={`${inputBase} ${errors.fullName ? "border-red-400 bg-red-50" : ""}`}
              />
              {errors.fullName && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.fullName.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="signup-email" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Email Address
              </label>
              <input
                id="signup-email"
                {...register("email")}
                type="email"
                autoComplete="email"
                placeholder="student@cit.edu"
                className={`${inputBase} ${errors.email ? "border-red-400 bg-red-50" : ""}`}
              />
              {errors.email && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="signup-password" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  id="signup-password"
                  {...register("password")}
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  placeholder="••••••••"
                  className={`${inputBase} pr-16 ${errors.password ? "border-red-400 bg-red-50" : ""}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[13px] font-semibold text-brand hover:underline"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.password.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="signup-confirm" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Confirm Password
              </label>
              <input
                id="signup-confirm"
                {...register("confirmPassword")}
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                className={`${inputBase} ${errors.confirmPassword ? "border-red-400 bg-red-50" : ""}`}
              />
              {errors.confirmPassword && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.confirmPassword.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3.5 rounded-lg text-[15px] font-semibold text-white transition-colors
                bg-gold hover:bg-gold-dark disabled:bg-gray-300 disabled:cursor-not-allowed mt-1"
            >
              {isSubmitting ? "Registering…" : "Register"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-gray-200 text-center">
            <p className="text-[14px] text-gray-500">
              Already have an account?{" "}
              <Link to="/login" className="font-semibold text-brand hover:underline">
                Sign in
              </Link>
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}
