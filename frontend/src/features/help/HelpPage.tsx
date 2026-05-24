import { PageHeader } from "@/components/layout/PageHeader";
import { Link } from "react-router-dom";

export default function HelpPage() {
  return (
    <div>
      <PageHeader
        title="Help & User Manual"
        description="Guidance for using the CIT-U Research Hub will be published here."
      />
      <div className="bg-white rounded-xl border border-gray-200 p-8 max-w-xl">
        <p className="text-[13px] text-gray-600 leading-relaxed mb-4">
          Documentation for disclosure submission, review queues, and AI features is in preparation.
        </p>
        <Link
          to="/"
          className="text-[13px] font-semibold text-brand hover:underline"
        >
          Return to Discover
        </Link>
      </div>
    </div>
  );
}
