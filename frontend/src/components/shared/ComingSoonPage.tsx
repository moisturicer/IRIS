import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";

interface ComingSoonPageProps {
  title: string;
  description: string;
  icon?: string;
  backTo?: string;
  backLabel?: string;
}

export function ComingSoonPage({
  title,
  description,
  icon = "fa-hourglass-half",
  backTo = "/",
  backLabel = "Go back",
}: ComingSoonPageProps) {
  return (
    <div>
      <PageHeader title={title} />
      <div className="mt-6 flex flex-col items-center text-center py-16 px-6 bg-white rounded-xl border border-gray-200 max-w-lg mx-auto">
        <div className="w-14 h-14 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center mb-5">
          <i className={`fas ${icon} text-2xl text-slate-300`} aria-hidden />
        </div>
        <span className="px-3 py-1 bg-amber-50 text-amber-700 text-[11px] font-bold rounded-full border border-amber-200 uppercase tracking-wider mb-4">
          Coming Soon
        </span>
        <p className="text-[13px] text-gray-500 leading-relaxed max-w-sm">{description}</p>
        <Link
          to={backTo}
          className="mt-6 text-[13px] font-semibold text-[#6B0F12] hover:underline"
        >
          ← {backLabel}
        </Link>
      </div>
    </div>
  );
}
