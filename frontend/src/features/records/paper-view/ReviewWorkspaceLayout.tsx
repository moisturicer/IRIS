import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { seatsApi } from "@/api/reviews";
import { errorDetail } from "@/lib/errorDetail";
import { useElementWidth } from "@/hooks/useElementWidth";
import { seatToOpen } from "@/features/records/capabilities";
import type { Capability } from "@/features/records/capabilities";
import { cn, formatDate } from "@/lib/utils";
import type { RecordDetail, RecordTracker, RecordVersion, ThreadDocument } from "@/types/records";

import { ReadinessPanel } from "./ReadinessPanel";
import { ReviewActionBar } from "./ReviewActionBar";
import { detailsTarget, ReviewDetails } from "./ReviewDetails";
import { ReviewTimeline } from "./ReviewTimeline";
import { REVIEWER_FOOTER_ACTIONS, REVIEW_ACTIONS, addReviewerSeat, type DialogReviewAction } from "./reviewActions";
import { AddColleagueLink } from "./AddColleagueLink";
import { ReviewFooterActions } from "./ReviewFooterActions";
import type { ShowPlace } from "./changes/ChangeItem";
import { ChangesTab } from "./changes/ChangesTab";
import { TabBesideMenu } from "./TabBesideMenu";
import { ReviewThreads } from "./threads/ReviewThreads";
import { isDiscussion } from "./threads/threadModel";
import { useThreadsWorkspace } from "./threads/useThreadsWorkspace";
import { ReviewPaneContext, type ReviewPane } from "./reviewPane";
import { DRAWER_BELOW_PX, fitWidths, maxWidth, minWidth, SIDE_TAB_MIN_PX, type Widths } from "./reviewGeometry";
import { GuidedTour } from "@/components/tour/GuidedTour";
import { markTourSeen, tourSeen } from "./tour/tourStorage";
import { reviewTourSteps, tourTargets, type TourTab } from "./tour/tourSteps";
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
const ROUTE = REVIEW_ACTIONS.find((a): a is DialogReviewAction => a.capability === "route" && a.kind === "dialog");
/** The author's tabs add Readiness, first (IR-1206); reviewers keep the tour's. */
type Tab = TourTab | "readiness";

const TAB_NAMES: Record<Tab, string> = {
  readiness: "Readiness", documents: "Documents", conversation: "Conversation", threads: "Threads", changes: "Changes",
  details: "Details",
};
// Documents is the reviewers' first tab and the author's second (IR-1203).
const REVIEWER_TABS: Tab[] = ["documents", "conversation", "threads", "changes", "details"];
const AUTHOR_TABS: Tab[] = ["readiness", "documents", "conversation", "threads", "details"];
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

/**
 * The review workspace: one frame for authors and reviewers (IR-1206), with
 * documents as one of its tabs (IR-1203). The page imports it directly; the
 * `ReviewWorkspace` wrapper that drew the documents drawer over it is gone.
 */
export interface ReviewWorkspaceProps {
  record: RecordDetail;
  /** What the capabilities adapter grants this viewer. */
  can: ReadonlySet<Capability>;
  /** The paper, as the Paper tab's reader; null when there is none to read. */
  reader: ReactNode;
  /** Bumped when the review changed, so the timeline re-reads the tracker. */
  timelineVersion: number;
  /** Something changed: re-read the record and the timeline. */
  onChanged: () => void;
  /**
   * The Documents tab's body (IR-1203): every document filed with the record.
   * It replaced the "All documents" drawer (IR-879). There is no Ask IRIS in
   * Review (IR-372).
   */
  documents: ReactNode;
  /**
   * The page was asked to show the documents -- `?documents=open`, or an old
   * `?section=files` link -- so the workspace opens its Documents tab, and
   * says so through `onDocumentsShown` so the page can drop the request.
   */
  showDocuments?: boolean;
  onDocumentsShown?: () => void;
  /**
   * The viewer owns the paper (IR-1206): the same workspace as reviewers,
   * with the author's tabs -- Readiness first, then Documents, Conversation,
   * Threads and Details -- and no tour and no Changes.
   */
  authorView?: boolean;
  /**
   * What left the owners' editorial header, shown at the top of their Details
   * (IR-1206): Edit details, the Proposal lineage and Continue as, each only
   * where the server offers it. Null when there is none.
   */
  authorDetails?: ReactNode;
  onOpenReview?: () => Promise<void>;
  /**
   * Show Version `n` in the reader, or the current paper for null (IR-873):
   * the Changes tab's *Show in paper* opens the Version a change is in.
   */
  onShowVersion?: (n: number | null) => void;
  /** Put the manuscript back in the reader: a thread or a change is shown there (IR-1203). */
  onShowManuscript?: () => void;
  /** Show the document a thread is about in the reader (IR-1204). */
  onShowDocument?: (document: ThreadDocument) => void;
}

