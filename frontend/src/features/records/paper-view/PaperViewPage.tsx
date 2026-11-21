import { Suspense, useEffect, useId, useState, type KeyboardEvent } from "react";
import { StatusScreen } from "@/components/shared/StatusScreen";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { failureMessage } from "@/lib/readFailure";
import { NotFoundScreen } from "@/features/errors/NotFoundScreen";
import { useParams, useNavigate, useLocation, Link } from "react-router-dom";
import { seatsApi } from "@/api/reviews";
import { PAGE_WIDTH } from "@/components/layout/PageContainer";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";
import { Skeleton } from "@/components/ui";
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
import { PaperSaveDropdown } from "@/features/discover/PaperSaveDropdown";
import { RelatedPublishedResearch } from "./RelatedPublishedResearch";
import { RelatedWorks } from "./RelatedWorks";
import { usePageTitle } from "@/hooks/useDocumentTitle";
import { ContinueProposal } from "../ContinueProposal";
import { ReviewRoutingTracker } from "./ReviewRoutingTracker";
import { ActionRequiredPanel } from "@/features/document-requests/ActionRequiredPanel";
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
import {
  usePaperChat,
  PaperChatPanel,
  PANEL_WIDTH_MIN,
} from "./PaperChatDock";
import { AskIrisFab, CORNER_CLEARANCE_CLASS, NotesFab } from "./AskIrisFab";
import { NotesPanel } from "./NotesPanel";
import { useReadingHighlights, type ReadableHighlight } from "./useReadingHighlights";
import { HighlightSwatch, type SelectionAction } from "./SelectionMenu";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { CommentsSection } from "./CommentsSection";
import { PaperAiOverview } from "./PaperAiOverview";
import { ContactPersonCard } from "./ContactPersonCard";
import { EmbargoCard } from "./EmbargoCard";
import { UnlistedCard } from "./UnlistedCard";
import { RdcoPaperControls } from "./RdcoPaperControls";
import { PaperGovernance } from "./PaperGovernance";
import { DocumentsTab } from "./DocumentsTab";
import { DocumentInReader, type ShownDocumentState } from "./DocumentInReader";
import { slotUploadDocument, type ReaderDocument } from "./readerDocument";
import { EditDetailsDialog } from "./EditDetailsDialog";
import { NewVersionDialog, newVersionSummary } from "./NewVersionDialog";
import { RevisionManuscriptUpload } from "./RevisionManuscriptUpload";
import { ReviewWorkspaceLayout } from "./ReviewWorkspaceLayout";
import { REVIEW_ACTIONS } from "./reviewActions";
import { VersionBanner, VersionPicker } from "./VersionPicker";
import { OVERVIEW_ASIDE_MAX_HEIGHT, OVERVIEW_ASIDE_TOP, readingTier } from "./paneLayout";
import { ReadingHeader } from "./ReadingHeader";
import { titleSizeClasses } from "./titleSize";
import { useFragmentFocus } from "./useFragmentFocus";
import { type CitationResolution } from "./useCitationReference";
import { useCitationLanding } from "./useCitationLanding";
import { useViewLocation } from "./useViewLocation";
import { WAITING_TARGET } from "../waitingOnYou";
import { SectionHeading } from "./headings";
import { PaperDownloadControl } from "./PaperDownloadControl";
import { PaperPdfReader } from "./lazyReader";
import { PersonChip } from "./PersonLink";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { IpTagger } from "./IpTagger";
import { LoadingSkeleton, MainColumnSkeleton } from "./PaperViewSkeletons";
import { useRecordLoader } from "./useRecordLoader";
import { useSidePanel } from "./useSidePanel";

