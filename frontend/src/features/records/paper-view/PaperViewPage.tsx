import { lazy, Suspense, useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams, useLocation, Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { reviewsApi } from "@/api/reviews";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button, Skeleton } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ROLES, STAFF_ROLES } from "@/lib/constants";
import { cn, formatDate } from "@/lib/utils";
import { citedPage, type CitationNavigationState } from "@/lib/citedPage";
import type { RecordDetail, IpType, RecordReview } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import type { Region, SemanticSearchResult } from "@/types/ai";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { PaperSaveDropdown } from "@/features/discover/PaperSaveDropdown";
import { recordVisit } from "@/lib/recordLibrary";
import { ReviewRoutingTracker } from "./ReviewRoutingTracker";
import { ActionRequiredPanel } from "@/features/document-requests/ActionRequiredPanel";
import { ReviewerDocumentRequests } from "@/features/document-requests/ReviewerDocumentRequests";
import {
  usePaperChat,
  PaperChatPanel,
  PaperChatLauncher,
  type DockMode,
  DOCKED_PANEL_CLASS,
  FLOATING_PANEL_CLASS,
  MINIMIZED_SHEET_CLASS,
  PAPER_TAB_PANEL_CLASS,
} from "./PaperChatDock";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { PaperAiOverview } from "./PaperAiOverview";
import { PaperGovernance } from "./PaperGovernance";
import { PaperDocuments } from "./PaperDocuments";
import { CONTAINED_LAYOUT_QUERY, PANE_MAX_HEIGHT, PANE_TOP, VIEW_SWITCH_TOP } from "./paneLayout";
import { SectionHeading } from "./headings";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";

// Lazy: pdf.js is a large dependency (its worker alone is over a megabyte),
// and most visits to this screen never open the Paper tab at all. Splitting
// it out of the main bundle means only a reader who actually opens the
// reader pays for it.
const PaperPdfReader = lazy(() =>
  import("./PaperPdfReader").then((m) => ({ default: m.PaperPdfReader })),
);

// ---------------------------------------------------------------------------
// Role predicates — these mirror the server's rules; the server still enforces.
// ---------------------------------------------------------------------------

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

// Declined (recoverable: revision requested) and rejected (terminal) must
// never look alike -- resubmission is the thesis contribution. Soft versus
// solid maroon, and their labels (IR-356).
const REVIEW_STATUS_STYLES: Record<string, string> = {
  approved: "bg-stone-100 text-stone-900 border-stone-300",
  declined: "bg-brand-50 text-brand border-brand-200",
  rejected: "bg-brand text-white border-brand",
};

