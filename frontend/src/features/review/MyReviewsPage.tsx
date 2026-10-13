import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { reviewsApi, seatsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ResearchCard } from "@/components/shared/ResearchCard";
import { Badge, Button, Skeleton } from "@/components/ui";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { errorDetail } from "@/features/document-requests/errorDetail";
import { cn, formatDate } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { MyReviewsPage as Page, MyReviewsRow, MyReviewsTab } from "@/types/reviews";

import { AssignReviewerDialog } from "./AssignReviewerDialog";
import {
  OUTCOME_FILTERS,
  TABS,
  WAITING_ON_LABEL,
  holderLine,
  readView,
  routingLine,
  viewSearch,
  waitLabel,
  type MyReviewsView,
} from "./myReviews";

/**
 * My Reviews (IR-268; ADR-032 §9 and its 2026-10-08 Amendment, ui-ux/16 §5).
 *
 * Your own seats plus your office's pool, as the work to do (To review), the
 * work under way (In review) and the decisions made (Done). It replaces the
 * Review Queue's Awaiting me / Cleared / Sent back, whose tabs were outcomes:
 * here outcomes are filters on Done.
 *
 * The page is a locator. Every row opens the record's Paper View at its
 * Review section, where *Open review* records when the review starts. The
 * only acts here are *Claim* and *Assign*, on an office's unclaimed records;
 * after either the page refetches and says where the row went. Nothing polls.
 *
 * What the server says decides everything shown: who may claim or assign is
 * on each row, and a coordinator is known from `review_access`.
 */
