import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import type { RecordDetail, IpType, RecordReview } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import { formatDate } from "@/lib/utils";
import { STAFF_ROLES } from "@/lib/constants";

/**
 * Returns true when this user's role is the expected reviewer at the
 * record's current pipeline stage.
 *
 * Routing:
 *   adviser_review -> Adviser (the assigned one; enforced server-side)
 *   rdco_intake    -> RDCO
 *   itso_review    -> ITSO
 *   parallel_review -> ITSO, IERC, or KTTO (per-office clearances; server enforces)
 *   rdco_review     -> RDCO
 */
function canReview(roleName: string | undefined, pipelineStatus: string): boolean {
  if (!roleName) return false;
  switch (pipelineStatus) {
    case "adviser_review":  return roleName === "Adviser";
    case "rdco_intake":     return roleName === "RDCO";
    case "itso_review":     return roleName === "ITSO" || roleName === "KTTO";
    case "parallel_review": return roleName === "ITSO" || roleName === "IERC" || roleName === "KTTO";
    case "rdco_review":     return roleName === "RDCO";
    default:                return false;
  }
}

/** Returns true if the current user owns this record. */
function isOwner(record: RecordDetail, userId: number | undefined): boolean {
  if (!userId) return false;
  return record.owners.some((o) => o.user === userId);
}

/** Returns true if the user can set IP tags (staff roles only). */
function canTag(roleName: string | undefined): boolean {
  if (!roleName) return false;
  return STAFF_ROLES.includes(roleName as typeof STAFF_ROLES[number]);
}

// ---------------------------------------------------------------------------
// Review History — shows all reviewer comments on a record
// ---------------------------------------------------------------------------

