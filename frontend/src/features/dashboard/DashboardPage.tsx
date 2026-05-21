import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { pipelineLabel } from "@/lib/utils";

interface DashboardStats {
  total_mine:      number;
  pending_mine:    number;
  approved_mine:   number;
  declined_mine:   number;
  total_published: number;
}

function StatCard({ label, value, to, color }: { label: string; value: number; to: string; color: string }) {
  return (
    <Link to={to} className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow">
      <div className={`text-[28px] font-bold ${color}`}>{value}</div>
      <div className="text-[12px] text-gray-500 mt-1">{label}</div>
    </Link>
  );
}

export default function DashboardPage() {
  const { user }           = useAuth();
  const { isReviewer }     = useRole();
  const [stats, setStats]  = useState<DashboardStats | null>(null);

  useEffect(() => {
    apiClient.get<DashboardStats>("/dashboard/stats/").then(({ data }) => setStats(data));
  }, []);

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user?.first_name ?? ""}!`}
        description="Here is a summary of your research records."
      />

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard label="My Records"  value={stats.total_mine}    to="/records/mine"        color="text-gray-800" />
          <StatCard label="Pending"     value={stats.pending_mine}  to="/records/mine"        color="text-yellow-600" />
          <StatCard label="Approved"    value={stats.approved_mine} to="/review/approved"     color="text-green-600" />
          <StatCard label="Declined"    value={stats.declined_mine} to="/review/declined"     color="text-red-600" />
        </div>
      )}

      {/* TODO: add ClassificationChart and PSCEDChart using recharts */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-[13px] font-semibold text-gray-700 mb-2">Classification Breakdown</p>
        <p className="text-[12px] text-gray-400">TODO: render recharts BarChart from /dashboard/charts/classifications/</p>
      </div>
    </div>
  );
}
