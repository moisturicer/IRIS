import { useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { createPortal } from "react-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { seatsApi } from "@/api/reviews";
import { errorDetail } from "@/lib/errorDetail";
import { useElementWidth } from "@/hooks/useElementWidth";
import { seatToOpen } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordTracker } from "@/types/records";

import { ReadinessPanel, ReadinessSummary } from "./ReadinessPanel";
import { ReviewActionBar } from "./ReviewActionBar";
import { detailsTarget, ReviewDetails } from "./ReviewDetails";
import { ReviewTimeline } from "./ReviewTimeline";
import { REVIEW_ACTIONS, VERDICT_CAPABILITIES, type DialogReviewAction } from "./reviewActions";
import type { ShowPlace } from "./changes/ChangeItem";
import { ChangesTab } from "./changes/ChangesTab";
import { ReviewThreads } from "./threads/ReviewThreads";
import { useThreadsWorkspace } from "./threads/useThreadsWorkspace";
import type { ReviewWorkspaceProps } from "./ReviewWorkspace";
import "./reviewWorkspace.css";

const WIDTHS_KEY = "iris-review-cols";

/**
 * Who reviews moves to the sidebar's Reviewers (ADR-032 §10 Amendment): the
 * existing route and add-reviewer acts, as two separate controls (IR-685).
 * Everything else stays in the footer.
 */
const ADD_COLLEAGUE = REVIEW_ACTIONS.filter((a) => a.capability === "add_reviewer")
  .map((a) => ({ ...a, label: "Add a colleague…" }));
const ROUTE = REVIEW_ACTIONS.find((a): a is DialogReviewAction => a.capability === "route" && a.kind === "dialog");
const FOOTER_ACTIONS = REVIEW_ACTIONS.filter((a) => a.capability !== "route" && a.capability !== "add_reviewer");
/**
 * With *Finish review* granted every verdict goes through it, so the drafts
 * go with it (ADR-032 §7, IR-875): the footer keeps only the acts that are
 * not verdicts -- requesting documents, withdrawing a revision request.
 */
const FINISH_FOOTER_ACTIONS = FOOTER_ACTIONS.filter((a) => !VERDICT_CAPABILITIES.includes(a.capability));
type Tab = "conversation" | "threads" | "changes" | "details";

const TAB_NAMES: Record<Tab, string> = {
  conversation: "Conversation", threads: "Threads", changes: "Changes", details: "Details",
};
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

