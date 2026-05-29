import { ComingSoonPage } from "@/components/shared/ComingSoonPage";

export default function DocumentReviewsPage() {
  return (
    <ComingSoonPage
      title="Document Reviews"
      description="Staff-side workflow for reviewing extracted document content — marking uploads as reviewed, filed, approved, or flagged. This feature is currently being developed."
      icon="fa-file-check"
      backTo="/admin/users"
      backLabel="Back to Administration"
    />
  );
}
