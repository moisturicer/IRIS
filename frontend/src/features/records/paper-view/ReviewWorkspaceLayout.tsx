import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { seatsApi } from "@/api/reviews";
import { errorDetail } from "@/lib/errorDetail";
import { useElementWidth } from "@/hooks/useElementWidth";
import { seatToOpen } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordTracker } from "@/types/records";

import { ReviewActionBar } from "./ReviewActionBar";
import { detailsTarget, ReviewDetails } from "./ReviewDetails";
import { ReviewTimeline } from "./ReviewTimeline";
import { REVIEW_ACTIONS, VERDICT_CAPABILITIES, type DialogReviewAction } from "./reviewActions";
import type { ShowPlace } from "./changes/ChangeItem";
import { ChangesTab } from "./changes/ChangesTab";
import { TabBesideMenu } from "./TabBesideMenu";
import { ReviewThreads } from "./threads/ReviewThreads";
import { useThreadsWorkspace } from "./threads/useThreadsWorkspace";
import { DRAWER_BELOW_PX, fitWidths, maxWidth, minWidth, SIDE_TAB_MIN_PX, type Widths } from "./reviewGeometry";
import { GuidedTour } from "./tour/GuidedTour";
import { markTourSeen, tourSeen } from "./tour/tourStorage";
import { reviewTourSteps, tourTargets, type TourTab } from "./tour/tourSteps";
import type { ReviewWorkspaceProps } from "./ReviewWorkspace";
import { YourPartFooter } from "./YourPartFooter";
import { readinessFacts, yourPartSummary } from "./yourPart";
import "./reviewWorkspace.css";

const WIDTHS_KEY = "iris-review-cols";
const SIDE_TAB_KEY = "iris-review-side-tab";

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
type Tab = TourTab;

const TAB_NAMES: Record<Tab, string> = {
  conversation: "Conversation", threads: "Threads", changes: "Changes", details: "Details",
};
function readWidths(): Widths {
  try {
    const value = JSON.parse(localStorage.getItem(WIDTHS_KEY) ?? "null");
    const valid = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
    return { mid: valid(value?.mid) ? value.mid : null, side: valid(value?.side) ? value.side : null };
  } catch {
    return { mid: null, side: null };
  }
}

/** The tab the reviewer last opened on the right, if it is still one this workspace has. */
function readSideTab(): Tab | null {
  try {
    const value = localStorage.getItem(SIDE_TAB_KEY);
    return value !== null && value in TAB_NAMES ? (value as Tab) : null;
  } catch {
    return null;
  }
}