/**
 * One page for a record, for every role (IR-411; spec §4.6, ADR-032 §10).
 *
 * Four sections, kept in the URL as `?section=`: **Overview**, **Paper**,
 * **Review** and **Files**. Which ones a viewer sees, and which actions the
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
  const [shareState, setShareState] = useState<"idle" | "copied" | "failed">("idle");
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
  const {
    note,
    notesWanted,
    openNotes,
    openAskFromNotes,
    askAbout,
    addToNote,
    panelRef,
    askButtonRef,
    notesButtonRef,
    chatMinimized,
    chatModal,
    panelRoom,
    panelWidth,
    panelClass: chatPanelClass,
    closeChat,
    backToPaper,
    openAsk,
    restore,
    stepAsideForHighlight,
  } = useSidePanel({
    chat, id, onPaperTab, onReviewTab, tier, workspaceWidth, askOffered, arriving, openAtPage, arrivalKey,
  });
  // The reader draws the reader's own highlights wherever the paper shows, so
  // they are read then, and when Notes lists them (IR-583).
  const highlights = useReadingHighlights(Number(id), !arriving && (onPaperTab || onReviewTab || notesWanted));

  // Reading collapses the sidebar to its rail, for this visit only (IR-569).
  useEffect(() => {
    if (!onPaperTab) return;
    enterReadingRail();
    return leaveReadingRail;
  }, [onPaperTab, enterReadingRail, leaveReadingRail]);

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

  const authorNames = record.authors.map((a) => a.name.trim()).filter(Boolean);

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
  // The one reader (IR-352), for the Paper tab and the Review section alike:
  // a citation lands the same way in either (IR-354).
  const reader = () => (
    <>
      {(viewedVersion || record.manuscript_unsubmitted) && (
      <div className={cn("space-y-3", onPaperTab && "px-4 pt-3")}>
      {viewedVersion && latestVersion && (
        <VersionBanner
          viewing={viewedVersion.number}
          latest={latestVersion.number}
          onBack={() => setViewParam("version", null)}
        />
      )}
      {/* The owner reads their own unsubmitted upload; nobody else is served
          it (IR-273), so only they are told. */}
      {!viewedVersion && record.manuscript_unsubmitted && (
        <div className="rounded-card border border-stone-300 bg-surface px-4 py-3 flex items-start gap-3">
          <i className="fas fa-file-pen text-sm text-brand mt-0.5" aria-hidden />
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-semibold text-stone-900">Your revised manuscript, not yet submitted</p>
            <p className="text-stone-700 mt-0.5">
              Reviewers still read {latestVersion ? `v${latestVersion.number}` : "the submitted version"} until
              you submit the new version.
            </p>
            <p className="text-stone-700 mt-0.5">
              Ask IRIS answers about the submitted version
              {latestVersion ? ` (v${latestVersion.number})` : ""} until you submit.
            </p>
          </div>
        </div>
      )}
      </div>
      )}
      {landingNotice && (
        <p role="status" className={cn("text-small text-stone-600", onPaperTab ? "px-4 pt-3" : "mb-3")}>
          {landingNotice}
        </p>
      )}
      {highlights.notice && (
        <p role="status" className={cn("text-small", highlights.notice.kind === "saved" ? "text-stone-600" : "font-semibold text-brand", onPaperTab ? "px-4 pt-3" : "mb-3")}>
          {highlights.notice.text}
        </p>
      )}
      <Suspense fallback={<Skeleton rows={8} label="Loading the reader…" />}>
        <PaperPdfReader
          recordId={record.id}
          version={viewedVersion?.number ?? null}
          scrollToPage={openedInShown ? openedInShown.page : viewedVersion ? null : landingPage}
          // Where the reader left off follows their account (IR-573); a citation,
          // a highlight or `?page=` above still wins, and an earlier Version keeps
          // none. A citation still being re-read keeps none yet, so the old place
          // is never put back only to jump to the citation after.
          keepPlace={resolution.status !== "loading"}
          highlightRegions={highlightRegions}
          landingLook={openedInShown ? "highlight" : "citation"}
          navKey={openedInShown ? `highlight-${openedInShown.key}` : arrivalKey}
          highlights={drawnHighlights}
          selectionActions={selectionActions}
          highlightsShown={highlightsShown}
          onHighlightsShownChange={setHighlightsShown}
          contained={onPaperTab || reviewWorkspace || tier === "wide"}
          fill={onPaperTab || reviewWorkspace}
          // Notes and Ask IRIS float over the Paper tab's bottom-right (IR-1079).
          clearCorner={onPaperTab}
          // On a phone's one-row bar there is no room for the version, so it
          // sits at the start of the reader's toolbar (IR-1092).
          toolbarStart={(onPaperTab || reviewWorkspace) && tier === "single" ? paperVersion : undefined}
          downloadControl={
            // An earlier version is not offered as a copy: the download route
            // serves only the current paper, and every copy must be marked.
            viewedVersion ? undefined : (
              <PaperDownloadControl
                recordId={record.id}
                recordTitle={record.title}
                download={record.download}
                fill={onPaperTab || reviewWorkspace}
                onChanged={reloadRecord}
                pending={pendingInBar ? "elsewhere" : "here"}
              />
            )
          }
        />
      </Suspense>
    </>
  );

  // One filled action per region (spec §4.6, 01-design-system §0): the
  // owner's pending action, else the reviewer's Open review, else View (Save
  // where there is no paper to view, IR-569). When
  // the pending action has its own region -- the revision banner, the
  // Review section's action bar -- the header fills nothing. The bar fills
  // its first granted action, so any granted review action puts the primary
  // there.
  // Where *View* opens the paper: Paper, or a participant's Review (IR-879).
  const hasPaper = readerSection !== "overview" && recordHasPaper(record);
  const showRail = section === "overview" && !arriving;
  // Ask IRIS open beside the page leaves no room for the rail (IR-569).
  const railHidden = showRail && chat.open && !chatMinimized;
  // A draft never reaches this page (it opens in Publish, IR-1227), so
  // `continue_draft` has no action here.
  const primary = can.has("create_version")
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

  // What left the owners' header for their Review's Details tab (IR-1206):
  // fixing the title or abstract during a revision, and where the paper
  // came from or went next. Each only where the server offers it.
  const lineageLinks = (
    <>
      {record.lineage?.derived_from && (
        <Link to={`/records/${record.lineage.derived_from.id}`} className="text-small underline">
          Developed from Proposal #{record.lineage.derived_from.id} — View proposal
        </Link>
      )}
      {record.lineage?.continued_as && (
        <Link to={`/records/${record.lineage.continued_as.id}`} className="text-small underline">
          Continued as {record.lineage.continued_as.record_type_name} #{record.lineage.continued_as.id}
        </Link>
      )}
    </>
  );
  const authorDetails = (can.has("edit_details") || can.has("continue_as") || record.lineage?.derived_from || record.lineage?.continued_as) ? (
    <div className="flex flex-col items-start gap-3">
      {can.has("edit_details") && (
        <button type="button" onClick={() => setViewParam("edit", "details")} className={PILL_SECONDARY}>
          <i className="fas fa-pen text-2xs" aria-hidden />
          Edit details
        </button>
      )}
      {lineageLinks}
      {can.has("continue_as") && <ContinueProposal recordId={record.id} />}
    </div>
  ) : null;

  const saveCiteShareActions = (
    <>
      <PaperSaveDropdown
        record={record}
        variant="pill"
        emphasis={primary === "save" ? "primary" : "secondary"}
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
        {shareState === "copied" ? "Link copied" : shareState === "failed" ? "Couldn’t copy" : "Share"}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {shareState === "copied"
          ? "Link to this paper copied"
          : shareState === "failed"
            ? "Couldn’t copy the link. Copy it from the address bar."
            : ""}
      </span>
    </>
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
            {/* Editorial header (IR-356): what it is, who wrote it, then
                what to do with it. Not in Paper mode, where the record bar
                holds the paper in one line (IR-569). */}
            {!onPaperTab && !reviewWorkspace && (
            <header className={cn("space-y-5", section === "overview" && "pb-1")}>
              {/* Sized by its length (IR-1264), never cut. */}
              <h1 className={cn("font-display font-semibold tracking-tight text-stone-900 text-balance", titleSizeClasses(record.title))}>
                {record.title}
              </h1>

              {/* The byline (IR-1264): each author, then the Adviser when the
                  record names one (IR-472), in their own pill. Where the record
                  stands is in Record details for those in its review, and the
                  year and what it is held under are Record details' rows
                  (IR-1089), so the header carries neither. */}
              <div className="flex items-center gap-2 flex-wrap">
                {authorNames.length > 0 ? (
                  <ul className="flex items-center gap-2 flex-wrap" aria-label="Authors">
                    {authorNames.map((name) => {
                      const owner = record.owners.find((candidate) => candidate.full_name.trim().toLocaleLowerCase() === name.toLocaleLowerCase());
                      return (
                        <li key={name}>
                          <PersonChip id={owner?.user} hasProfile={owner?.has_profile} name={name} role="Author" />
                        </li>
                      );
                    })}
                  </ul>
                ) : <p className="text-sm text-stone-500 italic">Authors not recorded</p>}
                {record.adviser_name && (
                  <ul className="flex items-center gap-2 flex-wrap" aria-label="Adviser">
                    <li>
                      <PersonChip
                        id={record.adviser ?? undefined}
                        hasProfile={record.adviser != null && record.adviser_has_profile === true}
                        name={record.adviser_name}
                        role="Adviser"
                      />
                    </li>
                  </ul>
                )}
                <ResearchOriginBadge origin={record.origin} />
              </div>

              {lineageLinks}
              {can.has("continue_as") && <ContinueProposal recordId={record.id} />}
              {/* The version picker (IR-416) whenever there is a version,
                  v1 alone included (IR-1214), and beside the owner's
                  unsubmitted revision (IR-273). */}
              {latestVersion && (
                <VersionPicker
                  unsubmitted={record.manuscript_unsubmitted}
                  versions={versions}
                  viewing={viewedVersion?.number ?? null}
                  onChoose={chooseVersion}
                />
              )}

              {(section !== "overview" || primary === "open_review" || can.has("edit_details")) && (
                <div className="flex items-center gap-2 flex-wrap">
                  {primary === "open_review" && (
                    <button type="button" onClick={() => void openReview()} className={PILL_PRIMARY}>
                      <i className="fas fa-clipboard-check text-xs" aria-hidden />
                      Open review
                    </button>
                  )}

                  {section !== "overview" && viewAction}

                  {can.has("edit_details") && (
                    <button type="button" onClick={() => setViewParam("edit", "details")} className={PILL_SECONDARY}>
                      <i className="fas fa-pen text-2xs" aria-hidden />
                      Edit details
                    </button>
                  )}

                  {section !== "overview" && saveCiteShareActions}
                </div>
              )}
            </header>
            )}

            <div
              id={`${tabsId}-panel`}
              role="tabpanel"
              aria-labelledby={tabId(section)}
              className={onPaperTab || reviewWorkspace ? "flex-1 min-h-0 flex flex-col" : "space-y-8"}
            >
            {section === "paper" && reader()}

            {section === "overview" && (
              <>
                {/* Action required (spec §4.10): what is waiting on the
                    owner comes first. The revision banner and the document
                    requests below are that, whole; a separate "Your
                    submission" summary repeated them and the rail (IR-1264). */}
                {/* Revision requests are answered through Submit new version. */}
                {userIsOwner && record.revision.open.length > 0 && (
                  <section
                    id={WAITING_TARGET.revision}
                    tabIndex={-1}
                    aria-labelledby="revision-requested-heading"
                    className="rounded-card border border-stone-300 bg-surface p-4 scroll-mt-20 focus:outline-none"
                  >
                    <h2
                      id="revision-requested-heading"
                      className="text-sm font-bold text-brand-dark flex items-center gap-2"
                    >
                      <i className="fas fa-arrow-rotate-left text-xs" aria-hidden />
                      Revision requested
                    </h2>
                    <p className="text-sm text-brand leading-relaxed mt-1">
                      Nothing can be decided on this record until you answer with a new version. Offices
                      that already cleared it keep their clearance; only the reviewers who asked look again.
                    </p>
                    <ul className="mt-3 space-y-3">
                      {record.revision.open.map((r) => (
                        <li key={r.id} className="text-sm text-stone-900">
                          <p className="font-semibold">
                            {r.label} asked for changes
                            {r.version != null && <span className="font-normal text-stone-600"> · on v{r.version}</span>}
                          </p>
                          {r.reason && (
                            <p className="text-justified mt-1 whitespace-pre-wrap break-words leading-relaxed text-stone-700">
                              {r.reason}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                    {can.has("create_version") && record.revision.new_version && (
                      <div className="mt-4 border-t border-stone-300 pt-3">
                        <p className="text-sm text-stone-700 leading-relaxed">
                          Upload your revised manuscript here, add any requested document below, or edit
                          the details, then submit. {newVersionSummary(record.revision.new_version)}
                        </p>
                        {can.has("replace_manuscript") && (
                          <div className="mt-3">
                            <RevisionManuscriptUpload
                              recordId={record.id}
                              staged={record.manuscript_unsubmitted}
                              onUploaded={handleDocumentRequestChanged}
                            />
                          </div>
                        )}
                        {record.revision.new_version.blocked && (
                          <p id="new-version-blocked" className="text-sm text-brand mt-2">
                            {record.revision.new_version.blocked}
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={() => setNewVersionOpen(true)}
                          aria-describedby={record.revision.new_version.blocked ? "new-version-blocked" : undefined}
                          className={cn(PILL_PRIMARY, "mt-3")}
                        >
                          <i className="fas fa-paper-plane text-2xs" aria-hidden />
                          Submit new version
                        </button>
                      </div>
                    )}
                  </section>
                )}
                {/* Rendered while a version can be submitted, so the
                    announcement lands when it fills; nowhere else, so the page
                    keeps one status region (Share's) otherwise. */}
                {(record.revision.new_version != null || newVersionDone) && (
                  <p role="status" aria-live="polite" className="sr-only">
                    {newVersionDone ?? ""}
                  </p>
                )}
                {newVersionOpen && record.revision.new_version && (
                  <NewVersionDialog
                    recordId={record.id}
                    hint={record.revision.new_version}
                    newManuscript={record.manuscript_unsubmitted}
                    onClose={() => setNewVersionOpen(false)}
                    onDone={(outcome) => {
                      setNewVersionOpen(false);
                      setNewVersionDone(outcome);
                      addToast({ type: "success", message: outcome });
                      setTrackerVersion((n) => n + 1);
                      // A failed reload leaves the page as it was, unless the
                      // Record can no longer be read (IR-906, IR-1273).
                      void reloadRecord();
                    }}
                    onRefreshed={(fresh) => {
                      replaceRecord(fresh);
                      setTrackerVersion((n) => n + 1);
                    }}
                  />
                )}

                {userIsOwner && (
                  <ActionRequiredPanel
                    id={WAITING_TARGET.document}
                    recordId={record.id}
                    onChanged={handleDocumentRequestChanged}
                  />
                )}

                {record.workflow_state === "rejected" && (
                  <div className="rounded-card border border-stone-300 bg-surface p-4">
                    <p className="text-sm font-bold text-brand-dark flex items-center gap-2">
                      <i className="fas fa-circle-xmark text-xs" aria-hidden />
                      This record was rejected
                    </p>
                    <p className="text-sm text-brand leading-relaxed mt-1">
                      It cannot be resubmitted. Contact the relevant office if you have questions.
                    </p>
                  </div>
                )}

                {/* Reading sections are separated by space. */}
                <div className="space-y-8">
                {/* The abstract shares the reading column with its heading and actions. */}
                <section>
                  <SectionHeading>Abstract</SectionHeading>
                  {record.abstract ? (
                    <p className="text-justified text-lg text-stone-700 leading-7">
                      {record.abstract}
                    </p>
                  ) : (
                    <p className="text-sm text-stone-500 italic">
                      No abstract was provided for this record.
                    </p>
                  )}
                  <div className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-2.5">
                    {viewAction}
                    {saveCiteShareActions}
                  </div>
                </section>

                <PaperAiOverview record={record} />

                {can.has("tag_ip") && (
                  <IpTagger
                    recordId={record.id}
                    currentIpType={record.ip_type}
                    onSaved={(updated) => replaceRecord(updated)}
                  />
                )}

                {/* The Novelty check (IR-312): the owner's own Proposal only,
                    per ADR-029's 2026-09-26 amendment, item 9. */}
                {userIsOwner && record.record_type_name === "Proposal" && (
                  <RelatedPublishedResearch recordId={record.id} />
                )}

                <RelatedWorks recordId={record.id} />

                {/* Public comments belong to published papers' Overview only. */}
                {record.pipeline_status === "published" && (
                  <CommentsSection recordId={record.id} viewerId={user?.id ?? null} viewerName={user ? `${user.first_name} ${user.last_name}`.trim() : null} />
                )}
                </div>
              </>
            )}

            {section === "review" && (
              <ReviewWorkspaceLayout
                record={record}
                authorView={userIsOwner}
                authorDetails={userIsOwner ? authorDetails : undefined}
                onOpenReview={openReview}
                onShowVersion={chooseVersion}
                can={can}
                reader={recordHasPaper(record)
                  ? shown
                    ? <DocumentInReader recordId={record.id} shown={shown} onBack={showManuscript}
                        fill={reviewWorkspace} contained={reviewWorkspace || tier === "wide"} />
                    : reader()
                  : null}
                onShowManuscript={showManuscript}
                onShowDocument={recordHasPaper(record) ? showThreadDocument : undefined}
                timelineVersion={trackerVersion}
                onChanged={handleDocumentRequestChanged}
                // No Ask IRIS in Review (ADR-032 §10, IR-372 as kept by IR-879).
                showDocuments={documentsWanted}
                // Once shown, the request is spent: the tab is the reviewer's to change.
                onDocumentsShown={() => setViewParams({ documents: null, section: "review" })}
                documents={
                  <DocumentsTab
                    record={record}
                    owner={userIsOwner}
                    editable={can.has("edit_details")}
                    reviewing={reviewing}
                    attach={can.has("attach_file")}
                    replaceManuscript={can.has("replace_manuscript")}
                    onChanged={handleDocumentRequestChanged}
                    onOpen={recordHasPaper(record) ? openDocument : undefined}
                  />
                }
              />
            )}
            </div>
          </div>
          )}

          {/* What the record is held under, and what is attached (spec §4.6).
              Beside the page while it is wide, sticky under the record bar;
              under it otherwise. The party status strip is for participants. */}
          {showRail && (
            // Folds away while Ask IRIS is open (rows when it sits under the
            // page, the column when it sits beside), and is inert meanwhile.
            <div
              aria-hidden={railHidden || undefined}
              {...(railHidden ? { inert: "" } : {})}
              className={cn(
                "grid min-w-0 transition-[grid-template-rows,opacity,visibility] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
                // The track is the scroller's content box, so the aside can
                // fit what its own scrollbar leaves rather than the full
                // column (IR-1178).
                "overview-wide:sticky overview-wide:grid-rows-[1fr] overview-wide:grid-cols-[minmax(0,1fr)] overview-wide:overflow-y-auto overview-wide:overflow-x-hidden",
                OVERVIEW_ASIDE_TOP,
                OVERVIEW_ASIDE_MAX_HEIGHT,
                railHidden ? "grid-rows-[0fr] opacity-0 invisible" : "grid-rows-[1fr] opacity-100",
              )}
            >
              <aside
                aria-labelledby={`${tabsId}-details`}
                // The column's width, held while the column folds, but never
                // wider than the scroller leaves it: its scrollbar takes ~23px
                // and the scroller clipped every row's right edge (IR-1178).
                className="min-h-0 space-y-4 overflow-hidden overview-wide:w-[clamp(17rem,25cqw,22rem)] overview-wide:min-w-[15rem] overview-wide:max-w-full overview-wide:overflow-visible"
              >
                <h2 id={`${tabsId}-details`} className="font-display text-section font-semibold text-stone-900">
                  Record details
                </h2>
                {/* Where the record stands, for those in its review, with who
                    has cleared it; the history is Review's (IR-1264). */}
                {participant && (
                  <ReviewRoutingTracker
                    key={trackerVersion}
                    recordId={record.id}
                    status={<StatusBadge state={record.workflow_state} label={record.workflow_state_label} compact />}
                    onOpenHistory={() => setViewParam("section", "review")}
                  />
                )}
                <PaperGovernance
                  record={record}
                  // Those in the review see every row; anyone else only the
                  // ones that say something (IR-1264). Decided by participation,
                  // never by role (IR-411).
                  full={participant}
                  showStatus={!participant}
                />
                <ContactPersonCard record={record} onChanged={reloadRecord} />
                <EmbargoCard record={record} onChanged={reloadRecord} />
                <UnlistedCard record={record} onChanged={reloadRecord} />
                <RdcoPaperControls
                  record={record}
                  onChanged={reloadRecord}
                  onWithdrawn={handleRdcoWithdrawn}
                />
                {/* No Documents card (IR-1244): Review's Documents tab lists them for
                    those who may download them, and nobody else is sent them. */}
              </aside>
            </div>
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

      {/* Over the paper, the rest of the page waits behind a scrim. */}
      {chatModal && (
        <div
          aria-hidden
          onClick={closeChat}
          className="hidden reading-split:block reading-wide:hidden absolute inset-0 z-30 bg-stone-900/25"
        />
      )}
      {chat.open && chat.tool === "ask" && askOffered && (
        <PaperChatPanel
          record={record}
          // Whether a citation inside the chat brought the reader here, which
          // keeps its conversation open (IR-355); withheld until the record
          // this navigation is going to has arrived. Keyed by arrival, so a
          // change of section is not one.
          arrival={
            arriving
              ? null
              : { key: arrivalKey, fromPaperChat: followedFromPaperChat(location.state) }
          }
          onClose={closeChat}
          onBackToPaper={backToPaper}
          panelRef={panelRef}
          modal={chatModal}
          draft={chat.draft}
          onDraftChange={chat.setDraft}
          resize={
            panelWidth && !chatMinimized
              ? {
                  width: panelWidth,
                  max: Math.max(PANEL_WIDTH_MIN, panelRoom),
                  onChange: chat.setWidth,
                }
              : undefined
          }
          style={panelWidth && !chatMinimized ? { width: panelWidth } : undefined}
          minimized={chatMinimized}
          onRestore={restore}
          viewingVersion={viewedVersion?.number ?? null}
          returnTo={chatReturn}
          onOpenNotes={onReviewTab ? undefined : openNotes}
          selection={chat.selection}
          onSelectionChange={chat.setSelection}
          className={chatPanelClass}
        />
      )}
      {chat.open && chat.tool === "notes" && (
        <NotesPanel
          record={record}
          note={note}
          highlights={highlights}
          onOpenHighlight={openHighlight}
          canOpenVersion={(n) => versions.some((v) => v.number === n && v.manuscript_url && (v !== latestVersion || record.manuscript_unsubmitted))}
          onClose={closeChat}
          onBackToPaper={backToPaper}
          onOpenAsk={askOffered ? openAskFromNotes : undefined}
          panelRef={panelRef}
          modal={chatModal}
          resize={
            panelWidth
              ? { width: panelWidth, max: Math.max(PANEL_WIDTH_MIN, panelRoom), onChange: chat.setWidth }
              : undefined
          }
          style={panelWidth ? { width: panelWidth } : undefined}
          className={chatPanelClass}
        />
      )}
      {/* Closed: two round icons at the bottom right, Notes above Ask IRIS
          (IR-569, IR-1079). On the bar while minimized, which is its way back. */}
      {!chat.open && !onReviewTab && (
        <>
          <NotesFab onOpen={openNotes} buttonRef={notesButtonRef} />
          {askOffered && <AskIrisFab onOpen={openAsk} buttonRef={askButtonRef} />}
        </>
      )}
      </div>
    </div>
  );
}

/**
 * What a reader is told about where a citation landed, when it is not
 * simply the passage, highlighted (IR-578). Every case says what is and is
 * not marked, so nothing reads as a guess.
 */
function citationLandingNotice(
  resolution: CitationResolution,
  pageContext: boolean,
  page: number | null,
  marked: boolean,
): string | null {
  switch (resolution.status) {
    case "changed":
      // The stored page is from when the answer was written; the paper may
      // have changed since, so it is offered as that, not as the passage.
      return page != null
        ? `The passage this answer quoted has changed since, so nothing is highlighted. Page ${page} is where it was when the answer was written.`
        : "The passage this answer quoted has changed since, so nothing is highlighted.";
    case "missing":
      return "That citation is no longer part of the answer, so nothing is highlighted.";
    case "elsewhere":
      return "That citation points at another paper, so nothing is highlighted here.";
    case "gone":
      return "The answer this citation came from is no longer available, so nothing is highlighted.";
    default:
      if (!pageContext || page == null) return null;
      return marked
        ? `Page context: the Overview drew on page ${page} as a whole, so only page ${page} is marked.`
        : `Page context: the Overview drew on page ${page} as a whole.`;
  }
}
