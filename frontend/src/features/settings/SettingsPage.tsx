import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import { PageHeader } from "@/components/layout/PageHeader";
import { RoleBadge } from "@/components/shared/RoleBadge";

export default function SettingsPage() {
  const { user } = useAuth();

  const [oldPassword, setOldPassword]       = useState("");
  const [newPassword, setNewPassword]       = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving]                 = useState(false);
  const [success, setSuccess]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess(false);
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword === oldPassword) {
      setError("New password must differ from your current password.");
      return;
    }

    setSaving(true);
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword });
      setSuccess(true);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string; old_password?: string[] } } })?.response
          ?.data?.detail ??
        (err as { response?: { data?: { old_password?: string[] } } })?.response?.data
          ?.old_password?.[0] ??
        "Failed to change password. Please check your current password.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <PageHeader title="Settings & Profile" />

      {/* Profile card */}
      <div className="mt-6 bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-[13px] font-bold text-gray-700 uppercase tracking-wider mb-4">
          Account Information
        </h2>
        <div className="flex items-center gap-4 mb-5">
          <div className="w-14 h-14 rounded-full bg-[#6B0F12] text-white flex items-center justify-center text-[18px] font-bold flex-shrink-0">
            {`${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase() || "?"}
          </div>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-gray-900 truncate">
              {user?.first_name} {user?.middle_initial ? `${user.middle_initial}. ` : ""}{user?.last_name}
            </p>
            <p className="text-[12px] text-gray-500 truncate mt-0.5">{user?.email}</p>
            {user?.role_name && (
              <div className="mt-1.5">
                <RoleBadge role={user.role_name} />
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-[12px]">
          <div className="bg-gray-50 rounded-lg px-3 py-2.5 border border-gray-100">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">First Name</p>
            <p className="text-gray-800 font-medium">{user?.first_name || "—"}</p>
          </div>
          <div className="bg-gray-50 rounded-lg px-3 py-2.5 border border-gray-100">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">Last Name</p>
            <p className="text-gray-800 font-medium">{user?.last_name || "—"}</p>
          </div>
          <div className="col-span-2 bg-gray-50 rounded-lg px-3 py-2.5 border border-gray-100">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">Email</p>
            <p className="text-gray-800 font-medium">{user?.email || "—"}</p>
          </div>
        </div>
      </div>

      {/* Change password card */}
      <div className="mt-4 bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-[13px] font-bold text-gray-700 uppercase tracking-wider mb-1">
          Change Password
        </h2>
        <p className="text-[12px] text-gray-500 mb-5">
          Choose a strong password with at least 8 characters.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
              Current Password
            </label>
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-[13px] focus:outline-none focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]/20"
              placeholder="Enter your current password"
            />
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
              New Password
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-[13px] focus:outline-none focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]/20"
              placeholder="At least 8 characters"
            />
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-gray-700 mb-1.5">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-[13px] focus:outline-none focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]/20"
              placeholder="Repeat new password"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 px-3 py-2.5 bg-red-50 border border-red-200 rounded-lg">
              <i className="fas fa-exclamation-circle text-red-500 text-[12px] mt-0.5 flex-shrink-0" />
              <p className="text-[12px] text-red-700">{error}</p>
            </div>
          )}

          {success && (
            <div className="flex items-center gap-2 px-3 py-2.5 bg-green-50 border border-green-200 rounded-lg">
              <i className="fas fa-check-circle text-green-500 text-[12px] flex-shrink-0" />
              <p className="text-[12px] text-green-700 font-medium">Password changed successfully.</p>
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full py-2.5 bg-[#6B0F12] text-white rounded-lg text-[13px] font-semibold hover:bg-[#850f13] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <span className="flex items-center justify-center gap-2">
                <i className="fas fa-spinner fa-spin text-[12px]" />
                Updating…
              </span>
            ) : (
              "Update Password"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