/** True from the first render `shown` is true, and from then on. */
function useShownOnce(shown: boolean): boolean {
  const [once, setOnce] = useState(shown);
  useEffect(() => {
    if (shown) setOnce(true);
  }, [shown]);
  return once || shown;
}

/** Out of reach -- unclickable, unfocusable and unread -- while `hidden` (IR-1336). */
function hiddenWhile(hidden: boolean) {
  return hidden ? { inert: "", "aria-hidden": true } : {};
}

/**
 * Who sent the Version under review, and when, as a pull request says who
 * opened it (IR-1131): "Ana Cruz sent v2 · Nov 3, 2026". The name and date
 * are the server's; with no name, the Version alone.
 */
function SentBy({ version }: { version: RecordVersion }) {
  const verb = version.cause === "submission" ? "submitted" : "sent";
  return (
    <>
      {version.created_by_name ? <><b>{version.created_by_name}</b> {verb} v{version.number}</> : <>v{version.number} {verb}</>}
      {" · "}
      <time dateTime={version.created_at}>{formatDate(version.created_at)}</time>
    </>
  );
}

export function ReviewWorkspaceLayout({
  record, can, reader, timelineVersion, onChanged, documents, showDocuments = false, onDocumentsShown, onOpenReview,
  onShowVersion, authorView = false, authorDetails, onShowManuscript, onShowDocument,
}: ReviewWorkspaceProps) {
  const [observe, width] = useElementWidth<HTMLDivElement>();
  const [wanted, setWanted] = useState(readWidths);
  const [statusTarget, setStatusTarget] = useState<HTMLDivElement | null>(null);
  // Each opens on their first tab: the author on what waits on them (IR-1206),
  // a reviewer on the documents (IR-1203, decided 2026-11-17).
  const home: Tab = authorView ? "readiness" : "documents";
  const [tab, setTab] = useState<Tab>(home);
  const [sideChoice, setSideChoice] = useState(readSideTab);
  // Narrow, the workspace starts on the paper, its pins in view; the pane
  // opens from its launcher, a pin, Comment or Readiness (IR-875).
  const [open, setOpen] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [routed, setRouted] = useState("");
  // The Conversation tab's count (IR-1131): comments and replies sent, from the timeline's own read.
  const [commentCount, setCommentCount] = useState(0);
  const pane = useRef<HTMLElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const ids = useId();
  const tourButton = useRef<HTMLButtonElement>(null);
  const footTour = useRef<HTMLButtonElement>(null);
  const target = tourTargets(ids);
  // The guided tour (IR-997): offered once per browser, startable any time. It
  // holds only its own opener; it reads and changes nothing about the review.
  // The tour walks a reviewer's tabs, so it is not offered to the author (IR-1206).
  const [offered, setOffered] = useState(() => !authorView && !tourSeen());
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

  // The server offers `open_review` for every seat still being worked on, an
  // opened one included, so only a seat not yet opened asks for it here: an
  // opened one finishes instead (IR-875).
  const unopened = can.has("open_review") && seatToOpen(record) !== null;
  // Not claimed, or not started: the reader's Comment waits for both (IR-1341).
  const notStarted = !authorView && (unopened || Boolean(record.review_claim));
  const tw = useThreadsWorkspace({
    record, can, onChanged, notStarted,
    showThreads: () => { reveal("threads"); if (drawer) setOpen(true); },
    // Threads and Changes point into the manuscript, so a document steps aside for it (IR-1203).
    showPaper: () => { onShowManuscript?.(); if (drawer && open) closeDrawer(); },
    showDocument: onShowDocument && ((document) => { onShowDocument(document); if (drawer && open) closeDrawer(); }),
    announce: setRouted,
  });
  const finishing = can.has("finish_review");
  // A review not yet started is covered until Start review records it (IR-1336).
  // Claim comes first: an office review nobody holds is claimed, not started.
  const covered = unopened && !authorView && !record.review_claim;
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const startReview = async () => {
    setStarting(true);
    setStartError(null);
    try {
      await onOpenReview?.();
    } catch {
      setStartError("Your review could not be started. Try again.");
    } finally {
      setStarting(false);
    }
  };
  // Changes needs two Versions to compare (ADR-058 §3, IR-873).
  const versions = record.versions ?? [];
  const comparable = versions.length >= 2;
  // Details is a tab at every width: the third column that repeated it is gone
  // (IR-1094). One tab may sit in a right column on a workspace wide enough;
  // narrower, it returns to the row, and the choice is kept for next time.
  // Changes is always a tab, as in the prototype (IR-1139): on the first
  // version it says there is nothing to compare yet, instead of vanishing.
  const allTabs = authorView ? AUTHOR_TABS : REVIEWER_TABS;
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
    // It falls back to the tab the pane opens on, else the first other one.
    if (next !== null && next === shown) setTab(home !== next ? home : allTabs.find((t) => t !== next)!);
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
  const latestVersion = versions[versions.length - 1] ?? null;
  const latest = latestVersion?.number ?? null;
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
  // Changes is fetched only once opened, then kept, so its choices survive a
  // tab switch (moving it to the right column mounts it again, and it starts
  // afresh). Documents loads itself too, so it mounts once shown, as the drawer
  // it replaced did (IR-1203), and stays so an upload under way survives a switch.
  const changesOpened = useShownOnce(shown === "changes" || sideTab === "changes");
  const documentsOpened = useShownOnce(shown === "documents" || sideTab === "documents");
  const showChange = (place: ShowPlace) => {
    onShowVersion?.(place.version === latest ? null : place.version);
    tw.showPlace(place);
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
  // One quiet row (IR-1191 misc): what the tour is on the left, Not now and an
  // outlined Start tour on the right, wrapping under the text when narrow. It
  // is an offer, not the page's action, so nothing in it is filled.
  const offer = (
    <div role="group" aria-label="Guided tour"
      className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-control border border-stone-300 bg-white px-4 py-3">
      <p className="min-w-0 flex-1 basis-56 text-small text-stone-800">
        New to the review workspace? A guided tour shows what each part is for and how a review goes, step by step.
      </p>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <button type="button" className={cn("review-control px-3 font-semibold text-stone-700 hover:text-stone-900", FOCUS_RING)}
          onClick={dismissOffer}>Not now</button>
        <button type="button" onClick={() => startTour(tourOpener())}
          className={cn(PILL_SECONDARY, "bg-white px-4 text-stone-900 ring-stone-400 reading-split:min-h-9", FOCUS_RING)}>
          Start tour
        </button>
      </div>
    </div>
  );
  const footer = useRef<HTMLElement>(null);
  // A Readiness link reuses a control the page already has; a target in
  // Details opens that tab first (unless it is already on the right), then
  // takes focus.
  const goTo = (to: string) => {
    // The author's Readiness is a tab of its own, not a section of Details.
    if (authorView && to === "readiness") {
      reveal("readiness");
      if (drawer) setOpen(true);
      return;
    }
    reveal("details");
    if (drawer) setOpen(true);
    requestAnimationFrame(() => {
      const el = document.getElementById(detailsTarget(ids, to));
      el?.scrollIntoView?.({ block: "start" });
      el?.focus({ preventScroll: true });
    });
  };
  // Documents is a tab (IR-1203): a document request's link, and the page
  // asking for the documents, open it, and the pane with it when narrow.
  const showDocumentsTab = () => {
    reveal("documents");
    if (drawer) setOpen(true);
  };
  // The page's request is taken at once; opening a narrow window's pane waits
  // for the first measure, which says whether there is a pane to open.
  const [paneForDocuments, setPaneForDocuments] = useState(false);
  const measured = width > 0;
  useEffect(() => {
    if (!showDocuments) return;
    reveal("documents");
    setPaneForDocuments(true);
    onDocumentsShown?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per request, not per render
  }, [showDocuments]);
  useEffect(() => {
    if (!paneForDocuments || !measured) return;
    setPaneForDocuments(false);
    if (drawer) setOpen(true);
  }, [paneForDocuments, measured, drawer]);
  const onReadinessAction = (action: { kind: string; target: string | null }) => {
    if (action.kind === "open_review") void onOpenReview?.();
    else if (action.kind === "claim") void claim();
    else if (action.kind === "open_documents") showDocumentsTab();
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
  // The office a colleague joins: the viewer's open office seat (IR-1340).
  const colleagueSeat = addReviewerSeat(record);
  const renderDetails = (tracker: RecordTracker) => (
    <div className="space-y-5">
    {authorView && authorDetails}
    <ReviewDetails record={record} tracker={tracker} ids={ids}
      readiness={authorView ? null : record.readiness} onReadinessAction={authorView ? undefined : onReadinessAction}
      requestReview={mayRequest ? { targets: targets.map((t) => t.label), onOpen: () => { setRouted(""); setRequesting(true); } } : undefined}
      addColleague={colleagueSeat && can.has("add_reviewer") ? {
        party: colleagueSeat.party,
        control: (office) => <AddColleagueLink record={record} office={office} onChanged={onChanged} />,
      } : undefined} />
    </div>
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
  // The first Version opens the timeline as its own box: who submitted and when (IR-1212).
  const first = versions[0];
  const submission = first ? { author: first.created_by_name, at: first.created_at } : undefined;
  const body: Record<Tab, ReactNode> = {
    // The author's first tab (IR-1206): where the record stands, then what
    // waits on them. Their documents are the next tab (IR-1203).
    readiness: authorView ? (
      <div className="space-y-4">
        <StatusBadge state={record.workflow_state} label={record.workflow_state_label} compact />
        {record.readiness
          ? <ReadinessPanel readiness={record.readiness} onAction={onReadinessAction} />
          : <p className="text-small text-stone-600">Nothing is waiting on you.</p>}
      </div>
    ) : null,
    conversation: (
      <ReviewTimeline key={`${record.id}-${timelineVersion}`} recordId={record.id} canComment={can.has("comment_review")} statusTarget={statusTarget}
        onCommented={tw.threads.reload} onOpenThreads={tw.openThreads} renderStatus={renderDetails} submission={submission} statusBox
        onLoaded={(data) => setCommentCount((data.review_comments ?? []).filter((c) => !c.is_draft && isDiscussion(c)).length)} />
    ),
    documents: documentsOpened ? documents : null,
    threads: <ReviewThreads {...tw.panel} />,
    changes: !comparable ? (
      <div className="rounded-card border border-stone-200 px-4 py-6 text-center">
        <p className="text-small font-semibold text-stone-900">Nothing to compare yet</p>
        <p className="mt-1 text-small text-stone-600">
          {latest !== null ? `v${latest} is the only version.` : "There is one version."} When the authors send the next one, what changed shows here.
        </p>
      </div>
    ) : changesOpened ? (
      <ChangesTab recordId={record.id} versions={versions} threads={tw.threads.sent}
        onShowInPaper={showChange} onOpenThread={tw.openThread} />
    ) : null,
    details,
  };
  const panel = (name: Tab) => name === sideTab ? null : (
    <div key={name} role="tabpanel" id={`${ids}-${name}`} aria-labelledby={`${ids}-tab-${name}`} hidden={shown !== name} className="p-4">
      {body[name]}
    </div>
  );

  // Your part: the server's words, and the controls the server grants.
  // A document opened from the Documents tab is read beside the pane or, narrow,
  // instead of it (IR-1203). The opener moves focus to it, so the launcher is not focused here.
  const paneForTabs: ReviewPane = { showReader: () => { if (drawer) setOpen(false); } };
  const draftCount = finishing ? tw.threads.drafts.length : 0;
  const part = yourPartSummary({ readiness: record.readiness, seat: ownSeat, draftCount });
  const hasFacts = readinessFacts(record.readiness).length > 0;

  return (
    <ReviewPaneContext.Provider value={paneForTabs}>
    <div ref={observe} className="review-workspace-container">
      <div className={cn("review-workspace", !reader && "review-without-paper", sideTab && "review-has-side")}
        style={{ "--mid-w": `${sizes.mid}px`, "--side-w": `${sizes.side}px` } as CSSProperties}>
        {reader && <div id={target.paper} className={cn("review-paper", drawer && !open && offered && "review-paper-offered")} {...(drawer && open ? { inert: "" } : {})}>{tw.wrapReader(reader)}</div>}
        <section ref={pane} id={`${ids}-mid`} aria-label="Review pane" tabIndex={-1}
          role={drawer && open ? "dialog" : "region"} aria-modal={drawer && open || undefined}
          aria-hidden={drawer && !open || undefined} {...(drawer && !open ? { inert: "" } : {})}
          className={cn("review-pane", open && "review-pane-open")}>
          {!drawer && reader && edge("mid", "Resize the review pane")}
          <header id={target.head} className="review-pane-head" {...hiddenWhile(covered)}>
            <div className="-mr-2 flex items-center gap-1">
              <h2 className="mr-auto font-display text-xl font-semibold text-stone-900">Review</h2>
              {!authorView && <button ref={tourButton} type="button"
                className={cn("review-control inline-flex items-center gap-1.5 whitespace-nowrap font-semibold text-stone-700 hover:text-brand", FOCUS_RING)}
                onClick={(e) => startTour(e.currentTarget)}>
                <i className="fas fa-circle-question text-xs" aria-hidden />Take a tour
              </button>}
              {drawer && <button type="button"
                className={cn("review-control inline-flex items-center gap-1.5 whitespace-nowrap font-semibold text-stone-700 hover:text-brand", FOCUS_RING)}
                onClick={closeDrawer}><i className="fas fa-arrow-left text-xs" aria-hidden />Back to paper</button>}
            </div>
            {(record.current_holders.length > 0 || latestVersion) && (
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                {record.current_holders.length > 0 && (
                  <p className="review-holder">With {record.current_holders.map((h) => h.label).join(", ")}</p>
                )}
                {latestVersion && <p className="review-meta"><SentBy version={latestVersion} /></p>}
              </div>
            )}
            {offered && offer}
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
                  <button key={name} type="button" role="tab" id={target.tab(name)}
                    aria-selected={shown === name} aria-controls={`${ids}-${name}`} tabIndex={shown === name ? 0 : -1}
                    aria-describedby={name === "conversation" && commentCount > 0 ? `${ids}-comment-count` : undefined}
                    onClick={() => setTab(name)} className={cn("review-tab", FOCUS_RING)}>
                    {TAB_NAMES[name]}
                    {name === "threads" && tw.count && <>{" "}<span className="review-count">{tw.count}</span></>}
                    {/* The number shows; the tab's name stays "Conversation" and the count is its description. */}
                    {name === "conversation" && commentCount > 0 && <span aria-hidden className="review-count">{commentCount}</span>}
                  </button>
                ))}
              </div>
              {commentCount > 0 && (
                <span id={`${ids}-comment-count`} className="sr-only">
                  {commentCount} comment{commentCount === 1 ? "" : "s"}
                </span>
              )}
              {roomy && <TabBesideMenu buttonId={target.beside} choices={tabs.map((t) => ({ id: t, label: TAB_NAMES[t] }))}
                onChoose={chooseSide} />}
            </div>
          </header>
          <div
            role="region"
            aria-label="Review pane content"
            tabIndex={0}
            className={cn("review-pane-body", FOCUS_RING)}
            {...hiddenWhile(covered)}
          >
            {allTabs.map(panel)}
          </div>
          {/* The author's part is the Readiness tab, so their foot holds only
              the review actions the server grants them, if any (IR-1206). */}
          {authorView ? (
            REVIEW_ACTIONS.some((a) => can.has(a.capability)) && (
              <footer className="review-pane-foot" aria-label="Your actions">
                <ReviewActionBar record={record} can={can} onChanged={onChanged} />
              </footer>
            )
          ) : (
          <YourPartFooter footerRef={footer} id={target.foot} part={part} hasFacts={hasFacts} onShowFacts={() => goTo("readiness")}
            hidden={covered}>
            <ReviewFooterActions record={record} can={can} actions={REVIEWER_FOOTER_ACTIONS} onChanged={onChanged}
              finishing={finishing && !record.review_claim && !unopened} onFinish={tw.finish} drafts={tw.threads.drafts.length}
              lead={record.review_claim
                ? <button type="button" disabled={claiming} onClick={() => void claim()} className={cn(PILL_PRIMARY, FOCUS_RING)}>{claiming ? "Claiming…" : record.review_claim.label}</button>
                : undefined} />
            {claimError && <p role="alert" className="basis-full text-small text-brand">{claimError}</p>}
          </YourPartFooter>
          )}
          {covered && (
            // IR-1336: until the review starts, the pane is covered and its one
            // control is Start review, which records the start (ADR-032 §4).
            <div role="group" aria-label="Your review hasn't started" className="review-cover">
              <p className="text-body font-semibold text-stone-900">Your review hasn&apos;t started</p>
              <p className="max-w-xs text-small text-stone-700">Read the paper on the left at any time. Start the review to comment and decide.</p>
              <button type="button" disabled={starting} onClick={() => void startReview()} className={cn(PILL_PRIMARY, FOCUS_RING)}>
                {starting ? "Starting…" : "Start review"}
              </button>
              {startError && <p role="alert" className="text-small font-semibold text-brand">{startError}</p>}
              {drawer && <button type="button" onClick={() => setOpen(false)} className={cn("review-control text-brand font-semibold", FOCUS_RING)}>Back to paper</button>}
            </div>
          )}
        </section>
        {sideTab && (
          <aside id={target.side} aria-label={`${TAB_NAMES[sideTab]} on the right`} className="review-side" {...hiddenWhile(covered)}>
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
            {!open && !authorView && <button ref={footTour} type="button" className={cn("review-control text-brand", FOCUS_RING)} onClick={(e) => startTour(e.currentTarget)}>Take a tour</button>}
            <button ref={launcher} id={target.launcher} type="button" className={cn("review-control text-brand font-semibold", FOCUS_RING)} onClick={() => setOpen(true)}>Open review pane</button>
          </div>
        )}
        {tour && (
          <GuidedTour label="Review workspace tour" opener={tour.opener} onClose={closeTour}
            steps={reviewTourSteps({ ids, hasPaper: Boolean(reader), drawer, paneOpen: open,
              tabs: allTabs.filter((t): t is TourTab => t !== "readiness"), beside: roomy,
              sideTab: sideTab === "readiness" ? null : sideTab, canStart: can.has("start_thread"),
              canComment: can.has("comment_review"), drafting: finishing })} />
        )}
      </div>
    </div>
    </ReviewPaneContext.Provider>
  );
}
