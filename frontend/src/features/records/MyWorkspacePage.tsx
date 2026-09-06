/**
 * My Workspace — case-tracking redesign of the old plain-table MyRecordsPage
 * (mode="workspace"; that route now points here, mode="library" was already
 * dead code once /records/mine moved to MyLibraryPage).
 *
 * Rebuilt from a user-supplied mockup (screenshots/Workspave.png) after being
 * grilled on it first (see iris-my-workspace-design memory). Every stat,
 * badge and stage shown here is derived from real data — the mockup's own
 * TRL score, "novelty %", "Technology Business Incubator" office and
 * patent-counsel activity text were cut entirely: none of it exists anywhere
 * in the SRS, ADRs, or Jira, and building it for real would mean a whole
 * unspecified assessment sub-workflow, not a dashboard redesign. The one
 * cosmetic addition kept is the formatted case id (`DISC-2026-0042`) — it
 * invents nothing, it's `record.id` and its year, formatted.
 *
 * `/records/mine/` already returns RecordDetailSerializer's payload
 * (clearances, ip_type, requested_itso/ierc/ktto — see api/records.ts),
 * so nothing on the backend needed to change for this page.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import type { RecordDetail } from "@/types/records";
import { metaBadges, BADGE_TONE_CLASS } from "@/features/discover/discoverUtils";
import { WorkspaceOfficePills } from "./WorkspaceOfficePills";
import {
  currentStage,
  stageSequence,
  stageLabel,
  currentOfficeLabel,
  pendingClearances,
  inIpAssessment,
  inCommercialization,
  formatCaseId,
  needsAuthorAction,
  type WorkspaceStage,
} from "@/lib/workspaceStages";
import { formatDate, cn } from "@/lib/utils";

type TabId = "all" | "validation" | "review_routing" | "ip_assessment" | "commercialization" | "past_review";

const TABS: { id: TabId; label: string }[] = [
  { id: "all", label: "All Cases" },
  { id: "validation", label: "Validation" },
  { id: "review_routing", label: "Review & Routing" },
  { id: "ip_assessment", label: "IP Assessment" },
  { id: "commercialization", label: "Commercialization" },
  // "Past Review", not "Completed": it holds both an approved Proposal whose
  // research is still ongoing and a genuinely finished one. Labelling it
  // "Completed" would contradict the card's own "Research Ongoing" badge.
  { id: "past_review", label: "Past Review" },
];

function matchesTab(record: RecordDetail, tab: TabId): boolean {
  if (tab === "all") return true;
  if (tab === "ip_assessment") return inIpAssessment(record);
  if (tab === "commercialization") return inCommercialization(record);
  if (tab === "past_review") {
    const stage = currentStage(record);
    return stage === "ongoing" || stage === "completed";
  }
  return currentStage(record) === (tab as WorkspaceStage);
}

export default function MyWorkspacePage() {
  const [records, setRecords] = useState<RecordDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<TabId>("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    recordsApi
      .mine()
      .then(({ data }) => setRecords(Array.isArray(data) ? data : []))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const activeCount = records.filter(
    (r) => !["published", "approved", "rejected", "pending_delete"].includes(r.pipeline_status),
  ).length;
  const ipAssessmentCount = records.filter(inIpAssessment).length;
  const commercializationCount = records.filter(inCommercialization).length;
  const actionsRequiredCount = records.filter(needsAuthorAction).length;

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return records
      .filter((r) => matchesTab(r, tab))
      .filter((r) => {
        if (!needle) return true;
        return (
          r.title.toLowerCase().includes(needle) ||
          formatCaseId(r).toLowerCase().includes(needle) ||
          currentOfficeLabel(r).toLowerCase().includes(needle)
        );
      });
  }, [records, tab, query]);

  return (
    <div>
      <PageHeader
        title="My Workspace"
        description="Track your research disclosures as they move through validation, routing, and office review."
        actions={
          <Link
            to="/records/add"
            className="inline-flex items-center gap-2 bg-brand text-white px-4 py-2 rounded-lg text-[13px] font-semibold hover:bg-brand-light transition-colors"
          >
            <i className="fas fa-file-signature text-[12px]" aria-hidden />
            Submit Disclosure
          </Link>
        }
      />

      {/* Stat cards — every number is a filter over records already fetched, not a separate query */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {[
          { label: "Active Cases", value: activeCount, icon: "fa-briefcase", sub: "Under institutional processing" },
          { label: "In IP Assessment", value: ipAssessmentCount, icon: "fa-scale-balanced", sub: "ITSO / IERC review" },
          { label: "In Commercialization", value: commercializationCount, icon: "fa-rocket", sub: "KTTO review" },
          {
            label: "Actions Required", value: actionsRequiredCount, icon: "fa-circle-exclamation",
            sub: "Pending author input", danger: true,
          },
        ].map((s) => (
          <div
            key={s.label}
            className={cn(
              "bg-white rounded-xl border p-4",
              s.danger && s.value > 0 ? "border-red-200 bg-red-50/40" : "border-stone-200",
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400">{s.label}</span>
              <i className={cn("fas", s.icon, "text-[13px]", s.danger && s.value > 0 ? "text-red-500" : "text-stone-300")} />
            </div>
            <p className={cn("text-[26px] font-bold leading-none", s.danger && s.value > 0 ? "text-red-600" : "text-stone-900")}>
              {s.value}
            </p>
            <p className="text-[11px] text-stone-400 mt-1">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Tabs + search */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex items-center gap-1 bg-white border border-stone-200 rounded-xl p-1 flex-wrap">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-colors whitespace-nowrap",
                tab === t.id ? "bg-brand text-white" : "text-stone-500 hover:bg-stone-50",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[12rem]">
          <i className="fas fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-[12px] text-stone-400" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by case #, title, office…"
            aria-label="Search your cases"
            className="w-full pl-9 pr-3 py-2 bg-white border border-stone-200 rounded-xl text-[13px] outline-none focus:border-brand/40 placeholder-stone-400"
          />
        </div>
      </div>

      {/* Case list */}
      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : failed ? (
        <div className="bg-white border border-stone-200 rounded-2xl p-8 text-center">
          <p className="text-[14px] font-semibold text-stone-700">Could not load your workspace</p>
          <p className="text-[12px] text-stone-500 mt-1">Please refresh and try again.</p>
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          icon="fa-folder-open"
          title={records.length === 0 ? "No disclosures yet" : "No cases match this view"}
          message={records.length === 0 ? "Submit your first research disclosure to start tracking it here." : "Try a different tab or search."}
        />
      ) : (
        <div className="space-y-3">
          {visible.map((record) => {
            const sequence = stageSequence(record);
            const at = currentStage(record);
            const atIndex = sequence.indexOf(at);
            const pending = pendingClearances(record);
            const badges = metaBadges(record).filter((b) => b.tone !== "topic"); // topic already implied by title context here
            const flagged = needsAuthorAction(record);

            return (
              <div
                key={record.id}
                className={cn(
                  "bg-white rounded-xl border p-4",
                  flagged ? "border-red-200" : "border-stone-200",
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500 text-[10px] font-mono font-semibold">
                        {formatCaseId(record)}
                      </span>
                      {badges.map((b) => (
                        <span
                          key={b.label}
                          className={cn("px-1.5 py-0.5 rounded text-[10px] font-semibold", BADGE_TONE_CLASS[b.tone])}
                        >
                          {b.label}
                        </span>
                      ))}
                      {flagged && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">
                          <i className="fas fa-circle-exclamation mr-1" aria-hidden />Action Required
                        </span>
                      )}
                    </div>

                    <Link to={`/records/${record.id}`} className="block text-[14px] font-bold text-stone-900 hover:text-brand leading-snug">
                      {record.title}
                    </Link>

                    <p className="text-[12px] text-stone-500 mt-2">
                      Office: <span className="font-medium text-stone-700">{currentOfficeLabel(record)}</span>
                      <span className="mx-1.5 text-stone-300">·</span>
                      Submitted: {formatDate(record.created_at)}
                    </p>

                    {pending.length > 0 && (
                      <div className="mt-2.5">
                        <WorkspaceOfficePills clearances={pending} />
                      </div>
                    )}
                  </div>

                  <div className="w-full sm:w-56 shrink-0">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-stone-400 mb-1.5 text-right">
                      {atIndex >= 0 ? `Stage ${atIndex + 1} of ${sequence.length}` : "Workflow stage"}
                    </p>
                    <div className="flex gap-1 mb-1.5">
                      {sequence.map((s, i) => (
                        <span
                          key={s}
                          className={cn(
                            "h-1.5 flex-1 rounded-full",
                            i < atIndex ? "bg-emerald-400" : i === atIndex ? "bg-brand" : "bg-stone-100",
                          )}
                        />
                      ))}
                    </div>
                    <p className="text-[12px] font-semibold text-stone-700 text-right">
                      {flagged ? "Awaiting your revision" : `Current: ${stageLabel(at)}`}
                    </p>
                    <div className="text-right mt-2">
                      <Link
                        to={`/records/${record.id}`}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-stone-200 text-[12px] font-semibold text-stone-600 hover:border-brand/40 hover:text-brand transition-colors"
                      >
                        Inspect Dossier <i className="fas fa-chevron-right text-[9px]" aria-hidden />
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