export function ReviewWorkspaceLayout({ record, can, reader, timelineVersion, onChanged, onDocuments, onOpenReview, onShowVersion }: ReviewWorkspaceProps) {
  const [observe, width] = useElementWidth<HTMLDivElement>();
  const [wanted, setWanted] = useState(readWidths);
  const sizes = fitWidths(width, wanted);
  const [statusTarget, setStatusTarget] = useState<HTMLDivElement | null>(null);
  const [tab, setTab] = useState<Tab>("conversation");
  // Narrow, the workspace starts on the paper, its pins in view; the pane
  // opens from its launcher, a pin, Comment or Readiness (IR-875).
  const [open, setOpen] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [routed, setRouted] = useState("");
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
    if (!folded) setTab((t) => (t === "details" ? "conversation" : t));
  }, [folded]);

  const tw = useThreadsWorkspace({
    record, can, onChanged,
    showThreads: () => { setTab("threads"); if (drawer) setOpen(true); },
    showPaper: () => { if (drawer && open) closeDrawer(); },
    announce: setRouted,
  });
  const finishing = can.has("finish_review");
  // The server offers `open_review` for every seat still being worked on, an
  // opened one included, so only a seat not yet opened asks for it here: an
  // opened one finishes instead (IR-875).
  const unopened = can.has("open_review") && seatToOpen(record) !== null;
  // Changes needs two Versions to compare (ADR-058 §3, IR-873).
  const versions = record.versions ?? [];
  const comparable = versions.length >= 2;
  const tabs: Tab[] = [
    "conversation", "threads", ...(comparable ? ["changes" as const] : []), ...(folded ? ["details" as const] : []),
  ];
  const latest = versions[versions.length - 1]?.number ?? null;
  // A reviewer looking again at a new Version reads the response it was
  // submitted with first (ADR-032 §7, IR-876): once per letter, so a later
  // tab choice is the reviewer's own.
  const letterVersion = tw.panel.letter?.version ?? null;
  const reviewing = finishing || unopened;
  const ledWithLetter = useRef<number | null>(null);
  useEffect(() => {
    if (!reviewing || letterVersion === null || letterVersion !== latest || ledWithLetter.current === letterVersion) return;
    ledWithLetter.current = letterVersion;
    setTab("threads");
  }, [reviewing, letterVersion, latest]);
  // Fetched only once opened, then kept, so its choices survive a tab switch.
  const [changesOpened, setChangesOpened] = useState(false);
  useEffect(() => {
    if (tab === "changes") setChangesOpened(true);
    if (tab === "changes" && !comparable) setTab("conversation");
  }, [tab, comparable]);
  const showChange = ({ version, page, regions }: ShowPlace) => {
    onShowVersion?.(version === latest ? null : version);
    tw.showPlace(page, regions);
  };

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
    // Documents moved into a drawer (IR-879): a document request's link opens it.
    else if (action.kind === "open_documents") onDocuments(true);
    else if (action.kind === "show_party") goTo(action.target ?? "reviewers");
    // An open thread's item shows that party's open threads (IR-875).
    else if (action.kind === "show_threads") tw.showParty(action.target);
    // The footer's own Withdraw asks first, as it always has.
    else if (action.kind === "withdraw_revision") {
      Array.from(footer.current?.querySelectorAll("button") ?? [])
        .find((b) => b.textContent?.includes("Withdraw revision request"))?.focus();
    }
  };
  // Request review offers exactly the routing flags' targets, never a table
  // of our own, so a change to the party graph needs no change here.
  const targets = record.routing.targets;
  const mayRequest = can.has("route") && targets.length > 0 && ROUTE !== undefined;
  const renderDetails = (tracker: RecordTracker) => (
    <ReviewDetails record={record} tracker={tracker} ids={ids}
      requestReview={mayRequest ? { targets: targets.map((t) => t.label), onOpen: () => { setRouted(""); setRequesting(true); } } : undefined}
      addColleague={<ReviewActionBar record={record} can={can} actions={ADD_COLLEAGUE} label="Reviewer actions"
        primary={false} onChanged={onChanged} className="pt-1" />}
      onAllDocuments={() => onDocuments(true)} />
  );
  const RouteDialog = ROUTE?.Dialog;
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
        {reader && <div className="review-paper" {...(drawer && open ? { inert: "" } : {})}>{tw.wrapReader(reader)}</div>}
        <section ref={pane} id={`${ids}-mid`} aria-label="Review pane" tabIndex={-1}
          role={drawer && open ? "dialog" : "region"} aria-modal={drawer && open || undefined}
          aria-hidden={drawer && !open || undefined} {...(drawer && !open ? { inert: "" } : {})}
          className={cn("review-pane", open && "review-pane-open")}>
          {!drawer && reader && edge("mid", "Resize the review pane")}
          <header className="review-pane-head">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wider text-stone-600">Review workspace / current record</p>
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
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
              e.preventDefault();
              const at = tabs.indexOf(tab);
              const next = e.key === "Home" ? tabs[0] : e.key === "End" ? tabs[tabs.length - 1]
                : tabs[(at + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
              setTab(next);
              document.getElementById(`${ids}-tab-${next}`)?.focus();
            }}>
              {tabs.map((name) => (
                <button key={name} type="button" role="tab" id={`${ids}-tab-${name}`}
                  aria-selected={tab === name} aria-controls={`${ids}-${name}`} tabIndex={tab === name ? 0 : -1}
                  onClick={() => setTab(name)} className={cn("review-tab", FOCUS_RING)}>
                  {TAB_NAMES[name]}
                  {name === "threads" && tw.count && <>{" "}<span className="ml-1 text-2xs font-normal text-stone-600">{tw.count}</span></>}
                </button>
              ))}
            </div>
          </header>
          <div
            role="region"
            aria-label="Review pane content"
            tabIndex={0}
            className={cn("review-pane-body", FOCUS_RING)}
          >
            <div role="tabpanel" id={`${ids}-conversation`} aria-labelledby={`${ids}-tab-conversation`} hidden={tab !== "conversation"} className="p-4">
              <ReviewTimeline key={`${record.id}-${timelineVersion}`} recordId={record.id} canComment={can.has("comment_review")} statusTarget={statusTarget}
                onCommented={tw.threads.reload}
                renderStatus={renderDetails}
                beforeComment={record.readiness ? <ReadinessPanel id={`${ids}-readiness`} readiness={record.readiness} onAction={onReadinessAction} /> : null} />
            </div>
            <div role="tabpanel" id={`${ids}-threads`} aria-labelledby={`${ids}-tab-threads`} hidden={tab !== "threads"} className="p-4">
              <ReviewThreads {...tw.panel} />
            </div>
            {comparable && (
              <div role="tabpanel" id={`${ids}-changes`} aria-labelledby={`${ids}-tab-changes`} hidden={tab !== "changes"} className="p-4">
                {changesOpened && (
                  <ChangesTab recordId={record.id} versions={versions} threads={tw.threads.sent}
                    onShowInPaper={showChange} onOpenThread={tw.openThread} />
                )}
              </div>
            )}
            {folded && <div role="tabpanel" id={`${ids}-details`} aria-labelledby={`${ids}-tab-details`} hidden={tab !== "details"} className="p-4">{details}</div>}
          </div>
          <footer ref={footer} className="review-pane-foot" aria-label="Your review">
            <p className="text-small font-semibold text-stone-900"><i className="fas fa-clipboard-check mr-2" aria-hidden />Your review: {ownSeat?.verdict_label ?? ownSeat?.state_label ?? "No verdict recorded"}</p>
            {finishing && (
              <p className="text-2xs text-stone-600">
                {tw.threads.drafts.length
                  ? `${tw.threads.drafts.length} draft comment${tw.threads.drafts.length === 1 ? "" : "s"}, not sent`
                  : "No draft comments"}
              </p>
            )}
            {record.review_claim
              ? <button type="button" disabled={claiming} onClick={() => void claim()} className={cn(PILL_PRIMARY, FOCUS_RING)}>{claiming ? "Claiming…" : record.review_claim.label}</button>
              : unopened && <button type="button" onClick={() => void onOpenReview?.()} className={cn(PILL_PRIMARY, FOCUS_RING)}>Open review</button>}
            {finishing && !record.review_claim && !unopened && (
              <button type="button" onClick={tw.finish} className={cn(PILL_PRIMARY, FOCUS_RING)}>Finish review…</button>
            )}
            {claimError && <p role="alert" className="text-small text-brand">{claimError}</p>}
            <ReviewActionBar record={record} can={can} actions={finishing ? FINISH_FOOTER_ACTIONS : FOOTER_ACTIONS} onChanged={onChanged}
              primary={!finishing && !unopened && !record.review_claim} />
          </footer>
        </section>
        {!folded && <aside id={`${ids}-side`} aria-label="Review details" className="review-details">
          {edge("side", "Resize the details sidebar")}
          <p className="text-2xs font-semibold uppercase tracking-wider text-brand">Record context</p>
          <h2 className="font-display text-xl font-semibold text-stone-900 mb-4">People &amp; details</h2>
          {details}
        </aside>}
        <p role="status" aria-live="polite" className="sr-only">{routed}</p>
        {tw.dialogs}
        {/* Into <body>, as the action bar mounts its dialogs, so no sticky
            column's stacking context draws it under the page. */}
        {requesting && RouteDialog && createPortal(
          <RouteDialog record={record} onClose={() => setRequesting(false)}
            onDone={(outcome) => { setRequesting(false); setRouted(outcome); onChanged(); }} />,
          document.body,
        )}
        {drawer && <div className="review-paper-foot"><button ref={launcher} type="button" className={cn("review-control text-brand font-semibold", FOCUS_RING)} onClick={() => setOpen(true)}>Open review pane</button></div>}
      </div>
    </div>
  );
}