const STATUS_STYLES: Record<string, string> = {
  approved: "bg-green-50 text-green-700 border-green-200",
  declined: "bg-amber-50 text-amber-700 border-amber-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

function ReviewHistory({ reviews }: { reviews: RecordReview[] }) {
  return (
    <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
      <p className="px-4 py-2.5 text-[11px] font-bold tracking-widest text-gray-400 uppercase">
        Review History
      </p>
      {reviews.map((r) => (
        <div key={r.id} className="px-4 py-3 flex gap-3">
          <div className="flex-shrink-0 mt-0.5">
            <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border capitalize ${STATUS_STYLES[r.status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
              {r.status}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] text-gray-500 mb-0.5">
              <span className="font-semibold text-gray-700">{r.reviewed_by_name ?? "Reviewer"}</span>
              {" · "}{r.stage.replace(/_/g, " ")}
              {" · "}{new Date(r.created_at).toLocaleDateString()}
            </p>
            {r.comment ? (
              <p className="text-[13px] text-gray-700 leading-relaxed">{r.comment}</p>
            ) : (
              <p className="text-[12px] text-gray-400 italic">No comment provided.</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// IP Type Tagger — inline panel for reviewers on published records
// ---------------------------------------------------------------------------

const IP_TYPE_OPTIONS: { value: IpType; label: string }[] = [
  { value: "patent",        label: "Patent" },
  { value: "copyright",     label: "Copyright" },
  { value: "trade_secret",  label: "Trade Secret" },
  { value: "utility_model", label: "Utility Model" },
];

interface IpTaggerProps {
  recordId: number;
  currentIpType: IpType;
  onSaved: (updated: RecordDetail) => void;
}

function IpTagger({ recordId, currentIpType, onSaved }: IpTaggerProps) {
  const [selected, setSelected] = useState<IpType>(currentIpType);
  const [saving,   setSaving]   = useState(false);
  const [saved,    setSaved]    = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const isDirty = selected !== currentIpType;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const { data } = await recordsApi.updateTags(recordId, { ip_type: selected });
      onSaved(data as RecordDetail);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError("Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 space-y-3">
      <p className="text-[12px] font-semibold text-indigo-800 flex items-center gap-1.5">
        <i className="fas fa-tag text-indigo-600" />
        IP Classification <span className="text-indigo-500 font-normal">(staff only)</span>
      </p>

      <div className="flex flex-wrap gap-2">
        {IP_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setSelected(opt.value === selected ? "" : opt.value)}
            className={`px-3 py-1 rounded-full text-[12px] font-medium border transition-colors ${
              selected === opt.value
                ? "bg-indigo-700 text-white border-indigo-700"
                : "bg-white text-indigo-700 border-indigo-300 hover:border-indigo-500"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="px-3 py-1.5 bg-indigo-700 text-white text-[12px] font-semibold rounded-lg
            hover:bg-indigo-800 disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving…" : "Save Classification"}
        </button>
        {selected && (
          <button
            type="button"
            onClick={() => setSelected("")}
            className="px-3 py-1.5 text-[12px] text-indigo-600 hover:underline"
          >
            Clear
          </button>
        )}
        {saved && <span className="text-[12px] text-green-600 font-medium">Saved ✓</span>}
        {error && <span className="text-[12px] text-red-500">{error}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RecordDetailPage() {
  const { id }  = useParams<{ id: string }>();
  const { user } = useAuth();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loading, setLoading]           = useState(true);
  const [resubmitting, setResubmitting] = useState(false);
  const [resubmitError, setResubmitError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    recordsApi.detail(Number(id))
      .then(({ data }) => setRecord(data))
      .finally(() => setLoading(false));
    recordsApi.incrementAccess(Number(id)).catch(() => {});
  }, [id]);

  const handleComplete = async () => {
    if (!id) return;
    setCompleting(true);
    setCompleteError(null);
    try {
      await recordsApi.completeProposal(Number(id));
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to mark as complete. Please try again.";
      setCompleteError(msg);
    } finally {
      setCompleting(false);
    }
  };

  const handleResubmit = async () => {
    if (!id) return;
    setResubmitting(true);
    setResubmitError(null);
    try {
      await reviewsApi.resubmit(Number(id));
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Resubmission failed. Please try again.";
      setResubmitError(msg);
    } finally {
      setResubmitting(false);
    }
  };

  if (loading) return <div className="p-8 text-gray-400 text-[13px]">Loading...</div>;
  if (!record)  return <div className="p-8 text-gray-500 text-[13px]">Record not found.</div>;

  const userCanReview    = canReview(user?.role_name ?? undefined, record.pipeline_status);
  const userIsOwner      = isOwner(record, user?.id);
  const canBeResubmitted = record.pipeline_status === "declined" && userIsOwner;
  const userCanTag       = canTag(user?.role_name ?? undefined);
  // IP Tagger shown on published records to all reviewer-role users
  const showIpTagger     = userCanTag && record.pipeline_status === "published";
  // "Mark as Complete" shown to RDCO on approved Proposals only
  const canComplete      =
    user?.role_name === "RDCO" &&
    record.pipeline_status === "approved" &&
    (record.record_type_name === "Proposal" || String(record.record_type) === "Proposal");

  return (
    <div>
      <PageHeader title={record.title} description={`Added ${formatDate(record.created_at)}`} />

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        {/* Status + flag badges */}
        <div className="flex items-center gap-3 flex-wrap">
          <StatusBadge status={record.pipeline_status} />
          {record.is_ip && (
            <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-[11px] font-semibold">
              Intellectual Property
            </span>
          )}
          {record.ip_type && (
            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-full text-[11px] font-semibold">
              {IP_TYPE_LABELS[record.ip_type as Exclude<typeof record.ip_type, "">]}
            </span>
          )}
          {record.for_commercialization && (
            <span className="px-2 py-0.5 bg-green-50 text-green-700 rounded-full text-[11px] font-semibold">
              For Commercialization
            </span>
          )}
          {record.community_extension && (
            <span className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded-full text-[11px] font-semibold">
              Community Extension
            </span>
          )}
        </div>

        {/* Revision requested banner */}
        {record.pipeline_status === "declined" && userIsOwner && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
            <strong>Revision requested.</strong> Please review the feedback, make the necessary
            changes, and resubmit when ready.
          </div>
        )}

        {/* Rejection banner */}
        {record.pipeline_status === "rejected" && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
            <strong>This record has been rejected.</strong> It cannot be resubmitted. Please
            contact the relevant office if you have questions.
          </div>
        )}

        {/* Review history — comments from reviewers */}
        {record.reviews && record.reviews.length > 0 && (
          <ReviewHistory reviews={record.reviews} />
        )}

        {/* Core metadata */}
        <div className="grid grid-cols-2 gap-4 text-[13px]">
          <div><span className="font-semibold text-gray-700">Year:</span> <span className="text-gray-600">{record.year_accomplished ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">Classification:</span> <span className="text-gray-600">{record.classification ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">Type:</span> <span className="text-gray-600">{record.record_type ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">PSCED:</span> <span className="text-gray-600">{record.psced ?? "-"}</span></div>
        </div>

        {record.abstract && (
          <div>
            <p className="text-[12px] font-semibold text-gray-700 mb-1">Abstract</p>
            <p className="text-[13px] text-gray-600 leading-relaxed">{record.abstract}</p>
          </div>
        )}

        <div>
          <p className="text-[12px] font-semibold text-gray-700 mb-2">Authors</p>
          <div className="flex flex-wrap gap-2">
            {record.authors.map((a) => (
              <span key={a.id} className="px-2 py-0.5 bg-gray-100 rounded text-[12px] text-gray-700">{a.name}</span>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[12px] font-semibold text-gray-700 mb-2">Owners</p>
          <div className="flex flex-wrap gap-2">
            {record.owners.map((o) => (
              <span key={o.id} className="px-2 py-0.5 bg-gray-100 rounded text-[12px] text-gray-700">
                {o.full_name}{o.is_primary ? " (primary)" : ""}
              </span>
            ))}
          </div>
        </div>

        {/* IP Classification tagger — shown to reviewer-role users on published records */}
        {showIpTagger && (
          <IpTagger
            recordId={record.id}
            currentIpType={record.ip_type}
            onSaved={(updated) => setRecord(updated)}
          />
        )}

        {/* Action bar */}
        <div className="pt-2 border-t border-gray-100 flex gap-2 flex-wrap">
          <Link
            to={`/records/${id}/documents`}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#6B0F12] text-white text-[13px] font-semibold hover:bg-[#7d1215] transition-colors"
          >
            <i className="fas fa-folder-open text-[12px]" />
            View Documents
          </Link>

          {userCanReview && (
            <Link
              to={`/review/${id}/evaluate`}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-green-700 text-white text-[13px] font-semibold hover:bg-green-800 transition-colors"
            >
              <i className="fas fa-clipboard-check text-[12px]" />
              Review this Record
            </Link>
          )}

          {canBeResubmitted && (
            <button
              type="button"
              onClick={handleResubmit}
              disabled={resubmitting}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-600 text-white text-[13px] font-semibold hover:bg-amber-700 transition-colors disabled:opacity-60"
            >
              <i className="fas fa-redo text-[12px]" />
              {resubmitting ? "Resubmitting..." : "Resubmit for Review"}
            </button>
          )}

          {canComplete && (
            <button
              type="button"
              onClick={handleComplete}
              disabled={completing}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-700 text-white text-[13px] font-semibold hover:bg-emerald-800 transition-colors disabled:opacity-60"
            >
              <i className="fas fa-check-circle text-[12px]" />
              {completing ? "Marking..." : "Mark as Completed"}
            </button>
          )}
        </div>

        {resubmitError && (
          <p className="text-[13px] text-red-600 mt-1">{resubmitError}</p>
        )}
        {completeError && (
          <p className="text-[13px] text-red-600 mt-1">{completeError}</p>
        )}
      </div>
    </div>
  );
}