export function ReviewWorkspaceLayout({ record, can, reader, timelineVersion, onChanged, onDocuments, onOpenReview, onShowVersion }: ReviewWorkspaceProps) {
  const [observe, width] = useElementWidth<HTMLDivElement>();
  const [wanted, setWanted] = useState(readWidths);
  const [statusTarget, setStatusTarget] = useState<HTMLDivElement | null>(null);
  const [tab, setTab] = useState<Tab>("conversation");
  const [sideChoice, setSideChoice] = useState(readSideTab);
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
  const tourButton = useRef<HTMLButtonElement>(null);
  const footTour = useRef<HTMLButtonElement>(null);
  const target = tourTargets(ids);
  // The guided tour (IR-997): offered once per browser, startable any time. It
  // holds only its own opener; it reads and changes nothing about the review.
  const [offered, setOffered] = useState(() => !tourSeen());
  const [tour, setTour] = useState<{ opener: HTMLElement | null } | null>(null);
  // Narrow, with the pane closed, the pane's own button is out of reach.
  const tourOpener = () => (drawer && !open ? footTour.current : tourButton.current);
  const startTour = (opener: HTMLElement | null) => {
    markTourSeen();
    setOffered(false);
    setTour({ opener });
  };
  const dismissOffer = () => {
    markTourSeen();
    setOffered(false);
  };
  const closeTour = useCallback(() => {
    setTour(null);
    // Focus goes back to the opener; if the pane closed under it, to a button in reach.
    requestAnimationFrame(() => {
      if (document.activeElement && document.activeElement !== document.body) return;
      [tourButton.current, footTour.current, launcher.current]
        .find((el) => el && !el.closest('[inert],[aria-hidden="true"]'))?.focus();
    });
  }, []);
  const drawer = width > 0 && width < DRAWER_BELOW_PX && Boolean(reader);
  const roomy = width >= SIDE_TAB_MIN_PX;
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

  const tw = useThreadsWorkspace({
    record, can, onChanged,
    showThreads: () => { reveal("threads"); if (drawer) setOpen(true); },
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
  // Details is a tab at every width: the third column that repeated it is gone
  // (IR-1094). One tab may sit in a right column on a workspace wide enough;
  // narrower, it returns to the row, and the choice is kept for next time.
  const allTabs: Tab[] = ["conversation", "threads", ...(comparable ? ["changes" as const] : []), "details"];
  const sideTab = roomy && sideChoice !== null && allTabs.includes(sideChoice) ? sideChoice : null;
  const tabs = allTabs.filter((t) => t !== sideTab);
  const shown: Tab = tabs.includes(tab) ? tab : tabs[0]!;
  const sizes = fitWidths(width, wanted, sideTab !== null);
  // Where focus goes once the control that was used is gone: the right column's
  // close button when a tab arrives, the tab's own button when it returns.
  const focusLater = (id: string) => requestAnimationFrame(() => document.getElementById(id)?.focus());
  const chooseSide = (next: Tab | null) => {
    // The tab that moves out of the row must not stay "selected" behind it, or
    // closing the column would silently bring it back as the shown tab.
    if (next !== null && next === shown) setTab(allTabs.find((t) => t !== next)!);
    if (next !== null) focusLater(`${ids}-side-close`);
    else if (sideTab) focusLater(`${ids}-tab-${sideTab}`);
    setSideChoice(next);
    try {
      if (next === null) localStorage.removeItem(SIDE_TAB_KEY);
      else localStorage.setItem(SIDE_TAB_KEY, next);
    } catch { /* The choice still holds for this visit. */ }
  };
  // Shows a tab wherever it is: its own button, or already in the right column.
  const reveal = (name: Tab) => { if (name !== sideTab) setTab(name); };
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
  // Fetched only once opened, then kept, so its choices survive a tab switch
  // (moving it to the right column mounts it again, and it starts afresh).
  const [changesOpened, setChangesOpened] = useState(false);
  const changesVisible = shown === "changes" || sideTab === "changes";
  useEffect(() => {
    if (changesVisible) setChangesOpened(true);
    if (tab === "changes" && !comparable) setTab("conversation");
  }, [changesVisible, tab, comparable]);
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
      aria-controls={`${ids}-${key}`} aria-valuenow={sizes[key]} aria-valuemin={minWidth(key)}
      aria-valuemax={maxWidth(key, width, sizes, sideTab !== null)}
      className="review-resize-edge"
      onPointerDown={(e) => startDrag(key, e)}
      onPointerMove={(e) => {
        const from = drag.current;
        if (!from || from.key !== key) return;
        update(fitWidths(width, { mid: from.mid, side: from.side, [key]: from[key] + from.x - e.clientX }, sideTab !== null));
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }}
      onDoubleClick={() => update({ ...wanted, [key]: null })}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        update(fitWidths(width, { ...sizes, [key]: sizes[key] + (e.key === "ArrowLeft" ? 24 : -24) }, sideTab !== null));
      }}
    />
  );

  const details = <div ref={setStatusTarget} />;
  // Shown in the pane's header, and beside the launcher while a narrow window
  // keeps the pane closed, so a first visit sees it either way.
  const offer = (
    <div role="group" aria-label="Guided tour" className="w-full rounded-lg border border-stone-300 bg-white p-3">
      <p className="text-small text-stone-800">New to the Review workspace? Take a short tour of its main parts.</p>
      <div className="mt-2 flex gap-2">
        <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} onClick={() => startTour(tourOpener())}>Start tour</button>
        <button type="button" className={cn("review-control font-semibold text-stone-700", FOCUS_RING)}
          onClick={dismissOffer}>Not now</button>
      </div>
    </div>
  );
  const footer = useRef<HTMLElement>(null);
  // A Readiness link reuses a control the page already has; a target in
  // Details opens that tab first (unless it is already on the right), then
  // takes focus.
  const goTo = (to: string) => {
    reveal("details");
    if (drawer) setOpen(true);
    requestAnimationFrame(() => {
      const el = document.getElementById(detailsTarget(ids, to));
      el?.scrollIntoView?.({ block: "start" });
      el?.focus({ preventScroll: true });
    });
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
      readiness={record.readiness} onReadinessAction={onReadinessAction}
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
  // What each tab holds. A tab is mounted wherever it is shown -- its place in
  // the pane, or the right column -- so choosing it there moves it (IR-1094).
  const body: Record<Tab, ReactNode> = {
    conversation: (
      <ReviewTimeline key={`${record.id}-${timelineVersion}`} recordId={record.id} canComment={can.has("comment_review")} statusTarget={statusTarget}
        onCommented={tw.threads.reload} renderStatus={renderDetails} />
    ),
    threads: <ReviewThreads {...tw.panel} />,
    changes: comparable && changesOpened ? (
      <ChangesTab recordId={record.id} versions={versions} threads={tw.threads.sent}
        onShowInPaper={showChange} onOpenThread={tw.openThread} />
    ) : null,
    details,
  };
  const panel = (name: Tab) => name === sideTab || (name === "changes" && !comparable) ? null : (
    <div key={name} role="tabpanel" id={`${ids}-${name}`} aria-labelledby={`${ids}-tab-${name}`} hidden={shown !== name} className="p-4">
      {body[name]}
    </div>
  );

  // Your part: the server's words, and the controls the server grants.
  const draftCount = finishing ? tw.threads.drafts.length : 0;
  const part = yourPartSummary({ readiness: record.readiness, seat: ownSeat, draftCount });
  const hasFacts = readinessFacts(record.readiness).length > 0;

  return (
    <div ref={observe} className="review-workspace-container">
      <div className={cn("review-workspace", !reader && "review-without-paper", sideTab && "review-has-side")}
        style={{ "--mid-w": `${sizes.mid}px`, "--side-w": `${sizes.side}px` } as CSSProperties}>
        {reader && <div id={target.paper} className={cn("review-paper", drawer && !open && offered && "review-paper-offered")} {...(drawer && open ? { inert: "" } : {})}>{tw.wrapReader(reader)}</div>}
        <section ref={pane} id={`${ids}-mid`} aria-label="Review pane" tabIndex={-1}
          role={drawer && open ? "dialog" : "region"} aria-modal={drawer && open || undefined}
          aria-hidden={drawer && !open || undefined} {...(drawer && !open ? { inert: "" } : {})}
          className={cn("review-pane", open && "review-pane-open")}>
          {!drawer && reader && edge("mid", "Resize the review pane")}
          <header className="review-pane-head">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                {record.current_holders.length > 0 && (
                  <p className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 bg-surface px-2 py-0.5 text-2xs font-semibold text-brand">
                    <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
                    With {record.current_holders.map((h) => h.label).join(", ")}
                  </p>
                )}
                <h2 className="font-display text-xl font-semibold text-stone-900 mt-1">Review</h2>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button ref={tourButton} type="button" className={cn("review-control whitespace-nowrap text-brand", FOCUS_RING)}
                  onClick={(e) => startTour(e.currentTarget)}>Take a tour</button>
                {drawer && <button type="button" className={cn("review-control whitespace-nowrap text-brand", FOCUS_RING)}
                  onClick={closeDrawer}>Back to paper</button>}
              </div>
            </div>
            {offered && <div className="mt-3">{offer}</div>}
            <div className="flex items-center justify-between gap-2">
              <div role="tablist" id={target.tabs} aria-label="Review pane sections" onKeyDown={(e) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                e.preventDefault();
                const at = tabs.indexOf(shown);
                const next = e.key === "Home" ? tabs[0]! : e.key === "End" ? tabs[tabs.length - 1]!
                  : tabs[(at + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]!;
                setTab(next);
                document.getElementById(`${ids}-tab-${next}`)?.focus();
              }}>
                {tabs.map((name) => (
                  <button key={name} type="button" role="tab" id={`${ids}-tab-${name}`}
                    aria-selected={shown === name} aria-controls={`${ids}-${name}`} tabIndex={shown === name ? 0 : -1}
                    onClick={() => setTab(name)} className={cn("review-tab", FOCUS_RING)}>
                    {TAB_NAMES[name]}
                    {name === "threads" && tw.count && <>{" "}<span className="ml-1 text-2xs font-normal text-stone-600">{tw.count}</span></>}
                  </button>
                ))}
              </div>
              {roomy && <TabBesideMenu choices={tabs.map((t) => ({ id: t, label: TAB_NAMES[t] }))}
                onChoose={chooseSide} />}
            </div>
          </header>
          <div
            role="region"
            aria-label="Review pane content"
            tabIndex={0}
            className={cn("review-pane-body", FOCUS_RING)}
          >
            {allTabs.map(panel)}
          </div>
          <YourPartFooter footerRef={footer} id={target.foot} part={part} hasFacts={hasFacts} onShowFacts={() => goTo("readiness")}>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {record.review_claim
                ? <button type="button" disabled={claiming} onClick={() => void claim()} className={cn(PILL_PRIMARY, FOCUS_RING)}>{claiming ? "Claiming…" : record.review_claim.label}</button>
                : unopened && <button type="button" onClick={() => void onOpenReview?.()} className={cn(PILL_PRIMARY, FOCUS_RING)}>Open review</button>}
              {finishing && !record.review_claim && !unopened && (
                <button type="button" onClick={tw.finish} className={cn(PILL_PRIMARY, FOCUS_RING)}>Finish review…</button>
              )}
              <ReviewActionBar record={record} can={can} actions={finishing ? FINISH_FOOTER_ACTIONS : FOOTER_ACTIONS} onChanged={onChanged}
                primary={!finishing && !unopened && !record.review_claim} className="contents" />
            </div>
            {claimError && <p role="alert" className="mt-2 text-small text-brand">{claimError}</p>}
          </YourPartFooter>
        </section>
        {sideTab && (
          <aside aria-label={`${TAB_NAMES[sideTab]} on the right`} className="review-side">
            {edge("side", "Resize the right column")}
            <header className="review-side-head">
              <h2 className="font-display text-xl font-semibold text-stone-900">{TAB_NAMES[sideTab]}</h2>
              <button type="button" id={`${ids}-side-close`} aria-label={`Close ${TAB_NAMES[sideTab]} on the right`} title="Close"
                onClick={() => chooseSide(null)} className={cn("review-control text-stone-600 hover:text-brand", FOCUS_RING)}>
                <i className="fas fa-xmark" aria-hidden />
              </button>
            </header>
            <div className="review-side-body">{body[sideTab]}</div>
          </aside>
        )}
        <p role="status" aria-live="polite" className="sr-only">{routed}</p>
        {tw.dialogs}
        {/* Into <body>, as the action bar mounts its dialogs, so no sticky
            column's stacking context draws it under the page. */}
        {requesting && RouteDialog && createPortal(
          <RouteDialog record={record} onClose={() => setRequesting(false)}
            onDone={(outcome) => { setRequesting(false); setRouted(outcome); onChanged(); }} />,
          document.body,
        )}
        {drawer && (
          <div className="review-paper-foot">
            {!open && offered && offer}
            {/* The pane's own Take a tour is out of reach while it is closed. */}
            {!open && <button ref={footTour} type="button" className={cn("review-control text-brand", FOCUS_RING)} onClick={(e) => startTour(e.currentTarget)}>Take a tour</button>}
            <button ref={launcher} id={target.launcher} type="button" className={cn("review-control text-brand font-semibold", FOCUS_RING)} onClick={() => setOpen(true)}>Open review pane</button>
          </div>
        )}
        {tour && (
          <GuidedTour opener={tour.opener} onClose={closeTour}
            steps={reviewTourSteps({ ids, hasPaper: Boolean(reader), drawer, paneOpen: open, tabs: allTabs, beside: roomy })} />
        )}
      </div>
    </div>
  );
}
