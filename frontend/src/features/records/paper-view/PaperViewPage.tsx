import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { reviewsApi } from "@/api/reviews";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import { STAFF_ROLES } from "@/lib/constants";
import { cn, formatDate } from "@/lib/utils";
import type { RecordDetail, IpType, RecordReview } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import type { SemanticSearchResult } from "@/types/ai";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { PaperSaveDropdown } from "@/features/discover/PaperSaveDropdown";
import { recordVisit } from "@/lib/recordLibrary";
import { ClearanceTrack } from "./ClearanceTrack";
import {
  usePaperChat,
  PaperChatPanel,
  PaperChatLauncher,
  DOCKED_PANEL_CLASS,
  FLOATING_PANEL_CLASS,
} from "./PaperChatDock";
import { PaperAiOverview } from "./PaperAiOverview";
import { PaperGovernance } from "./PaperGovernance";
import { PaperDocuments } from "./PaperDocuments";

// ---------------------------------------------------------------------------
// Role predicates — these mirror the server's rules; the server still enforces.
// ---------------------------------------------------------------------------

/**
 * True when this user's role is the expected reviewer at the record's current
 * pipeline stage.
 *
 *   adviser_review  -> Adviser (the assigned one; enforced server-side)
 *   rdco_intake     -> RDCO
 *   itso_review     -> ITSO or KTTO
 *   parallel_review -> ITSO, IERC or KTTO (per-office clearances)
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

function isOwner(record: RecordDetail, userId: number | undefined): boolean {
  if (!userId) return false;
  return record.owners.some((o) => o.user === userId);
}

function canTag(roleName: string | undefined): boolean {
  if (!roleName) return false;
  return STAFF_ROLES.includes(roleName as typeof STAFF_ROLES[number]);
}

// ---------------------------------------------------------------------------
// Review history
// ---------------------------------------------------------------------------

const REVIEW_STATUS_STYLES: Record<string, string> = {
  approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  declined: "bg-amber-50 text-amber-700 border-amber-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

function ReviewHistory({ reviews }: { reviews: RecordReview[] }) {
  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-3">
        Review History
      </h2>
      <ol className="space-y-3">
        {reviews.map((r) => (
          <li key={r.id} className="flex gap-3">
            <span
              className={cn(
                "shrink-0 mt-0.5 px-2 py-0.5 rounded-full text-[10px] font-bold border capitalize",
                REVIEW_STATUS_STYLES[r.status] ?? "bg-stone-50 text-stone-600 border-stone-200",
              )}
            >
              {r.status}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] text-stone-400">
                <span className="font-semibold text-stone-600">
                  {r.reviewed_by_name ?? "Reviewer"}
                </span>
                {" · "}
                <span className="capitalize">{r.stage.replace(/_/g, " ")}</span>
                {" · "}
                {formatDate(r.created_at)}
              </p>
              {r.comment ? (
                <p className="text-[13px] text-stone-700 leading-relaxed mt-0.5">{r.comment}</p>
              ) : (
                <p className="text-[12px] text-stone-400 italic mt-0.5">No comment provided.</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------------------
// IP classification tagger — staff only, published records
// ---------------------------------------------------------------------------

const IP_TYPE_OPTIONS: Exclude<IpType, "">[] = [
  "patent",
  "copyright",
  "trade_secret",
  "utility_model",
];

interface IpTaggerProps {
  recordId: number;
  currentIpType: IpType;
  onSaved: (updated: RecordDetail) => void;
}

function IpTagger({ recordId, currentIpType, onSaved }: IpTaggerProps) {
  const [selected, setSelected] = useState<IpType>(currentIpType);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-1">
        IP Classification
      </h2>
      <p className="text-[12px] text-stone-500 mb-3">
        Staff only. Sets the structured IP type recorded against this disclosure.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {IP_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt}
            type="button"
            aria-pressed={selected === opt}
            onClick={() => setSelected(opt === selected ? "" : opt)}
            className={cn(
              "px-2.5 py-1 rounded-full text-[12px] font-semibold border transition-colors",
              selected === opt
                ? "bg-brand text-white border-brand"
                : "bg-white text-stone-600 border-stone-200 hover:border-brand/40",
            )}
          >
            {IP_TYPE_LABELS[opt]}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="px-3 py-1.5 rounded-lg bg-brand text-white text-[12px] font-bold hover:bg-brand-light disabled:opacity-40 transition-colors"
        >
          {saving ? "Saving…" : "Save classification"}
        </button>
        {saved && <span className="text-[12px] font-semibold text-emerald-600">Saved</span>}
        {error && <span className="text-[12px] text-red-600">{error}</span>}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Similar papers — same retrieval, and the same visibility predicate, as Ask IRIS
// ---------------------------------------------------------------------------

function SimilarPapers({ recordId }: { recordId: number }) {
  const [items, setItems] = useState<SemanticSearchResult[] | null>(null);

  useEffect(() => {
    let alive = true;
    recordsApi
      .similar(recordId)
      .then(({ data }) => {
        if (alive) setItems(data.results ?? []);
      })
      .catch(() => {
        if (alive) setItems([]);
      });
    return () => {
      alive = false;
    };
  }, [recordId]);

  if (items === null) {
    return (
      <section>
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-3">
          Related Institutional Works
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-24 rounded-2xl border border-stone-200 bg-white animate-pulse"
            />
          ))}
        </div>
      </section>
    );
  }

  if (items.length === 0) return null;

  return (
    <section>
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400">
          Related Institutional Works
        </h2>
        <Link to="/discover" className="text-[12px] font-semibold text-brand hover:underline">
          Explore all papers →
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/records/${item.id}`}
            className="bg-white border border-stone-200 rounded-2xl p-3.5 hover:border-brand/30 hover:shadow-card-md transition-all"
          >
            <p className="text-[10px] font-bold tracking-wider text-stone-300 mb-1.5">
              CIT-U #{item.id}
            </p>
            <p className="text-[13px] font-bold text-stone-900 leading-snug line-clamp-3">
              {item.title}
            </p>
            <p className="text-[11px] text-stone-400 mt-1.5">
              {item.year ?? "—"}
              {item.classification ? ` · ${item.classification}` : ""}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] items-start animate-pulse">
      <div className="space-y-4">
        <div className="h-5 w-56 rounded bg-stone-200" />
        <div className="h-9 w-full rounded bg-stone-200" />
        <div className="h-9 w-2/3 rounded bg-stone-200" />
        <div className="h-32 w-full rounded-2xl bg-stone-100" />
      </div>
      <div className="space-y-4">
        <div className="h-44 rounded-2xl bg-stone-100" />
        <div className="h-36 rounded-2xl bg-stone-100" />
      </div>
    </div>
  );
}

/** Initials for the owner chip. */
function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function PaperViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const chat = usePaperChat();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [citeOpen, setCiteOpen] = useState(false);
  const [resubmitting, setResubmitting] = useState(false);
  const [resubmitError, setResubmitError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    recordsApi
      .detail(Number(id))
      .then(({ data }) => {
        setRecord(data);
        // access_count is a global counter, so it cannot answer "what have I
        // read?". My Library's reading history is written here instead, per
        // browser. See lib/recordLibrary.
        recordVisit(data.id, data.title);
      })
      .catch(() => setRecord(null))
      .finally(() => setLoading(false));
    recordsApi.incrementAccess(Number(id)).catch(() => {});
  }, [id]);

  const handleResubmit = async () => {
    if (!id) return;
    setResubmitting(true);
    setResubmitError(null);
    try {
      await reviewsApi.resubmit(Number(id));
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch (err: unknown) {
      setResubmitError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Resubmission failed. Please try again.",
      );
    } finally {
      setResubmitting(false);
    }
  };

  const handleComplete = async () => {
    if (!id) return;
    setCompleting(true);
    setCompleteError(null);
    try {
      await recordsApi.completeProposal(Number(id));
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch (err: unknown) {
      setCompleteError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Could not mark as completed. Please try again.",
      );
    } finally {
      setCompleting(false);
    }
  };

  if (loading) return <LoadingSkeleton />;

  if (!record) {
    return (
      <div className="max-w-md mx-auto text-center py-20">
        <i className="fas fa-file-circle-question text-[28px] text-stone-300 mb-3" aria-hidden />
        <p className="text-[15px] font-bold text-stone-800">Record not available</p>
        <p className="text-[13px] text-stone-500 mt-1">
          It may have been withdrawn, or you may not have access to it.
        </p>
        <Link
          to="/discover"
          className="inline-block mt-4 px-4 py-2 rounded-lg bg-brand text-white text-[13px] font-bold hover:bg-brand-light transition-colors"
        >
          Back to Discover
        </Link>
      </div>
    );
  }

  const userIsOwner      = isOwner(record, user?.id);
  const userCanReview    = canReview(user?.role_name ?? undefined, record.pipeline_status);
  const canBeResubmitted = record.pipeline_status === "declined" && userIsOwner;
  const showIpTagger =
    canTag(user?.role_name ?? undefined) && record.pipeline_status === "published";
  const canComplete =
    user?.role_name === "RDCO" &&
    record.pipeline_status === "approved" &&
    record.record_type_name === "Proposal";

  const primaryOwner = record.owners.find((o) => o.is_primary) ?? record.owners[0];

  // The paper itself. `abstract_file` is the uploaded manuscript when there is
  // one; otherwise fall back to the first attachment. The Documents rail covers
  // the rest, so this button is only ever "the paper".
  const paperUrl = record.abstract_file ?? record.files[0]?.url ?? null;

  // Clearances decided before the latest decline are the ones a resubmission
  // carried over. Reviews arrive oldest-first from the API.
  const lastDeclineAt =
    [...record.reviews].reverse().find((r) => r.status === "declined")?.created_at ?? null;

  return (
    <div
      className={cn(
        "lg:flex lg:gap-6 lg:items-start",
        chat.dock === "left" && "lg:flex-row-reverse",
      )}
    >
      <div className="min-w-0 lg:flex-1">
        {/* Orientation bar */}
        <div className="flex items-center justify-between gap-4 flex-wrap mb-6">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-stone-600 hover:text-brand transition-colors"
          >
            <i className="fas fa-arrow-left text-[11px]" aria-hidden />
            Back
          </button>
          <div className="flex items-center gap-4 text-[12px] text-stone-400">
            <span className="flex items-center gap-1.5">
              <i className="fas fa-calendar text-[11px]" aria-hidden />
              Added {formatDate(record.created_at)}
            </span>
            <span className="flex items-center gap-1.5">
              <i className="fas fa-eye text-[11px]" aria-hidden />
              {record.access_count} view{record.access_count === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] items-start">
          {/* ------------------------------------------------------------- */}
          {/* Main column                                                    */}
          {/* ------------------------------------------------------------- */}
          <div className="min-w-0 space-y-6">
            {/* Chips */}
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={record.pipeline_status} />
              {record.is_ip && (
                <span className="px-2 py-0.5 rounded-full bg-brand text-white text-[11px] font-semibold flex items-center gap-1.5">
                  <i className="fas fa-shield-halved text-[9px]" aria-hidden />
                  Intellectual Property
                </span>
              )}
              {record.ip_type && (
                <span className="px-2 py-0.5 rounded-full bg-stone-900 text-white text-[11px] font-semibold">
                  {IP_TYPE_LABELS[record.ip_type]}
                </span>
              )}
              {record.for_commercialization && (
                <span className="px-2 py-0.5 rounded-full border border-stone-300 text-stone-700 text-[11px] font-semibold">
                  For Commercialization
                </span>
              )}
              {record.community_extension && (
                <span className="px-2 py-0.5 rounded-full border border-stone-300 text-stone-700 text-[11px] font-semibold">
                  Community Extension
                </span>
              )}
              {record.record_type_name && (
                <span className="px-2 py-0.5 rounded-full border border-stone-300 text-stone-700 text-[11px] font-semibold">
                  {record.record_type_name}
                </span>
              )}
              {record.classification_name && (
                <span className="px-2 py-0.5 rounded-full bg-brand-50 text-brand border border-brand-200 text-[11px] font-semibold">
                  {record.classification_name}
                </span>
              )}
            </div>

            {/* Title + attribution */}
            <div>
              <h1 className="text-[26px] leading-[1.2] font-bold text-stone-900 tracking-tight">
                {record.title}
              </h1>
              {primaryOwner && (
                <div className="flex items-center gap-2 flex-wrap mt-3">
                  <span className="inline-flex items-center gap-2 pl-1 pr-3 py-1 rounded-full border border-stone-200 bg-white">
                    <span className="w-6 h-6 rounded-full bg-brand text-white text-[10px] font-bold flex items-center justify-center">
                      {initials(primaryOwner.full_name)}
                    </span>
                    <span className="text-[13px] font-semibold text-stone-800">
                      {primaryOwner.full_name}
                    </span>
                  </span>
                  <span className="text-[12px] text-stone-400">
                    · Cebu Institute of Technology – University
                  </span>
                </div>
              )}
            </div>

            {/* Owner-actionable banners */}
            {canBeResubmitted && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-[13px] font-bold text-amber-900 flex items-center gap-2">
                  <i className="fas fa-arrow-rotate-left text-[12px]" aria-hidden />
                  Revision requested
                </p>
                <p className="text-[13px] text-amber-800 leading-relaxed mt-1">
                  Address the reviewer comments below, then resubmit. Offices that already cleared
                  this record keep their clearance — only the office that asked for changes reviews
                  it again.
                </p>
                <button
                  type="button"
                  onClick={handleResubmit}
                  disabled={resubmitting}
                  className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-600 text-white text-[13px] font-bold hover:bg-amber-700 disabled:opacity-60 transition-colors"
                >
                  <i className="fas fa-paper-plane text-[11px]" aria-hidden />
                  {resubmitting ? "Resubmitting…" : "Resubmit for review"}
                </button>
                {resubmitError && <p className="text-[12px] text-red-700 mt-2">{resubmitError}</p>}
              </div>
            )}

            {record.pipeline_status === "rejected" && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-4">
                <p className="text-[13px] font-bold text-red-900 flex items-center gap-2">
                  <i className="fas fa-circle-xmark text-[12px]" aria-hidden />
                  This record was rejected
                </p>
                <p className="text-[13px] text-red-800 leading-relaxed mt-1">
                  It cannot be resubmitted. Contact the relevant office if you have questions.
                </p>
              </div>
            )}

            {/* Abstract */}
            <section>
              <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-2">
                Abstract
              </h2>
              {record.abstract ? (
                <p className="text-[14px] text-stone-700 leading-[1.75] text-justify">
                  {record.abstract}
                </p>
              ) : (
                <p className="text-[13px] text-stone-400 italic">
                  No abstract was provided for this record.
                </p>
              )}
            </section>

            {/* Action row */}
            <div className="flex items-center gap-2 flex-wrap pb-6 border-b border-stone-200">
              {paperUrl ? (
                <a
                  href={paperUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-[13px] font-bold hover:bg-brand-light transition-colors"
                >
                  <i className="fas fa-book-open text-[12px]" aria-hidden />
                  View Paper
                </a>
              ) : (
                <span
                  title="No paper file has been uploaded for this record yet."
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-stone-100 text-stone-400 text-[13px] font-bold cursor-not-allowed"
                >
                  <i className="fas fa-book-open text-[12px]" aria-hidden />
                  View Paper
                </span>
              )}

              {userCanReview && (
                <Link
                  to={`/review/${record.id}/evaluate`}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-700 text-white text-[13px] font-bold hover:bg-emerald-800 transition-colors"
                >
                  <i className="fas fa-clipboard-check text-[12px]" aria-hidden />
                  Review this record
                </Link>
              )}

              {canComplete && (
                <button
                  type="button"
                  onClick={handleComplete}
                  disabled={completing}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-700 text-white text-[13px] font-bold hover:bg-emerald-800 disabled:opacity-60 transition-colors"
                >
                  <i className="fas fa-circle-check text-[12px]" aria-hidden />
                  {completing ? "Marking…" : "Mark as completed"}
                </button>
              )}

              <PaperSaveDropdown record={record} />

              <button
                type="button"
                onClick={() => setCiteOpen(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-stone-200 bg-white text-stone-700 text-[13px] font-bold hover:border-brand/40 transition-colors"
              >
                <i className="fas fa-quote-right text-[11px]" aria-hidden />
                Cite
              </button>
            </div>

            {completeError && <p className="text-[12px] text-red-600">{completeError}</p>}

            <PaperAiOverview record={record} />

            {/* Authors */}
            {record.authors.length > 0 && (
              <section>
                <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-2">
                  Authors
                </h2>
                <div className="flex flex-wrap gap-1.5">
                  {record.authors.map((a) => (
                    <span
                      key={a.id}
                      className="px-2.5 py-1 rounded-lg bg-stone-100 text-[12px] font-medium text-stone-700"
                    >
                      {a.name}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {record.reviews.length > 0 && <ReviewHistory reviews={record.reviews} />}

            {showIpTagger && (
              <IpTagger
                recordId={record.id}
                currentIpType={record.ip_type}
                onSaved={(updated) => setRecord(updated)}
              />
            )}

            <SimilarPapers recordId={record.id} />
          </div>

          {/* ------------------------------------------------------------- */}
          {/* Right rail                                                     */}
          {/* ------------------------------------------------------------- */}
          <aside className="space-y-4 lg:sticky lg:top-6">
            <ClearanceTrack clearances={record.clearances} preservedBefore={lastDeclineAt} />
            <PaperGovernance record={record} />
            <PaperDocuments recordId={record.id} files={record.files} />
          </aside>
        </div>

        <PaperCiteModal record={record} isOpen={citeOpen} onClose={() => setCiteOpen(false)} />
      </div>

      {chat.open ? (
        <PaperChatPanel
          record={record}
          dock={chat.dock}
          onDockChange={chat.setDockMode}
          onClose={() => chat.setOpen(false)}
          className={
            chat.dock === "floating" ? FLOATING_PANEL_CLASS : DOCKED_PANEL_CLASS
          }
        />
      ) : (
        <PaperChatLauncher onOpen={() => chat.setOpen(true)} />
      )}
    </div>
  );
}
