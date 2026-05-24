/**
 * Shown to authenticated users whose role request has not yet been approved.
 * Replaces the full app shell — no sidebar, no navigation.
 */
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import irisLogo from "@/assets/images/iris_logo.png";

export function PendingApprovalPage() {
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    try {
      const refresh = localStorage.getItem("refresh_token") ?? "";
      await authApi.logout(refresh);
    } catch {
      // ignore — we log out regardless
    }
    logout();
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      {/* Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm w-full max-w-md p-8 flex flex-col items-center text-center gap-5">

        {/* Logo + branding */}
        <div className="flex items-center gap-3 mb-1">
          <img src={irisLogo} alt="IRIS" className="w-10 h-10 object-contain" />
          <div className="text-left">
            <div className="text-[22px] font-extrabold tracking-[4px] text-[#6B0F12] leading-none">
              IRIS
            </div>
            <div className="text-[9px] font-bold tracking-[2px] text-amber-600 uppercase mt-0.5">
              CIT-U Research Hub
            </div>
          </div>
        </div>

        {/* Icon */}
        <div className="w-16 h-16 rounded-full bg-amber-50 border border-amber-100 flex items-center justify-center">
          <i className="fas fa-hourglass-half text-[28px] text-amber-500" />
        </div>

        {/* Heading */}
        <div>
          <h1 className="text-[18px] font-bold text-gray-900">
            Account Pending Approval
          </h1>
          <p className="text-[13px] text-gray-500 mt-1.5 leading-relaxed">
            Your registration was received and your email has been verified.
            An administrator will review and approve your account shortly.
          </p>
        </div>

        {/* User info */}
        {user && (
          <div className="w-full rounded-lg bg-gray-50 border border-gray-100 px-4 py-3 text-left">
            <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-1">
              Registered as
            </p>
            <p className="text-[13px] font-semibold text-gray-800">
              {user.first_name} {user.last_name}
            </p>
            <p className="text-[12px] text-gray-500">{user.email}</p>
          </div>
        )}

        {/* What to expect */}
        <div className="w-full text-left space-y-2">
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
            What happens next
          </p>
          <div className="flex items-start gap-2.5 text-[12px] text-gray-600">
            <i className="fas fa-envelope text-[#6B0F12] mt-0.5 w-4 flex-shrink-0" />
            <span>You will receive an email notification once your account is approved.</span>
          </div>
          <div className="flex items-start gap-2.5 text-[12px] text-gray-600">
            <i className="fas fa-sign-in-alt text-[#6B0F12] mt-0.5 w-4 flex-shrink-0" />
            <span>After approval, log back in to access the full IRIS platform.</span>
          </div>
          <div className="flex items-start gap-2.5 text-[12px] text-gray-600">
            <i className="fas fa-clock text-[#6B0F12] mt-0.5 w-4 flex-shrink-0" />
            <span>Approvals are typically processed within 1–2 business days.</span>
          </div>
        </div>

        {/* Logout */}
        <button
          type="button"
          onClick={handleLogout}
          className="mt-1 w-full py-2.5 rounded-lg border border-gray-200 text-[13px] font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
        >
          Sign out
        </button>
      </div>

      <p className="mt-5 text-[11px] text-gray-400">
        Questions? Contact the RDCO office or your department administrator.
      </p>
    </div>
  );
}