function ReviewHistory({ reviews }: { reviews: RecordReview[] }) {
  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <h2 className="text-2xs font-bold uppercase tracking-wider text-stone-400 mb-3">
        Review History
      </h2>
      <ol className="space-y-3">
        {reviews.map((r) => (
          <li key={r.id} className="flex gap-3">
            <span
              className={cn(
                "shrink-0 mt-0.5 px-2 py-0.5 rounded-full text-2xs font-bold border capitalize",
                REVIEW_STATUS_STYLES[r.status] ?? "bg-stone-50 text-stone-600 border-stone-200",
              )}
            >
              {r.status}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-2xs text-stone-400">
                <span className="font-semibold text-stone-600">
                  {r.reviewed_by_name ?? "Reviewer"}
                </span>
                {" · "}
                <span className="capitalize">{r.stage.replace(/_/g, " ")}</span>
                {" · "}
                {formatDate(r.created_at)}
              </p>
              {r.comment ? (
                <p className="text-sm text-stone-700 leading-relaxed mt-0.5">{r.comment}</p>
              ) : (
                <p className="text-xs text-stone-400 italic mt-0.5">No comment provided.</p>
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
      <h2 className="text-2xs font-bold uppercase tracking-wider text-stone-400 mb-1">
        IP Classification
      </h2>
      <p className="text-xs text-stone-500 mb-3">
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
              "px-2.5 py-1 rounded-full text-xs font-semibold border transition-colors",
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
          className="px-3 py-1.5 rounded-lg bg-brand text-white text-xs font-bold hover:bg-brand-light disabled:opacity-40 transition-colors"
        >
          {saving ? "Saving…" : "Save classification"}
        </button>
        {saved && <span className="text-xs font-semibold text-stone-900">Saved</span>}
        {error && <span className="text-xs text-brand">{error}</span>}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Similar papers — record-vector similarity (ADR-029 §5), through the same
// `visible_to` predicate as Ask IRIS. The *predicate* is shared; the retrieval
// is not — Ask IRIS ranks passages, this ranks whole records on their
// title-and-abstract vector, so it answers "broadly about the same thing?"
// and will miss two papers sharing a method described mid-document.
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
        <SectionHeading>Related works</SectionHeading>
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-28 rounded-2xl ring-1 ring-stone-200 bg-white animate-pulse motion-reduce:animate-none"
            />
          ))}
        </div>
      </section>
    );
  }

  // Empty is the common case today and says nothing by itself: a record with
  // no vector has no neighbours, and the disclosure gate (IR-250) means no
  // record has one yet. Rendering nothing at all left a reader to conclude
  // this paper is unrelated to everything in the repository, which is a
  // stronger claim than IRIS can make.
  if (items.length === 0) {
    return (
      <section>
        <SectionHeading>Related works</SectionHeading>
        <p className="text-sm text-stone-500">
          No related works found. Similarity is computed from indexed records, and indexing
          has not run for this repository yet.
        </p>
      </section>
    );
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading>Related works</SectionHeading>
        <Link to="/discover" className="text-sm font-semibold text-brand hover:underline">
          Explore all papers →
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/records/${item.id}`}
            className="group bg-white ring-1 ring-stone-200 rounded-2xl p-4 border-t-2 border-t-brand/70 hover:ring-brand/30 hover:shadow-card-md transition-all duration-200"
          >
            <p className="text-2xs font-semibold tracking-wider text-stone-500 mb-2">
              CIT-U #{item.id}
            </p>
            <p className="font-display text-lg font-semibold text-stone-900 leading-snug line-clamp-3 group-hover:text-brand transition-colors duration-200">
              {item.title}
            </p>
            <p className="text-2xs text-stone-500 mt-2">
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

type PaperViewTab = "abstract" | "paper";

export default function PaperViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const { user } = useAuth();

  const chat = usePaperChat();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [citeOpen, setCiteOpen] = useState(false);
  const [shareState, setShareState] = useState<"idle" | "copied" | "failed">("idle");
  const [resubmitting, setResubmitting] = useState(false);
  const [resubmitError, setResubmitError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  /** Bumped when a document request changes, so the tracker reloads. */
  const [trackerVersion, setTrackerVersion] = useState(0);

  // A citation links here with `?page=` (IR-284), so acting on it lands on
  // the page that supports the claim rather than the paper's first. The
  // rules for reading that number live in `lib/citedPage`, testable without
  // standing up this screen.
  const openAtPage = citedPage(searchParams.get("page"));

  // An Abstract/Paper toggle, alphaxiv-style (IR-335): Abstract is this
  // screen's own detail, Paper is the embedded reader. Arriving with a page
  // named -- from a citation, or a shared link -- opens straight into Paper;
  // `useState`'s initializer only runs once, so the effect below is what
  // keeps a *later* citation click (the component instance is reused; the
  // route only changes its `:id`/query, not its element) switching tabs too.
  const [tab, setTab] = useState<PaperViewTab>(openAtPage != null ? "paper" : "abstract");

  // Below `lg` the docked chat is a bottom sheet over the paper; at `lg` it
  // is a column beside it (IR-352).
  const contained = useMediaQuery(CONTAINED_LAYOUT_QUERY);

  useEffect(() => {
    if (openAtPage == null) return;
    setTab("paper");
    // A citation followed while the chat is a bottom sheet would land its
    // passage under the sheet, so the sheet tucks away to a bar (IR-354).
    if (chat.open && !contained) chat.setMinimized(true);
    // `location.key` is unique per navigation, including a second click on
    // the very citation already open -- without it in the dependency list,
    // clicking the same marker twice would not re-fire this effect to
    // re-scroll and re-flash the highlight. The chat's state is read, not a
    // trigger: opening the chat is not following a citation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openAtPage, location.key]);

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

  // Share copies the paper's permanent link (IR-356), the address a reader
  // would paste to a colleague. A blocked clipboard claims nothing.
  const handleShare = async () => {
    let outcome: "copied" | "failed" = "copied";
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/records/${id}`);
    } catch {
      // No clipboard (plain http, or permission refused): say so rather
      // than failing silently; the address bar still has the link.
      outcome = "failed";
    }
    setShareState(outcome);
    window.setTimeout(() => setShareState("idle"), 2500);
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

  /** A document request was made or answered: re-read what derives from it. */
  const handleDocumentRequestChanged = async () => {
    setTrackerVersion((v) => v + 1);
    if (!id) return;
    try {
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch {
      // The panel already shows the new state; the badge catches up on reload.
    }
  };

  if (loading) return <LoadingSkeleton />;

  if (!record) {
    return (
      <div className="max-w-md mx-auto text-center py-20">
        <i className="fas fa-file-circle-question text-3xl text-stone-300 mb-3" aria-hidden />
        <p className="text-md font-bold text-stone-800">Record not available</p>
        <p className="text-sm text-stone-500 mt-1">
          It may have been withdrawn, or you may not have access to it.
        </p>
        <Link
          to="/discover"
          className="inline-block mt-4 px-4 py-2 rounded-lg bg-brand text-white text-sm font-bold hover:bg-brand-light transition-colors"
        >
          Back to Discover
        </Link>
      </div>
    );
  }

  const userIsOwner      = isOwner(record, user?.id);
  // Both gates read the API (IR-259), which knows who holds the record and
  // what the server will accept from this viewer. The server still enforces.
  const userCanReview    = record.can_act.length > 0;
  const canBeResubmitted = record.workflow_state === "awaiting_resubmission" && userIsOwner;
  const showIpTagger =
    canTag(user?.role_name ?? undefined) && record.pipeline_status === "published";
  // RDCO or the Proposal's assigned Adviser (ADR-021 §3, IR-267) -- the same
  // two parties the server's /complete/ admits. "Assigned" is the record's
  // `adviser` id, not the Adviser role alone.
  const canComplete =
    (user?.role_name === ROLES.RDCO ||
      (user?.role_name === ROLES.ADVISER && user.id === record.adviser)) &&
    record.pipeline_status === "approved" &&
    record.record_type_name === "Proposal";

  const primaryOwner = record.owners.find((o) => o.is_primary) ?? record.owners[0];

  // Whether there is a paper to read at all. `manuscript/` resolves the same
  // abstract_file-then-newest-upload fallback server-side (`download_service
  // .resolve_record_download_file`), so this is only ever an affordance
  // decision -- the reader itself is the one source of truth for what it can
  // actually fetch.
  const hasPaper = Boolean(record.abstract_file) || record.files.length > 0;

  // A citation carries the exact chunk it points at as router `state`
  // (IR-335), so the reader draws its highlight with no second fetch. A
  // navigation this link did not originate -- a typed URL, a refresh, a
  // bookmark -- carries no state, and the reader still opens at `openAtPage`
  // with nothing to highlight, which is the same graceful case a passage
  // with no recovered regions already is.
  const navCitation = (location.state as CitationNavigationState | null)?.citation;
  // The Paper tab is the paper and Ask IRIS, nothing else (IR-372): chat is
  // always docked right there, the rail is never drawn, and the pair spans
  // the full content width rather than a centred column. The reader's own
  // dock choice is only overridden, never overwritten, so the Abstract tab
  // gets it back unchanged.
  const onPaperTab = tab === "paper";
  const dock: DockMode = onPaperTab ? "right" : chat.dock;
  const chatDocked = chat.open && dock !== "floating";
  // Never at `lg`, where there is no sheet to tuck away: widening the window
  // brings the column back whole.
  const chatMinimized = chat.minimized && chatDocked && !contained;
  const chatPanelClass = chatMinimized
    ? MINIMIZED_SHEET_CLASS
    : onPaperTab
      ? PAPER_TAB_PANEL_CLASS
      : chatDocked
        ? DOCKED_PANEL_CLASS
        : FLOATING_PANEL_CLASS;
  const showRail = !onPaperTab && !chatDocked;
  const highlightRegions: Region[] =
    navCitation && navCitation.record_id === record.id && "regions" in navCitation
      ? navCitation.regions
      : [];

  return (
    // Centred, not stretched edge to edge (IR-335) -- alphaxiv's reading
    // layout. `AppShell`'s own `<main>` sets no max-width, deliberately: it
    // is shared by every screen, and this constraint belongs to the one that
    // reads like a paper. The right rail stays inside this same container,
    // centred with the main column as a pair, rather than moving elsewhere.
    // The Paper tab is the exception (IR-372): the reader and Ask IRIS use
    // the whole width, so a wide screen gives the paper more room instead of
    // margins.
    <div className={cn(!onPaperTab && "max-w-6xl mx-auto")}>
      <div
        className={cn(
          "lg:flex lg:gap-6 lg:items-start",
          dock === "left" && "lg:flex-row-reverse",
        )}
      >
        <div className="min-w-0 lg:flex-1">
          {/* The Abstract / Paper switch floats just under the app header,
              so either view is one click away at any depth (IR-356). */}
          <div className={cn("sticky z-30 flex justify-center mb-4 pointer-events-none", VIEW_SWITCH_TOP)}>
            <div
              role="tablist"
              aria-label="Paper view"
              className="pointer-events-auto inline-flex gap-1 rounded-full bg-white/90 backdrop-blur p-0.5 shadow-card-md ring-1 ring-stone-200"
            >
              <button
                type="button"
                role="tab"
                aria-selected={tab === "abstract"}
                onClick={() => setTab("abstract")}
                className={cn(
                  "min-h-11 px-6 rounded-full text-md font-semibold transition-colors duration-200",
                  tab === "abstract" ? "bg-brand text-white shadow-card" : "text-stone-600 hover:text-brand",
                )}
              >
                Abstract
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "paper"}
                onClick={() => setTab("paper")}
                disabled={!hasPaper}
                title={hasPaper ? undefined : "No paper file has been uploaded for this record yet."}
                className={cn(
                  "min-h-11 px-6 rounded-full text-md font-semibold transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed",
                  tab === "paper" ? "bg-brand text-white shadow-card" : "text-stone-600 hover:text-brand",
                )}
              >
                Paper
              </button>
            </div>
          </div>

          <div
            className={cn(
              "grid gap-6 items-start",
              showRail && "lg:grid-cols-[minmax(0,1fr)_20rem]",
            )}
          >
          {/* ------------------------------------------------------------- */}
          {/* Main column                                                    */}
          {/* ------------------------------------------------------------- */}
          <div className="min-w-0 space-y-6">
            {/* Editorial header (IR-356): where it sits, what it is, who
                wrote it, then what to do with it. */}
            <header className="space-y-3">
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="inline-flex items-center gap-2 min-h-11 -my-2 text-sm font-medium text-stone-500 hover:text-brand transition-colors duration-200"
              >
                <i className="fas fa-arrow-left text-2xs" aria-hidden />
                Back
              </button>

              <div className="flex items-center gap-x-3 gap-y-2 flex-wrap">
                {(record.record_type_name || record.classification_name) && (
                  <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand">
                    {[record.record_type_name, record.classification_name].filter(Boolean).join(" · ")}
                  </p>
                )}
                <StatusBadge state={record.workflow_state} label={record.workflow_state_label} />
              </div>

              <h1 className="font-display font-semibold text-3xl sm:text-4xl leading-tight text-stone-900 text-balance">
                {record.title}
              </h1>

              <div className="flex items-center gap-x-3 gap-y-2 flex-wrap text-sm text-stone-600">
                {primaryOwner && (
                  <span className="inline-flex items-center gap-2">
                    <span className="w-7 h-7 rounded-full bg-brand text-white text-2xs font-bold flex items-center justify-center" aria-hidden>
                      {initials(primaryOwner.full_name)}
                    </span>
                    <span className="font-semibold text-stone-800">{primaryOwner.full_name}</span>
                  </span>
                )}
                <span>Cebu Institute of Technology – University</span>
              </div>

              <div className="flex items-center gap-x-4 gap-y-1 flex-wrap text-xs text-stone-500">
                <span className="inline-flex items-center gap-1.5">
                  <i className="fas fa-calendar text-2xs" aria-hidden />
                  Added {formatDate(record.created_at)}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <i className="fas fa-eye text-2xs" aria-hidden />
                  {record.access_count} view{record.access_count === 1 ? "" : "s"}
                </span>
                {record.is_ip && (
                  <span className="px-2 py-0.5 rounded-full bg-brand-50 text-brand ring-1 ring-brand-200 font-semibold inline-flex items-center gap-1">
                    <i className="fas fa-shield-halved text-2xs" aria-hidden />
                    Intellectual Property
                  </span>
                )}
                {record.ip_type && (
                  <span className="px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 font-semibold">
                    {IP_TYPE_LABELS[record.ip_type]}
                  </span>
                )}
                {record.for_commercialization && (
                  <span className="px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 font-semibold">
                    For Commercialization
                  </span>
                )}
                {record.community_extension && (
                  <span className="px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 font-semibold">
                    Community Extension
                  </span>
                )}
              </div>

              {tab === "abstract" && (
                // One filled action (IR-356): the reviewer's review, else the
                // adviser's completion, else a reader's Save.
                <div className="flex items-center gap-2 flex-wrap pt-1">
                  {userCanReview && (
                    <Link to={`/review/${record.id}/evaluate`} className={PILL_PRIMARY}>
                      <i className="fas fa-clipboard-check text-xs" aria-hidden />
                      Review this record
                    </Link>
                  )}

                  {canComplete && (
                    <button
                      type="button"
                      onClick={handleComplete}
                      disabled={completing}
                      className={userCanReview ? PILL_SECONDARY : PILL_PRIMARY}
                    >
                      <i className="fas fa-circle-check text-xs" aria-hidden />
                      {completing ? "Marking…" : "Mark as completed"}
                    </button>
                  )}

                  <PaperSaveDropdown
                    record={record}
                    variant="pill"
                    emphasis={userCanReview || canComplete ? "secondary" : "primary"}
                  />

                  <button type="button" onClick={() => setCiteOpen(true)} className={PILL_SECONDARY}>
                    <i className="fas fa-quote-right text-2xs" aria-hidden />
                    Cite
                  </button>

                  <button type="button" onClick={handleShare} className={PILL_SECONDARY}>
                    <i
                      className={cn(
                        "fas text-2xs",
                        shareState === "copied" ? "fa-check text-brand" : shareState === "failed" ? "fa-circle-exclamation" : "fa-link",
                      )}
                      aria-hidden
                    />
                    {shareState === "copied" ? "Link copied" : shareState === "failed" ? "Couldn\u2019t copy" : "Share"}
                  </button>
                  <span className="sr-only" role="status" aria-live="polite">
                    {shareState === "copied"
                      ? "Link to this paper copied"
                      : shareState === "failed"
                        ? "Couldn\u2019t copy the link. Copy it from the address bar."
                        : ""}
                  </span>
                </div>
              )}
              {completeError && <p className="text-xs text-brand">{completeError}</p>}
            </header>

            {/* Owner-actionable banners */}
            {canBeResubmitted && (
              <div className="rounded-2xl border border-brand-200 bg-brand-50 p-4">
                <p className="text-sm font-bold text-brand-dark flex items-center gap-2">
                  <i className="fas fa-arrow-rotate-left text-xs" aria-hidden />
                  Revision requested
                </p>
                <p className="text-sm text-brand leading-relaxed mt-1">
                  Address the reviewer comments below, then resubmit. Offices that already cleared
                  this record keep their clearance — only the office that asked for changes reviews
                  it again.
                </p>
                <button
                  type="button"
                  onClick={handleResubmit}
                  disabled={resubmitting}
                  className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-bold hover:bg-brand-light disabled:opacity-60 transition-colors"
                >
                  <i className="fas fa-paper-plane text-2xs" aria-hidden />
                  {resubmitting ? "Resubmitting…" : "Resubmit for review"}
                </button>
                {resubmitError && <p className="text-xs text-brand mt-2">{resubmitError}</p>}
              </div>
            )}

            {userIsOwner && (
              <ActionRequiredPanel
                recordId={record.id}
                onChanged={handleDocumentRequestChanged}
              />
            )}

            {record.pipeline_status === "rejected" && (
              <div className="rounded-2xl border border-brand-200 bg-brand-50 p-4">
                <p className="text-sm font-bold text-brand-dark flex items-center gap-2">
                  <i className="fas fa-circle-xmark text-xs" aria-hidden />
                  This record was rejected
                </p>
                <p className="text-sm text-brand leading-relaxed mt-1">
                  It cannot be resubmitted. Contact the relevant office if you have questions.
                </p>
              </div>
            )}

            {tab === "paper" ? (
              hasPaper ? (
                <Suspense
                  fallback={<Skeleton rows={8} label="Loading the reader…" />}
                >
                  <PaperPdfReader
                    recordId={record.id}
                    scrollToPage={openAtPage}
                    highlightRegions={highlightRegions}
                    navKey={location.key}
                    toolbarStart={
                      !chat.open && (
                        <Button
                          variant="outline"
                          onClick={() => chat.setOpen(true)}
                          title="Ask IRIS about this paper"
                          className="min-h-11 lg:min-h-8 mr-1 font-semibold"
                        >
                          <AskIrisMark className="w-4 h-4 text-brand" />
                          Ask IRIS
                        </Button>
                      )
                    }
                  />
                </Suspense>
              ) : (
                <p className="text-sm text-stone-400 italic py-8 text-center">
                  No paper file has been uploaded for this record yet.
                </p>
              )
            ) : (
              <>
            {/* Abstract, as a reading column: a measure of ~65 characters
                and relaxed leading, not justified text (IR-356). */}
            <section>
              <SectionHeading>Abstract</SectionHeading>
              {record.abstract ? (
                <p className="max-w-prose text-lg text-stone-700 leading-7">
                  {record.abstract}
                </p>
              ) : (
                <p className="text-sm text-stone-500 italic">
                  No abstract was provided for this record.
                </p>
              )}
            </section>

            {/* Request documents, and the requests this reviewer made:
                accept, reject, withdraw (IR-262, IR-263). */}
            <ReviewerDocumentRequests
              record={record}
              onChanged={handleDocumentRequestChanged}
            />

            <PaperAiOverview record={record} />

            {/* Authors */}
            {record.authors.length > 0 && (
              <section>
                <SectionHeading>Authors</SectionHeading>
                <div className="flex flex-wrap gap-2">
                  {record.authors.map((a) => (
                    <span
                      key={a.id}
                      className="px-3 py-1.5 rounded-full bg-white ring-1 ring-stone-200 text-sm font-medium text-stone-700"
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
              </>
            )}
          </div>

          {/* ------------------------------------------------------------- */}
          {/* Right rail                                                     */}
          {/* ------------------------------------------------------------- */}
          {/* Never on the Paper tab (IR-372). On the Abstract tab, not shown
              while chat is docked (IR-351): a docked chat beside the rail
              squeezed the paper under it. Floating or closing the chat brings
              it back. Sticky below the fixed 58px header, capped
              to the viewport and scrollable, because a sticky rail taller
              than the window would hide its lower cards until the paper
              ended. */}
          {showRail && (
            <aside className={cn("space-y-4 lg:sticky lg:overflow-y-auto", PANE_TOP, PANE_MAX_HEIGHT)}>
              <ReviewRoutingTracker key={trackerVersion} recordId={record.id} />
              <PaperGovernance record={record} />
              <PaperDocuments recordId={record.id} files={record.files} />
            </aside>
          )}
        </div>

        <PaperCiteModal record={record} isOpen={citeOpen} onClose={() => setCiteOpen(false)} />
      </div>

      {chat.open ? (
        <PaperChatPanel
          record={record}
          dock={dock}
          onDockChange={chat.setDockMode}
          onClose={() => chat.setOpen(false)}
          canChangePosition={!onPaperTab}
          minimized={chatMinimized}
          onRestore={() => chat.setMinimized(false)}
          className={chatPanelClass}
        />
      ) : (
        // On the Paper tab the way back sits in the reader's toolbar instead,
        // so nothing floats over the paper (IR-372).
        !onPaperTab && <PaperChatLauncher onOpen={() => chat.setOpen(true)} />
      )}
      </div>
    </div>
  );
}
