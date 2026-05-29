import { ComingSoonPage } from "@/components/shared/ComingSoonPage";

export default function ReviewAnalyticsPage() {
  return (
    <ComingSoonPage
      title="Review Analytics"
      description="Track review cycle times, approval rates by office, and pipeline throughput across all record types. This dashboard is currently being developed."
      icon="fa-chart-line"
      backTo="/review/pending"
      backLabel="Back to Review Queue"
    />
  );
}
