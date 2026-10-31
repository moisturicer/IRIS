import { useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { seatsApi } from "@/api/reviews";
import { errorDetail } from "@/lib/errorDetail";
import { useElementWidth } from "@/hooks/useElementWidth";
import { cn } from "@/lib/utils";
import type { RecordTracker } from "@/types/records";

import { ReadinessPanel, ReadinessSummary } from "./ReadinessPanel";
import { ReviewActionBar } from "./ReviewActionBar";
import { detailsTarget, ReviewDetails } from "./ReviewDetails";
import { ReviewTimeline } from "./ReviewTimeline";
import { REVIEW_ACTIONS } from "./reviewActions";
import type { ReviewWorkspaceProps } from "./ReviewWorkspace";
import "./reviewWorkspace.css";

const WIDTHS_KEY = "iris-review-cols";

/**
 * Who reviews moves to the sidebar's Reviewers (ADR-032 §10 Amendment): the
 * existing route and add-reviewer acts, named as the contract names them.
 * Everything else stays in the footer.
 */
const SIDEBAR_LABELS: Partial<Record<string, string>> = { route: "Request review…", add_reviewer: "Add a colleague…" };
const SIDEBAR_ACTIONS = REVIEW_ACTIONS.filter((a) => a.capability in SIDEBAR_LABELS)
  .map((a) => ({ ...a, label: SIDEBAR_LABELS[a.capability]! }));
const FOOTER_ACTIONS = REVIEW_ACTIONS.filter((a) => !(a.capability in SIDEBAR_LABELS));
type Widths = { mid: number | null; side: number | null };

function readWidths(): Widths {
  try {
    const value = JSON.parse(localStorage.getItem(WIDTHS_KEY) ?? "null");
    const valid = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
    return { mid: valid(value?.mid) ? value.mid : null, side: valid(value?.side) ? value.side : null };
  } catch {
    return { mid: null, side: null };
  }
}

/** One geometry for pointer, keyboard, restored widths and container changes. */
function fitWidths(width: number, wanted: Widths) {
  const w = width || 1600;
  let mid = Math.max(320, Math.min(wanted.mid ?? w * .3, w / 2));
  const side = Math.max(220, Math.min(wanted.side ?? w * .2, 420, mid - 40));
  mid = Math.max(320, Math.min(mid, w - 480 - (w >= 1200 ? side : 0)));
  // The paper's minimum can reduce the pane after the first sidebar clamp.
  return { mid: Math.floor(mid), side: Math.floor(Math.min(side, mid - 40)) };
}

export function ReviewWorkspaceLayout({ record, can, reader, timelineVersion, onChanged, onAskAboutPaper, onOpenReview }: ReviewWorkspaceProps) {
  const [observe, width] = useElementWidth<HTMLDivElement>();
  const [wanted, setWanted] = useState(readWidths);
  const sizes = fitWidths(width, wanted);
  const [statusTarget, setStatusTarget] = useState<HTMLDivElement | null>(null);
  const [tab, setTab] = useState<"conversation" | "details">("conversation");
  const [open, setOpen] = useState(true);
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);
  const pane = useRef<HTMLElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const ids = useId();
  const drawer = width > 0 && width < 900 && Boolean(reader);
  const folded = width > 0 && width < 1200;
  const drag = useRef<{ key: keyof Widths; x: number; mid: number; side: number } | null>(null);

  // Deferred, so the drawer's focus trap is gone before the launcher is focused.
  const closeDrawer = () => {
    setOpen(false);
    requestAnimationFrame(() => launcher.current?.focus());
  };

  const update = (next: Widths) => {
    setWanted(next);
    try { localStorage.setItem(WIDTHS_KEY, JSON.stringify(next)); } catch { /* Defaults still render. */ }
  };

  useEffect(() => {
    if (!folded) setTab("conversation");
  }, [folded]);

  useEffect(() => {
    if (!drawer || !open) return;
    pane.current?.focus();
    const otherDialog = (target: EventTarget | null) => target instanceof Element &&
      target.closest('[role="dialog"],[role="alertdialog"]') != null &&
      target.closest('[role="dialog"],[role="alertdialog"]') !== pane.current;
    const keepFocus = (e: FocusEvent) => {
      if (e.target instanceof Node && !pane.current?.contains(e.target) && !otherDialog(e.target)) pane.current?.focus();
    };
    const escape = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented && !otherDialog(e.target)) closeDrawer();
    };
    document.addEventListener("focusin", keepFocus);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("focusin", keepFocus);
      document.removeEventListener("keydown", escape);
    };
  }, [drawer, open]);

  const startDrag = (key: keyof Widths, e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    drag.current = { key, x: e.clientX, ...sizes };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const edge = (key: keyof Widths, label: string) => (
    <div
      role="separator" tabIndex={0} aria-label={label} aria-orientation="vertical"
      aria-controls={`${ids}-${key}`} aria-valuenow={sizes[key]} aria-valuemin={key === "mid" ? 320 : 220}
      aria-valuemax={key === "mid" ? Math.max(320, Math.min(width / 2, width - 480 - (folded ? 0 : sizes.side))) : Math.min(420, sizes.mid - 40)}
      className="review-resize-edge"
      onPointerDown={(e) => startDrag(key, e)}
      onPointerMove={(e) => {
        const from = drag.current;
        if (!from || from.key !== key) return;
        update(fitWidths(width, { mid: from.mid, side: from.side, [key]: from[key] + from.x - e.clientX }));
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }}
      onDoubleClick={() => update({ ...wanted, [key]: null })}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        update(fitWidths(width, { ...sizes, [key]: sizes[key] + (e.key === "ArrowLeft" ? 24 : -24) }));
      }}
    />
  );

  const details = <div ref={setStatusTarget} />;
  const footer = useRef<HTMLElement>(null);
  // A Readiness link reuses a control the page already has; a sidebar target
  // folded into Details opens that tab first, then takes focus.
  const goTo = (to: string) => {
    if (folded) setTab("details");
    requestAnimationFrame(() => document.getElementById(detailsTarget(ids, to))?.focus());
  };
  const onReadinessAction = (action: { kind: string; target: string | null }) => {
    if (action.kind === "open_review") void onOpenReview?.();
    else if (action.kind === "claim") void claim();
    else if (action.kind === "open_documents") goTo("documents");
    else if (action.kind === "show_party") goTo(action.target ?? "reviewers");
    // The footer's own Withdraw asks first, as it always has.
    else if (action.kind === "withdraw_revision") {
      Array.from(footer.current?.querySelectorAll("button") ?? [])
        .find((b) => b.textContent?.includes("Withdraw revision request"))?.focus();
    }
  };
  const renderDetails = (tracker: RecordTracker) => (
    <ReviewDetails record={record} tracker={tracker} ids={ids} reviewerActions={
      <ReviewActionBar record={record} can={can} actions={SIDEBAR_ACTIONS} label="Reviewer actions"
        primary={false} onChanged={onChanged} className="pt-1" />
    } />
  );
  const ownSeat = record.my_seats.find((s) => s.state === "assigned" || s.state === "in_review") ?? record.my_seats[record.my_seats.length - 1];
  const claim = async () => {
    if (!record.review_claim || claiming) return;
    setClaiming(true);
    setClaimError(null);
    try {
      await seatsApi.claim(record.review_claim.assignment);
      onChanged();
    } catch (error) {
      setClaimError(errorDetail(error, "Could not claim this review. Please try again."));
    } finally {
      setClaiming(false);
    }
  };
  return (
    <div ref={observe} className="review-workspace-container">
      <div className={cn("review-workspace", !reader && "review-without-paper")}
        style={{ "--mid-w": `${sizes.mid}px`, "--side-w": `${sizes.side}px` } as CSSProperties}>
        {reader && <div className="review-paper" {...(drawer && open ? { inert: "" } : {})}>{reader}</div>}
        <section ref={pane} id={`${ids}-mid`} aria-label="Review pane" tabIndex={-1}
          role={drawer && open ? "dialog" : "region"} aria-modal={drawer && open || undefined}
          aria-hidden={drawer && !open || undefined} {...(drawer && !open ? { inert: "" } : {})}
          className={cn("review-pane", open && "review-pane-open")}>
          {!drawer && reader && edge("mid", "Resize the review pane")}
          <header className="review-pane-head">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wider text-stone-500">Review workspace / current record</p>
                {record.current_holders.length > 0 && (
                  <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-full border border-brand/40 bg-brand/5 px-2 py-0.5 text-2xs font-semibold text-brand">
                    <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
                    With {record.current_holders.map((h) => h.label).join(", ")}
                  </p>
                )}
                <h2 className="font-display text-xl font-semibold text-stone-900 mt-1">Review</h2>
              </div>
              {drawer && <button type="button" className={cn("review-control text-brand", FOCUS_RING)}
                onClick={closeDrawer}>Back to paper</button>}
            </div>
            {record.readiness && (
              <ReadinessSummary readiness={record.readiness} onShow={() => {
                setTab("conversation");
                requestAnimationFrame(() => {
                  const panel = document.getElementById(`${ids}-readiness`);
                  panel?.scrollIntoView({ block: "start" });
                  panel?.focus({ preventScroll: true });
                });
              }} />
            )}
            <div role="tablist" aria-label="Review pane sections" onKeyDown={(e) => {
              if (!folded || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
              e.preventDefault();
              const next = e.key === "Home" ? "conversation" : e.key === "End" ? "details" : tab === "conversation" ? "details" : "conversation";
              setTab(next);
              document.getElementById(`${ids}-tab-${next}`)?.focus();
            }}>
              {(["conversation", ...(folded ? ["details"] : [])] as const).map((name) => (
                <button key={name} type="button" role="tab" id={`${ids}-tab-${name}`}
                  aria-selected={tab === name} aria-controls={`${ids}-${name}`} tabIndex={tab === name ? 0 : -1}
                  onClick={() => setTab(name as typeof tab)} className={cn("review-tab", FOCUS_RING)}>
                  {name === "conversation" ? "Conversation" : "Details"}
                </button>
              ))}
            </div>
          </header>
          <div className="review-pane-body">
            <div role="tabpanel" id={`${ids}-conversation`} aria-labelledby={`${ids}-tab-conversation`} hidden={tab !== "conversation"} className="p-4">
              {onAskAboutPaper && <button type="button" onClick={onAskAboutPaper} className={cn("review-control text-brand hover:underline", FOCUS_RING)}>Ask about this paper</button>}
              <ReviewTimeline key={`${record.id}-${timelineVersion}`} recordId={record.id} canComment={can.has("comment_review")} statusTarget={statusTarget}
                renderStatus={renderDetails}
                beforeComment={record.readiness ? <ReadinessPanel id={`${ids}-readiness`} readiness={record.readiness} onAction={onReadinessAction} /> : null} />
            </div>
            {folded && <div role="tabpanel" id={`${ids}-details`} aria-labelledby={`${ids}-tab-details`} hidden={tab !== "details"} className="p-4">{details}</div>}
          </div>
          <footer ref={footer} className="review-pane-foot" aria-label="Your review">
            <p className="text-small font-semibold text-stone-900"><i className="fas fa-clipboard-check mr-2" aria-hidden />Your review: {ownSeat?.verdict_label ?? ownSeat?.state_label ?? "No verdict recorded"}</p>
            {record.review_claim
              ? <button type="button" disabled={claiming} onClick={() => void claim()} className={cn(PILL_PRIMARY, FOCUS_RING)}>{claiming ? "Claiming…" : record.review_claim.label}</button>
              : can.has("open_review") && <button type="button" onClick={() => void onOpenReview?.()} className={cn(PILL_PRIMARY, FOCUS_RING)}>Open review</button>}
            {claimError && <p role="alert" className="text-small text-brand">{claimError}</p>}
            <ReviewActionBar record={record} can={can} actions={FOOTER_ACTIONS} onChanged={onChanged} primary={!can.has("open_review") && !record.review_claim} />
          </footer>
        </section>
        {!folded && <aside id={`${ids}-side`} aria-label="Review details" className="review-details">
          {edge("side", "Resize the details sidebar")}
          <p className="text-2xs font-semibold uppercase tracking-wider text-brand">Record context</p>
          <h2 className="font-display text-xl font-semibold text-stone-900 mb-4">People &amp; details</h2>
          {details}
        </aside>}
        {drawer && <div className="review-paper-foot"><button ref={launcher} type="button" className={cn("review-control text-brand font-semibold", FOCUS_RING)} onClick={() => setOpen(true)}>Open review pane</button></div>}
      </div>
    </div>
  );
}
