import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { StatusScreen } from "@/components/shared/StatusScreen";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { failureMessage } from "@/lib/readFailure";
import { NotFoundScreen } from "@/features/errors/NotFoundScreen";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { seatsApi } from "@/api/reviews";
import { PAGE_WIDTH } from "@/components/layout/PageContainer";
import { FOCUS_RING } from "@/components/ui/interaction";
import { useAuth } from "@/hooks/useAuth";
import { useElementWidth } from "@/hooks/useElementWidth";
import { useUIStore } from "@/store/ui.store";
import { PIPELINE_STATUS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { followedFromPaperChat, hasCitationQuote } from "@/lib/citedPage";
import type { ThreadDocument } from "@/types/records";
import type { Region } from "@/types/ai";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { usePageTitle } from "@/hooks/useDocumentTitle";
import { ContinueProposal } from "../ContinueProposal";
import {
  capabilitiesFor,
  hasPaper as recordHasPaper,
  isOwner,
  isParticipant,
  isReviewing,
  seatToOpen,
  sectionsFor,
  type PaperSection,
  type Viewer,
} from "@/features/records/capabilities";
import { usePaperChat } from "./PaperChatDock";
import { CORNER_CLEARANCE_CLASS } from "./AskIrisFab";
import { useReadingHighlights, type ReadableHighlight } from "./useReadingHighlights";
import { HighlightSwatch, type SelectionAction } from "./SelectionMenu";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { type ShownDocumentState } from "./DocumentInReader";
import { slotUploadDocument, type ReaderDocument } from "./readerDocument";
import { EditDetailsDialog } from "./EditDetailsDialog";
import { REVIEW_ACTIONS } from "./reviewActions";
import { VersionPicker } from "./VersionPicker";
import { readingTier } from "./paneLayout";
import { ReadingHeader } from "./ReadingHeader";
import { useFragmentFocus } from "./useFragmentFocus";
import { citationLandingNotice } from "./citationLandingNotice";
import { useCitationLanding } from "./useCitationLanding";
import { useViewLocation } from "./useViewLocation";
import { PaperDownloadControl } from "./PaperDownloadControl";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { LoadingSkeleton, MainColumnSkeleton } from "./PaperViewSkeletons";
import { useRecordLoader } from "./useRecordLoader";
import { useSidePanel } from "./useSidePanel";
import { PaperReader } from "./PaperReader";
import { OverviewSection } from "./OverviewSection";
import { ReviewSection } from "./ReviewSection";
import { RecordDetailsRail } from "./RecordDetailsRail";
import { EditorialHeader, LineageLinks, type PrimaryAction } from "./EditorialHeader";
import { SaveCiteShare, useShareLink } from "./SaveCiteShare";
import { SidePanel } from "./SidePanel";

/**
 * One page for a record, for every role (IR-411; spec §4.6, ADR-032 §10).
 *
 * Three sections, kept in the URL as `?section=`: **Overview**, **Paper**
 * and **Review**. Which ones a viewer sees, and which actions the
 * header offers, come from the capabilities adapter
 * (`features/records/capabilities.ts`); this page reads no role name of its
 * own. A section the viewer may not open falls back to
 * Overview, so an old or shared link never shows a broken page.
 *
 * Switching sections *replaces* the history entry rather than adding one, and
 * is not an arrival: Back still leaves the paper, and Paper Chat keeps the
 * conversation it is on, pinned or not (IR-355).
 */
export default function PaperViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const tabsId = useId();

  const chat = usePaperChat();
  // Saved highlights are drawn until a plain click on the paper hides them (IR-581).
  const [highlightsShown, setHighlightsShown] = useState(true);
  // The supporting document Review's reader shows (IR-1203); see `shownDocument`.
  const [documentShown, setDocumentShown] = useState<ShownDocumentState | null>(null);
  // The highlight the reader asked to open from Notes (IR-583): where to land,
  // in which version, and the navigation it belongs to, so a later arrival
  // (a citation, Back) is not held to it.
  const [opened, setOpened] = useState<{
    key: number; page: number; regions: Region[]; version: number | null; arrival: string;
  } | null>(null);
  const { record, status: loadStatus, error: loadError, retry, reload: reloadRecord, replace: replaceRecord } =
    useRecordLoader(id);
  // The tab names the paper (IR-1073); until it loads, the route's own "Paper".
  // The previous paper stays in state while the next one loads, so it must match the address.
  usePageTitle(record && String(record.id) === id ? record.title : null);
  const [citeOpen, setCiteOpen] = useState(false);
  const { shareState, share } = useShareLink(id);
  /** *Submit new version* (IR-273): the dialog, and what the last one announced. */
  const [newVersionOpen, setNewVersionOpen] = useState(false);
  const [newVersionDone, setNewVersionDone] = useState<string | null>(null);
  /** Bumped when a document request changes, so the tracker reloads. */
  const [trackerVersion, setTrackerVersion] = useState(0);
  // The author's Review tab action bar, stuck over the bottom of the screen
  // below `reading-wide`: the reader lands citations above it (IR-477).
  // A My Library link names the request it answers as `#fragment` (IR-625).
  useFragmentFocus(location.hash, record != null);

  // Landing from a citation (IR-284, IR-578): the page to open at, the passage
  // to draw and the way back to the answer.
  const { resolution, openAtPage, landingPage, backToAnswer, chatReturn, navCitation, pageContext } =
    useCitationLanding(id, () => {
      chat.setOpen(true);
      chat.setMinimized(false);
    });

  // The workspace's own width picks the Paper layout (IR-569), so either
  // sidebar state counts; null until measured.
  const [observeWorkspace, workspaceWidth] = useElementWidth<HTMLDivElement>();
  const tier = readingTier(workspaceWidth);
  const enterReadingRail = useUIStore((s) => s.enterReadingRail);
  const leaveReadingRail = useUIStore((s) => s.leaveReadingRail);
  const addToast = useUIStore((s) => s.addToast);

  // Before the early returns below, so the hooks that follow can use them.
  const viewer: Viewer | null = user ? { id: user.id, role_name: user.role_name } : null;
  const sections = record ? sectionsFor(record, viewer) : [];
  const {
    section,
    readerSection,
    documentsWanted,
    editRequested,
    askedVersion,
    arrivalKey,
    setViewParams,
    setViewParam,
  } = useViewLocation({ sections, openAtPage });
  // Still on the record being left while the next one loads.
  const arriving = loadStatus === "loading" || !record || record.id !== Number(id);
  const onPaperTab = record != null && section === "paper";
  const onReviewTab = section === "review";
  // Ask IRIS reads published papers only (ADR-052 as amended, IR-1252), so it isn't
  // offered beside any other: the Ask IRIS page still searches the published ones.
  const askOffered = record?.pipeline_status === PIPELINE_STATUS.PUBLISHED;
  // Ask IRIS and Notes (IR-569, IR-580): one panel, laid out by reading tier.
  const panel = useSidePanel({
    chat, id, onPaperTab, onReviewTab, tier, workspaceWidth, askOffered, arriving, openAtPage, arrivalKey,
  });
  const { notesWanted, askAbout, addToNote, chatMinimized, chatModal, stepAsideForHighlight } = panel;
  // The reader draws the reader's own highlights wherever the paper shows, so
  // they are read then, and when Notes lists them (IR-583).
  const highlights = useReadingHighlights(Number(id), !arriving && (onPaperTab || onReviewTab || notesWanted));

  // Reading collapses the sidebar to its rail, for this visit only (IR-569).
  useEffect(() => {
    if (!onPaperTab) return;
    enterReadingRail();
    return leaveReadingRail;
  }, [onPaperTab, enterReadingRail, leaveReadingRail]);

  /**
   * RDCO withdrew the paper (IR-798): it is deleted, so reading it again would
   * only say it is gone. Say what happened and go to the review queue.
   */
  const handleRdcoWithdrawn = () => {
    addToast({ type: "success", message: "Paper withdrawn. Its owners and reviewers have been told." });
    navigate("/review", { replace: true });
  };

  /** A document or request changed: re-read what derives from it. */
  const handleDocumentRequestChanged = async () => {
    setTrackerVersion((v) => v + 1);
    await reloadRecord();
  };

  // The whole page is a skeleton only before the first record arrives.
  // Moving from one record to another keeps the page, and Paper Chat with
  // it, and swaps only the main column (IR-355): a citation followed from
  // the chat must not unmount the conversation it was followed from.
  if (loadStatus === "loading" && !record) return <LoadingSkeleton />;

  if (loadStatus === "interrupted") {
    return <InterruptedState what="record" onRetry={retry} />;
  }

  if (loadStatus === "failed") {
    return (
      <StatusScreen
        tone="error"
        icon="fa-circle-exclamation"
        title="We couldn't load this record"
        message={failureMessage(loadError)}
        actions={
          <button
            type="button"
            onClick={retry}
            className={cn(PILL_PRIMARY, FOCUS_RING)}
          >
            Try again
          </button>
        }
      />
    );
  }

  // Missing and refused alike (IR-153), on the shared Not found screen (IR-745).
  if (!record) return <NotFoundScreen subject="Record" />;

  const can = capabilitiesFor(record);
  const userIsOwner = isOwner(record, viewer);
  // Review is one full-height workspace for everyone (IR-1206): the owners'
  // editorial header left it, so Back and the title are all above the reader.
  const reviewWorkspace = onReviewTab;
  const participant = isParticipant(record, viewer);
  const reviewing = isReviewing(record, viewer);

  const editOpen = editRequested && can.has("edit_details") && !arriving;

  // Versions (IR-416). Null to a viewer who may not read the review, so a
  // reader of a published paper has none, and `?version=` means nothing to
  // them. An earlier version is open only while it is asked for, exists and
  // has a manuscript; the newest is the current paper, read as it always was.
  const versions = record.versions ?? [];
  const latestVersion = versions.length > 0 ? versions[versions.length - 1] : null;
  // While the owner's revised manuscript is unsubmitted (IR-273), the current
  // paper is that upload, so the newest version opens like an earlier one.
  const viewedVersion =
    versions.find(
      (v) =>
        v.number === askedVersion && (v !== latestVersion || record.manuscript_unsubmitted) && v.manuscript_url,
    ) ?? null;
  // A highlight opened from Notes lands like a citation: its page and region,
  // in the version it belongs to. It holds only for the navigation it was
  // opened in, and only once the version it names is the one shown.
  const openedHere = opened && opened.arrival === arrivalKey ? opened : null;
  const openedInShown =
    openedHere && openedHere.version === (viewedVersion?.number ?? null) ? openedHere : null;
  // What the reader draws: highlights made on the bytes it shows. A stale one is
  // drawn only on the version that still holds its bytes -- never on the paper now.
  const drawnHighlights = highlights.items
    .filter((h) => (viewedVersion ? h.state === "stale" && h.open_version === viewedVersion.number : h.state === "current"))
    .map((h) => ({ key: h.id, regions: h.regions }));
  // The menu is offered on the current paper only (ADR-065 §8), so this names the current version.
  const currentVersionLabel = record.manuscript_unsubmitted
    ? "Unsubmitted upload"
    : latestVersion ? `Version ${latestVersion.number}` : "Current version";
  const selectionActions: SelectionAction[] = [
    // Wherever Ask IRIS is offered (IR-581). A typed question is sent with the passage at once,
    // from the composer's own Send; with nothing typed, Paper Chat opens on an editable question.
    ...(onReviewTab || !askOffered ? [] : [{
      id: "ask-selection", label: "Ask about selection", short: "Ask IRIS",
      placeholder: "Ask IRIS about this passage…",
      icon: <AskIrisMark className="size-4" />,
      run: (passage, manuscriptRevision, question) => {
        askAbout({
          recordId: record.id, title: record.title, versionLabel: currentVersionLabel, manuscriptRevision,
          page: passage.page, quote: passage.quote,
          ...(question ? { question, send: true } : {}),
        });
      },
    } satisfies SelectionAction]),
    {
      id: "save-highlight", label: "Save highlight", short: "Highlight", sendIcon: "fa-check",
      placeholder: "Add a note to your Notes (optional)…",
      icon: <HighlightSwatch />,
      run: (passage, manuscriptRevision, text) => {
        setHighlightsShown(true);
        void highlights.save(passage, manuscriptRevision);
        // The reader's own words go to their Notes, never into the highlight (ADR-065 §1).
        if (text) {
          addToNote(`Page ${passage.page}: ${text}`);
        }
      },
    },
  ];
  const openHighlight = (h: ReadableHighlight) => {
    setHighlightsShown(true);
    const version = h.state === "stale" ? h.open_version : null;
    setOpened((last) => ({
      key: (last?.key ?? 0) + 1, page: h.page, regions: h.regions, version, arrival: arrivalKey,
    }));
    // The paper, in the version that has its bytes; a panel that would cover
    // the passage steps aside, as it does for a citation.
    setViewParams({ section: readerSection, version: version == null ? null : String(version) });
    stepAsideForHighlight();
  };
  /** Open version `n`, or the current paper for null, in a section that shows the paper. */
  const chooseVersion = (n: number | null) =>
    setViewParams({
      version: n == null ? null : String(n),
      ...(section !== "paper" && section !== "review" && readerSection !== "overview"
        ? { section: readerSection }
        : {}),
    });
  // A citation's regions and page are the current paper's (ADR-031), so an
  // earlier version opens at its start with nothing highlighted.
  const highlightRegions: Region[] = openedInShown
    ? openedInShown.regions
    : !viewedVersion && navCitation && navCitation.record_id === record.id && hasCitationQuote(navCitation)
      ? pageContext
        ? navCitation.regions.filter((region) => region.page === navCitation.page)
        : navCitation.regions
      : [];
  const landingNotice = viewedVersion || openedInShown
    ? null
    : citationLandingNotice(resolution, pageContext, openAtPage, highlightRegions.length > 0);
  // A download request waiting on RDCO is the paper's state, so it sits in the
  // record bar, not beside zoom (IR-1098, audit CMP-06). Only where the bar
  // shows the paper and has room: on a phone it stays in the reader's toolbar,
  // as the version does. An earlier version offers no download at all.
  // A supporting document opened from Documents (IR-1203), shown in Review's
  // reader instead of the manuscript. It holds only for the address it was
  // opened at: any change of view (a Version, a section, a citation) brings
  // the manuscript back, and so does a thread or Changes' *Show in paper*.
  const shown = section === "review" && documentShown?.at === location.search ? documentShown : null;
  const openDocument = (document: ReaderDocument, opener: HTMLElement) =>
    setDocumentShown({ document, at: location.search, opener });
  const showManuscript = () => setDocumentShown(null);
  // A thread's document (IR-1204), opened from its card: focus goes back there.
  const showThreadDocument = (thread: ThreadDocument) => {
    const opener = window.document.activeElement;
    setDocumentShown({
      document: slotUploadDocument(thread.slot, { id: thread.upload, version: thread.version }, thread.extension, !thread.earlier),
      at: location.search,
      opener: opener instanceof HTMLElement ? opener : null,
    });
  };
  const pendingInBar =
    (onPaperTab || reviewWorkspace) && (tier === "wide" || tier === "overlay") && !viewedVersion && !shown &&
    record.download?.state === "pending";

  // Where *View* opens the paper: Paper, or a participant's Review (IR-879).
  const hasPaper = readerSection !== "overview" && recordHasPaper(record);
  const showRail = section === "overview" && !arriving;
  // Ask IRIS open beside the page leaves no room for the rail (IR-569).
  const railHidden = showRail && chat.open && !chatMinimized;
  // One filled action per region (spec §4.6, 01-design-system §0): the
  // owner's pending action, else the reviewer's Open review, else View (Save
  // where there is no paper to view, IR-569). When
  // the pending action has its own region -- the revision banner, the
  // Review section's action bar -- the header fills nothing. The bar fills
  // its first granted action, so any granted review action puts the primary
  // there. A draft never reaches this page (it opens in Publish, IR-1227), so
  // `continue_draft` has no action here.
  const primary: PrimaryAction = can.has("create_version")
    ? "elsewhere"
    : can.has("open_review") && section !== "review"
      ? "open_review"
      : section === "review" && (can.has("finish_review") || REVIEW_ACTIONS.some((action) => can.has(action.capability)))
        ? "elsewhere"
        : hasPaper
          ? "view"
          : "save";

  // *Open review* (ADR-032 §4) records when this reviewer started -- the
  // seat moves to `in_review` and the server stamps `opened_at` -- then moves
  // into the Review section. With no unopened seat it only navigates. A
  // failed recording still opens the review: the seat stays `assigned`, and
  // the next *Open review* records it (IR-1206). A recorded seat re-reads the
  // Record through `reloadRecord`, so one the viewer can no longer read falls
  // to the not-available screen (IR-906, IR-1273).
  const openReview = async () => {
    const seat = seatToOpen(record);
    if (seat) {
      let opened = false;
      try {
        await seatsApi.open(seat.id);
        opened = true;
      } catch {
        // See above: the review opens regardless.
      }
      if (opened) await reloadRecord();
    }
    setViewParam("section", "review");
  };

  // Paper mode's version: a compact picker whenever there is a version, v1
  // alone included, so every paper's header looks alike (IR-1214); nothing
  // to a reader shown none (IR-416, IR-479).
  const paperVersion = latestVersion ? (
    <VersionPicker
      compact
      unsubmitted={record.manuscript_unsubmitted}
      versions={versions}
      viewing={viewedVersion?.number ?? null}
      onChoose={chooseVersion}
    />
  ) : null;

  const tabId = (s: PaperSection) => `${tabsId}-${s}`;
  const onTabKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    e.preventDefault();
    const next = sections[(sections.indexOf(section) + step + sections.length) % sections.length];
    setViewParam("section", next);
    document.getElementById(tabId(next))?.focus();
  };

  const viewAction = hasPaper && (
    <button
      type="button"
      onClick={() => setViewParam("section", readerSection)}
      className={primary === "view" ? PILL_PRIMARY : PILL_SECONDARY}
    >
      <i className="fas fa-book-open text-xs" aria-hidden />
      View
    </button>
  );
  const saveCiteShare = (
    <SaveCiteShare record={record} savePrimary={primary === "save"} canCite={can.has("cite")} onCite={() => setCiteOpen(true)}
      shareState={shareState} onShare={share} />
  );

  // What left the owners' header for their Review's Details tab (IR-1206):
  // fixing the title or abstract during a revision, and where the paper
  // came from or went next. Each only where the server offers it.
  const authorDetails = (can.has("edit_details") || can.has("continue_as") || record.lineage?.derived_from || record.lineage?.continued_as) ? (
    <div className="flex flex-col items-start gap-3">
      {can.has("edit_details") && (
        <button type="button" onClick={() => setViewParam("edit", "details")} className={PILL_SECONDARY}>
          <i className="fas fa-pen text-2xs" aria-hidden />
          Edit details
        </button>
      )}
      <LineageLinks lineage={record.lineage} />
      {can.has("continue_as") && <ContinueProposal recordId={record.id} />}
    </div>
  ) : null;

  // The one reader (IR-352), for the Paper tab and the Review section alike:
  // a citation lands the same way in either (IR-354).
  const reader = (
    <PaperReader
      record={record}
      viewedVersion={viewedVersion}
      latestVersion={latestVersion}
      onShowCurrentVersion={() => setViewParam("version", null)}
      landingNotice={landingNotice}
      highlightsNotice={highlights.notice}
      onPaperTab={onPaperTab}
      workspace={onPaperTab || reviewWorkspace}
      contained={onPaperTab || reviewWorkspace || tier === "wide"}
      // On a phone's one-row bar there is no room for the version, so it
      // sits at the start of the reader's toolbar (IR-1092).
      toolbarStart={(onPaperTab || reviewWorkspace) && tier === "single" ? paperVersion : undefined}
      pendingInBar={pendingInBar}
      onDownloadChanged={reloadRecord}
      reader={{
        scrollToPage: openedInShown ? openedInShown.page : viewedVersion ? null : landingPage,
        // Where the reader left off follows their account (IR-573); a citation,
        // a highlight or `?page=` above still wins, and an earlier Version keeps
        // none. A citation still being re-read keeps none yet, so the old place
        // is never put back only to jump to the citation after.
        keepPlace: resolution.status !== "loading",
        highlightRegions,
        landingLook: openedInShown ? "highlight" : "citation",
        navKey: openedInShown ? `highlight-${openedInShown.key}` : arrivalKey,
        highlights: drawnHighlights,
        selectionActions,
        highlightsShown,
        onHighlightsShownChange: setHighlightsShown,
      }}
    />
  );

  return (
    // The `reading` container (IR-569): its width, not the window's, lays
    // out the page. Paper is a full-height workspace (record bar, then the
    // paper beside Ask IRIS); the other sections scroll with the window,
    // at the app's standard width except Review, which uses all of it.
    <div
      ref={observeWorkspace}
      className={cn(
        "relative [container-type:inline-size] [container-name:reading]",
        (onPaperTab || reviewWorkspace) && "flex flex-col h-[calc(100dvh-3.5rem)] md:h-dvh overflow-hidden",
      )}
    >
      <ReadingHeader
        inert={chatModal}
        className={cn(!onPaperTab && !reviewWorkspace && "sticky top-0 z-30")}
        sections={sections}
        section={section}
        onSelect={(s) => setViewParam("section", s)}
        onTabKeyDown={onTabKeyDown}
        tabId={tabId}
        panelId={arriving ? undefined : `${tabsId}-panel`}
        onBack={() => navigate(-1)}
        onBackToAnswer={backToAnswer}
        title={!onPaperTab && !reviewWorkspace ? undefined : arriving ? null : record.title}
        // Not in the bar below 640px, where the reader's toolbar holds it. Not
        // while a supporting document is shown: the bar would describe the
        // manuscript, and the document's strip names what is shown (IR-1203).
        version={(onPaperTab || reviewWorkspace) && tier !== "single" && !shown ? paperVersion : undefined}
        actions={pendingInBar ? (
          <PaperDownloadControl
            recordId={record.id}
            recordTitle={record.title}
            download={record.download}
            fill
            onChanged={reloadRecord}
          />
        ) : undefined}
      />
      <div
        className={cn(
          onPaperTab || reviewWorkspace
            ? "flex-1 min-h-0 flex"
            : onReviewTab
              ? "px-4 sm:px-7 pt-6 pb-7"
              : "flex items-start",
        )}
      >
        <div
          {...(chatModal ? { inert: "" } : {})}
          className={cn(
            "min-w-0",
            (onPaperTab || reviewWorkspace) && "flex-1 min-h-0 flex flex-col",
            // Its own container, so the rail and the page read the room the
            // panel leaves them (IR-569), as the reader reads the paper's.
            !onPaperTab && !onReviewTab && "flex-1 [container-type:inline-size] [container-name:overview]",
          )}
        >

          <div
            className={cn(
              onPaperTab || reviewWorkspace ? "flex-1 min-h-0 flex flex-col" : "grid gap-8 items-start",
              !onPaperTab && !onReviewTab && cn("px-4 sm:pl-14 sm:pr-8 pt-8", CORNER_CLEARANCE_CLASS, PAGE_WIDTH[showRail ? "wide-left" : "standard"]),
              // Wide: the page takes the width it has, with what the record is
              // held under beside it while there is room, and under it when
              // the panel or the sidebar leave none (IR-569). Ask IRIS open
              // takes its place: the rail folds away, and the page sits centred
              // in the room the panel leaves rather than against its left edge.
              showRail &&
                cn(
                  "transition-[grid-template-columns,column-gap,row-gap] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
                  railHidden
                    ? "gap-y-0 overview-wide:grid-cols-[minmax(0,60rem)_0rem] overview-wide:justify-center overview-wide:gap-x-0"
                    : "overview-wide:grid-cols-[minmax(0,60rem)_clamp(17rem,25cqw,22rem)] overview-wide:justify-between overview-wide:gap-x-8",
                ),
            )}
          >
          {/* ------------------------------------------------------------- */}
          {/* Main column                                                    */}
          {/* ------------------------------------------------------------- */}
          {arriving ? (
            <MainColumnSkeleton />
          ) : (
          <div
            className={cn(
              "min-w-0",
              onPaperTab || reviewWorkspace ? "flex-1 min-h-0 flex flex-col" : "space-y-8",
              // The Overview reads in one column, up to 60rem, flush left with
              // the rail beside it. With Ask IRIS open the rail is gone, so the
              // column is centred in the room that is left.
              showRail && "w-full max-w-[60rem]",
              railHidden && "mx-auto",
            )}
          >
            {/* Editorial header (IR-356): not in Paper mode, where the record
                bar holds the paper in one line (IR-569). */}
            {!onPaperTab && !reviewWorkspace && (
              <EditorialHeader
                record={record}
                section={section}
                can={can}
                primary={primary}
                versions={versions}
                latestVersion={latestVersion}
                viewedVersion={viewedVersion}
                onChooseVersion={chooseVersion}
                onOpenReview={openReview}
                onEditDetails={() => setViewParam("edit", "details")}
                viewAction={viewAction}
                saveCiteShareActions={saveCiteShare}
              />
            )}

            <div
              id={`${tabsId}-panel`}
              role="tabpanel"
              aria-labelledby={tabId(section)}
              className={onPaperTab || reviewWorkspace ? "flex-1 min-h-0 flex flex-col" : "space-y-8"}
            >
            {section === "paper" && reader}

            {section === "overview" && (
              <OverviewSection
                record={record}
                can={can}
                userIsOwner={userIsOwner}
                viewerId={user?.id ?? null}
                viewerName={user ? `${user.first_name} ${user.last_name}`.trim() : null}
                actions={<>{viewAction}{saveCiteShare}</>}
                newVersionOpen={newVersionOpen}
                newVersionDone={newVersionDone}
                onOpenNewVersion={() => setNewVersionOpen(true)}
                onCloseNewVersion={() => setNewVersionOpen(false)}
                onNewVersionDone={(outcome) => {
                  setNewVersionOpen(false);
                  setNewVersionDone(outcome);
                  addToast({ type: "success", message: outcome });
                  setTrackerVersion((n) => n + 1);
                  // A failed reload leaves the page as it was, unless the
                  // Record can no longer be read (IR-906, IR-1273).
                  void reloadRecord();
                }}
                onNewVersionRefreshed={(fresh) => {
                  replaceRecord(fresh);
                  setTrackerVersion((n) => n + 1);
                }}
                onDocumentsChanged={handleDocumentRequestChanged}
                onRecordReplaced={replaceRecord}
              />
            )}

            {section === "review" && (
              <ReviewSection
                record={record}
                can={can}
                userIsOwner={userIsOwner}
                reviewing={reviewing}
                authorDetails={authorDetails}
                onOpenReview={openReview}
                onShowVersion={chooseVersion}
                reader={reader}
                shown={shown}
                onShowManuscript={showManuscript}
                onShowThreadDocument={showThreadDocument}
                onOpenDocument={openDocument}
                timelineVersion={trackerVersion}
                onChanged={handleDocumentRequestChanged}
                showDocuments={documentsWanted}
                onDocumentsShown={() => setViewParams({ documents: null, section: "review" })}
              />
            )}
            </div>
          </div>
          )}

          {showRail && (
            <RecordDetailsRail
              record={record}
              headingId={`${tabsId}-details`}
              participant={participant}
              hidden={railHidden}
              trackerVersion={trackerVersion}
              onOpenHistory={() => setViewParam("section", "review")}
              onChanged={reloadRecord}
              onWithdrawn={handleRdcoWithdrawn}
            />
          )}
          </div>

        <PaperCiteModal record={record} isOpen={citeOpen} onClose={() => setCiteOpen(false)} />
        {editOpen && (
          <EditDetailsDialog
            record={record}
            selfId={user?.id ?? null}
            onClose={() => setViewParam("edit", null)}
            onSaved={(updated) => {
              replaceRecord(updated);
              setViewParam("edit", null);
            }}
          />
        )}
      </div>

      <SidePanel
        record={record}
        chat={chat}
        panel={panel}
        arrival={
          arriving
            ? null
            : { key: arrivalKey, fromPaperChat: followedFromPaperChat(location.state) }
        }
        onReviewTab={onReviewTab}
        askOffered={askOffered}
        highlights={highlights}
        onOpenHighlight={openHighlight}
        canOpenVersion={(n) => versions.some((v) => v.number === n && v.manuscript_url && (v !== latestVersion || record.manuscript_unsubmitted))}
        viewingVersion={viewedVersion?.number ?? null}
        chatReturn={chatReturn}
      />
      </div>
    </div>
  );
}
