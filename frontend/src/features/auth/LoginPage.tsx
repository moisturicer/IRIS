import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { useUIStore } from "@/store/ui.store";

const schema = z.object({
  email:    z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

type FormData = z.infer<typeof schema>;

export default function LoginPage() {
  const navigate     = useNavigate();
  const { login }    = useAuth();
  const { addToast } = useUIStore();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      const res = await authApi.login(data);
      login(res.data.user, res.data.access, res.data.refresh);
      navigate("/");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      addToast({ type: "error", message: detail ?? "Invalid credentials." });
    }
  };

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'Inter', sans-serif" }}>

      {/* ── Left panel ─────────────────────────────────────────────── */}
      <div className="hidden md:flex md:w-[38%] bg-[#6B0F12] flex-col justify-between relative overflow-hidden"
           style={{ padding: "60px 48px", minHeight: "100vh" }}>
        {/* Decorative blobs */}
        <div className="absolute rounded-full bg-white/[0.04]"
             style={{ width: 340, height: 340, top: -80, right: -100 }} />
        <div className="absolute rounded-full bg-white/[0.06]"
             style={{ width: 260, height: 260, bottom: 60, left: -80 }} />
        <div className="absolute rounded-full bg-white/[0.04]"
             style={{ width: 180, height: 180, bottom: 200, right: 20 }} />

        <div className="relative z-10">
          <h1 className="text-[52px] font-extrabold text-white leading-tight">
            Welcome<br />Back
          </h1>
          <p className="text-[14px] mt-3 leading-relaxed" style={{ color: "rgba(255,255,255,0.65)" }}>
            Sign in to access your research<br />and IP records.
          </p>
        </div>

        <div className="relative z-10 text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
          <div>Intelligent Research &amp; IP System</div>
          <div>© 2026 Cebu Institute of Technology - University</div>
        </div>
      </div>

      {/* ── Right panel ─────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center overflow-y-auto"
           style={{ padding: "48px 40px" }}>
        <div style={{ width: "100%", maxWidth: 420 }}>

          {/* Logo / brand */}
          <div className="text-center mb-7">
            <div className="text-[38px] font-extrabold tracking-[6px] text-[#6B0F12]">IRIS</div>
            <p className="text-[13px] text-gray-500 mt-1">Intelligent Research &amp; IP System</p>
          </div>

          <h2 className="text-[22px] font-bold text-gray-900 text-center mb-6">Sign In</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">

            {/* Email */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                Email Address
              </label>
              <input
                {...register("email")}
                type="email"
                placeholder="you@cit.edu"
                className={`w-full border rounded-lg px-3.5 py-2.5 text-[14px] bg-gray-50 outline-none
                  transition-colors placeholder:text-gray-400
                  ${errors.email
                    ? "border-red-400 bg-red-50 focus:border-red-500"
                    : "border-gray-300 focus:border-[#6B0F12] focus:bg-white"}`}
              />
              {errors.email && (
                <p className="text-[11px] text-red-600 mt-1">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
                Password
              </label>
              <input
                {...register("password")}
                type="password"
                placeholder="Your password"
                className={`w-full border rounded-lg px-3.5 py-2.5 text-[14px] bg-gray-50 outline-none
                  transition-colors placeholder:text-gray-400
                  ${errors.password
                    ? "border-red-400 bg-red-50 focus:border-red-500"
                    : "border-gray-300 focus:border-[#6B0F12] focus:bg-white"}`}
              />
              {errors.password && (
                <p className="text-[11px] text-red-600 mt-1">{errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 rounded-lg text-[15px] font-semibold text-white transition-colors
                bg-[#6B0F12] hover:bg-[#7d1215] disabled:bg-gray-300 disabled:cursor-not-allowed mt-1"
            >
              {isSubmitting ? "Signing in..." : "Sign In"}
            </button>
          </form>

          <p className="text-[13px] text-gray-500 text-center mt-5">
            No account?{" "}
            <Link to="/signup" className="text-[#6B0F12] font-semibold hover:underline">
              Sign up
            </Link>
          </p>

        </div>
      </div>
    </div>
  );
}