export default function MyReviewsPage() {
  const [params, setParams] = useSearchParams();
  const { view, replace } = readView(params);
  const viewer = useAuthStore((s) => s.user);
  const access = viewer?.review_access;
  const coordinatorOffice = access?.is_coordinator ? access.offices[0] ?? null : null;

  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [assigning, setAssigning] = useState<MyReviewsRow | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const ids = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // The retired Review Queue's `?status=` is translated once, then replaced.
  useEffect(() => {
    if (replace != null) setParams(replace, { replace: true });
  }, [replace, setParams]);

  const { tab, outcome, office } = view;

  /** Reload the tab; whether it worked, so an act announces only what is shown. */
  const load = useCallback(async (): Promise<boolean> => {
    setLoadError(null);
    try {
      const { data } = await reviewsApi.mine({ tab, outcome, office, cursor: null });
      setPage(data);
      return true;
    } catch {
      // An empty tab and a failed request must not look alike.
      setLoadError("My Reviews could not be loaded.");
      return false;
    }
  }, [tab, outcome, office]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setRowErrors({});
    load().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const go = (next: Partial<MyReviewsView>) => {
    const merged = { ...view, ...next };
    if (merged.tab !== "done") merged.outcome = null;
    setAnnouncement("");
    setParams(viewSearch(merged));
  };

  const showMore = async () => {
    if (!page?.next) return;
    setLoadingMore(true);
    try {
      const { data } = await reviewsApi.mine({ tab, outcome, office, cursor: page.next });
      setPage({ ...data, rows: [...page.rows, ...data.rows] });
    } catch {
      setLoadError("More of Done could not be loaded.");
    } finally {
      setLoadingMore(false);
    }
  };

  const claim = async (row: MyReviewsRow) => {
    if (row.assignment == null) return;
    setBusy(row.key);
    setAnnouncement("");
    setRowErrors((e) => ({ ...e, [row.key]: "" }));
    try {
      await seatsApi.claim(row.assignment);
      if (await load()) setAnnouncement("Claimed. It's in To review as yours.");
    } catch (err) {
      setRowErrors((e) => ({ ...e, [row.key]: errorDetail(err, "The review could not be claimed.") }));
    } finally {
      setBusy(null);
    }
  };

  const assigned = async (name: string, self: boolean) => {
    setAssigning(null);
    if (!(await load())) return;
    setAnnouncement(self ? "Assigned to you. It's in To review as yours." : `Assigned to ${name}. It's in their To review.`);
  };

  const onTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    e.preventDefault();
    const at = TABS.findIndex((t) => t.key === tab);
    const next = TABS[(at + step + TABS.length) % TABS.length].key;
    go({ tab: next });
    tabRefs.current[next]?.focus();
  };

  const officeLabel = coordinatorOffice?.toUpperCase() ?? "";
  const rows = page?.rows ?? [];

  return (
    <div>
      <PageHeader
        title="My Reviews"
        description="What you need to review, what you have opened, and what you have finished."
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="My Reviews"
          onKeyDown={onTabKeyDown}
          className="inline-flex flex-wrap gap-1 rounded-full bg-stone-100 p-1"
        >
          {TABS.map((t) => {
            const active = t.key === tab;
            const count = page?.counts[t.key];
            return (
              <button
                key={t.key}
                ref={(el) => {
                  tabRefs.current[t.key] = el;
                }}
                id={`${ids}-tab-${t.key}`}
                type="button"
                role="tab"
                aria-selected={active}
                aria-controls={`${ids}-panel`}
                tabIndex={active ? 0 : -1}
                onClick={() => go({ tab: t.key })}
                className={cn(
                  "min-h-11 px-4 rounded-full text-small font-semibold",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                  active ? "bg-brand text-white shadow-card" : "text-stone-600 hover:text-brand",
                )}
              >
                {t.label}
                {count != null && " "}
                {count != null && (
                  <span className={cn("ml-1 tabular-nums", active ? "text-white" : "text-stone-500")}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {coordinatorOffice && (
          <div role="group" aria-label="Whose reviews" className="inline-flex gap-1 rounded-full border border-stone-200 p-1">
            {[
              { key: null, label: "Mine" },
              { key: coordinatorOffice, label: `All of ${officeLabel}` },
            ].map((choice) => (
              <button
                key={choice.label}
                type="button"
                aria-pressed={office === choice.key}
                onClick={() => go({ office: choice.key })}
                className={cn(
                  "min-h-11 px-3 rounded-full text-small font-medium",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                  office === choice.key ? "bg-stone-900 text-white" : "text-stone-600 hover:text-brand",
                )}
              >
                {choice.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Polite, and always rendered, so a change to it is what gets announced. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <div id={`${ids}-panel`} role="tabpanel" aria-labelledby={`${ids}-tab-${tab}`}>
        {tab === "done" && (
          <div role="group" aria-label="Filter by outcome" className="mb-4 flex flex-wrap gap-2">
            {[{ key: null, label: "All" }, ...OUTCOME_FILTERS].map((f) => (
              <button
                key={f.label}
                type="button"
                aria-pressed={outcome === f.key}
                onClick={() => go({ outcome: f.key })}
                className={cn(
                  "min-h-9 px-3 rounded-full border text-small font-medium",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                  outcome === f.key
                    ? "border-brand bg-brand-50 text-brand"
                    : "border-stone-200 text-stone-600 hover:border-stone-400",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <Skeleton rows={3} label="Loading My Reviews…" />
        ) : loadError && !page ? (
          <EmptyState icon="fa-triangle-exclamation" tone="error" title="Could not load My Reviews" message={loadError} />
        ) : rows.length === 0 ? (
          <EmptyState icon={EMPTY_ICON[tab]} {...emptyCopy(tab, outcome, office ? officeLabel : access?.offices[0]?.toUpperCase())} />
        ) : (
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.key}>
                <ReviewRow
                  row={r}
                  tab={tab}
                  busy={busy === r.key}
                  error={rowErrors[r.key] || null}
                  onClaim={() => claim(r)}
                  onAssign={() => setAssigning(r)}
                />
              </li>
            ))}
          </ul>
        )}

        {loadError && page && (
          <p role="alert" className={cn(LOAD_ERROR, "mt-3")}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {loadError}
          </p>
        )}

        {tab === "done" && page?.next && !loading && (
          <div className="mt-4 flex justify-center">
            <Button type="button" variant="secondary" onClick={showMore} loading={loadingMore}>
              Show more
            </Button>
          </div>
        )}
      </div>

      {assigning?.assignment != null && (
        <AssignReviewerDialog
          assignmentId={assigning.assignment}
          recordTitle={assigning.title}
          viewerId={viewer?.id ?? null}
          onClose={() => setAssigning(null)}
          onAssigned={assigned}
        />
      )}
    </div>
  );
}

const EMPTY_ICON: Record<MyReviewsTab, string> = {
  to_review: "fa-inbox",
  in_review: "fa-book-open",
  done:      "fa-check",
};

/** Empty states say what arrives there, not "no data" (ui-ux/16 §5). */
function emptyCopy(tab: MyReviewsTab, outcome: string | null, office: string | undefined) {
  if (tab === "to_review") {
    return {
      title: "Nothing to review",
      message: office
        ? `Records routed to ${office} appear here until someone claims them, and so do the reviews you are given.`
        : "Records your advisees submit, and reviews you are given, appear here.",
    };
  }
  if (tab === "in_review") {
    return {
      title: "Nothing in review",
      message: "A review you open stays here until you finish it.",
    };
  }
  if (outcome) {
    const label = OUTCOME_FILTERS.find((f) => f.key === outcome)?.label ?? outcome;
    return { title: `Nothing ${label.toLowerCase()}`, message: "Try All to see every decision you have made." };
  }
  return {
    title: "No decisions yet",
    message: "Records you finish reviewing stay here as your decision history.",
  };
}

interface ReviewRowProps {
  row:      MyReviewsRow;
  tab:      MyReviewsTab;
  busy:     boolean;
  error:    string | null;
  onClaim:  () => void;
  onAssign: () => void;
}

function ReviewRow({ row, tab, busy, error, onClaim, onAssign }: ReviewRowProps) {
  const href = `/records/${row.record}?section=review`;
  const routing = routingLine(row);

  const status = (
    <>
      <span className="font-semibold text-stone-800">{holderLine(row)}</span>
      {row.waiting_on && tab !== "done" && <Badge variant="warning">{WAITING_ON_LABEL[row.waiting_on]}</Badge>}
      {tab === "done" && (
        <Badge variant={row.outcome == null ? "default" : "success"}>
          {row.outcome_label ?? "Completed by your office"}
        </Badge>
      )}
    </>
  );

  const meta =
    tab === "done"
      ? row.decided_at && <span>{formatDate(row.decided_at)}</span>
      : row.waiting_days != null && <span>Waiting {waitLabel(row.waiting_days)}</span>;

  // A record waiting on its author shows the badge in place of any action
  // (ADR-032 §9 Amendment); its title still opens it.
  const waiting = tab !== "done" && row.waiting_on != null;
  let actions = null;
  if (waiting || tab === "done") {
    // No action: the badge, or the outcome, says where the record stands.
  } else if (row.kind === "pool") {
    actions = (
      <>
        {row.can_assign && (
          <Button type="button" variant="secondary" size="sm" onClick={onAssign} aria-label={`Assign reviewer: ${row.title}`}>
            Assign reviewer
          </Button>
        )}
        {row.can_claim && (
          <Button type="button" size="sm" onClick={onClaim} loading={busy} aria-label={`Claim review: ${row.title}`}>
            Claim review
          </Button>
        )}
      </>
    );
  } else {
    // A link, not a button: *Open review* is recorded in Paper View alone.
    const label = tab === "in_review" ? "Continue review" : "Open review";
    actions = (
      <Link
        to={href}
        aria-label={`${label}: ${row.title}`}
        className={cn(
          "inline-flex min-h-9 items-center rounded-lg bg-brand px-3 text-small font-semibold text-white hover:bg-brand-dark",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        {label}
      </Link>
    );
  }

  return (
    <div>
      <ResearchCard
        href={href}
        title={row.title}
        eyebrow={row.record_type_name ?? "Unspecified type"}
        meta={meta || undefined}
        byline={routing ?? undefined}
        status={status}
        actions={actions ?? undefined}
      />
      {error && (
        <p role="alert" className={cn(LOAD_ERROR, "mt-2")}>
          <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}
