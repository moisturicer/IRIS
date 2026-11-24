import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import type { ReadingStatus } from "@/api/library";
import { canAuthor } from "@/lib/access";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useHistoryStore } from "@/store/history.store";
import { READING_STATUSES, useLibraryStore } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import { DownloadRequestsView } from "./DownloadRequestsView";
import { UnderlineFilters } from "./LibraryToolbar";
import { LibraryOverview } from "./LibraryOverview";
import { MyResearchList } from "./MyResearchList";
import { isSameView, viewKey, type LibraryView } from "./ReadingPanel";
import type { ResearchFilter } from "./researchSections";
import { isRequestTimeout } from "@/api/requestPolicy";
import { SavedCallsSection } from "@/features/opportunities/SavedCallsSection";
import { SavedView } from "./SavedView";
import { useLibrary, useReadingHistory } from "./useLibrary";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { PUBLISH_PARAM, usePublishHref } from "@/features/publish/publishLink";

type Tab = "overview" | "research" | "saved" | "calls" | "downloads";
type SavedViewKind = Exclude<LibraryView, { kind: "research" }>;

/** Every tab, in order. `reader`: every reader has it, author or not (IR-743, IR-766). */
const AUTHOR_TABS: { value: Tab; label: string; reader: boolean }[] = [
  { value: "overview",  label: "Overview",          reader: false },
  // Title Case at the owner's direction (IR-1324), an exception to DESIGN.md's sentence case.
  { value: "research",  label: "My Submissions",    reader: false },
  { value: "saved",     label: "Saved Papers",      reader: true },
  // Calls for papers the reader saved, apart from papers (IR-766).
  { value: "calls",     label: "Saved Calls",       reader: true },
  { value: "downloads", label: "Download Requests", reader: true },
];
const READER_TABS = AUTHOR_TABS.filter((t) => t.reader);

type StatusFilter = "all" | ReadingStatus;
const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All saved" },
  ...READING_STATUSES.map((s) => ({ value: s.value as StatusFilter, label: s.label })),
];

const ALL_SAVED: SavedViewKind = { kind: "saved" };

function tabFromSection(section: string | null, canAuthor: boolean): Tab {
  const readerTab = READER_TABS.find((t) => t.value === section);
  if (readerTab) return readerTab.value;
  if (!canAuthor) return "saved";
  return section === "research" ? section : "overview";
}

/**
 * My Library (IR-410; spec §4.9 as amended 2026-10-11): an author's own
 * research and their saved reading, in tabs: Overview, My submissions, Saved
 * papers, Saved calls (IR-766) and Download requests. A reader who cannot
 * author sees Saved papers, Saved calls and Download requests (IR-743).
 *
 * Owned research comes from `/records/mine/`; saves, Reading status (IR-566,
 * ADR-044), the reader's own folders (IR-572, ADR-070) and reading history
 * (IR-756) from the account. `?section=research` (where
 * the retired `/workspace` lands), `?section=saved`, `?section=calls` and
 * `?section=downloads` pick a tab.
 */
export default function MyLibraryPage() {
  // The server's `can_author` (IR-1096), not the role name.
  const mayAuthor = useAuthStore((state) => canAuthor(state.user));
  const [searchParams, setSearchParams] = useSearchParams();
  const section = searchParams.get("section");
  // Publish opens over this page (IR-1258), so its links keep the tab.
  const publishHref = usePublishHref();
  const publishing = searchParams.get(PUBLISH_PARAM) != null;

  const tab: Tab = tabFromSection(section, mayAuthor);
  const tabs = mayAuthor ? AUTHOR_TABS : READER_TABS;
  const [savedView, setSavedView] = useState<SavedViewKind>(ALL_SAVED);
  const [researchFilter, setResearchFilter] = useState<ResearchFilter>("all");
  useReadingHistory();
  const history = useHistoryStore((s) => s.items);

  const { load: libraryLoad, interrupted: libraryInterrupted, retry: retryLibrary } = useLibrary();
  const library = useLibraryStore((s) => s.items);
  const folders = useLibraryStore((s) => s.folders);
  const folderLimit = useLibraryStore((s) => s.folderLimit);
  const failure = useLibraryStore((s) => s.failure);
  const unsave = useLibraryStore((s) => s.unsave);
  const createFolder = useLibraryStore((s) => s.createFolder);
  const renameFolder = useLibraryStore((s) => s.renameFolder);
  const deleteFolder = useLibraryStore((s) => s.deleteFolder);
  const removeFromFolder = useLibraryStore((s) => s.removeFromFolder);
  const dismissFailure = useLibraryStore((s) => s.dismissFailure);

  const [research, setResearch] = useState<MyResearchItem[]>([]);
  const dropDeleted = (id: number) => setResearch((items) => items.filter((item) => item.id !== id));
  const [loading, setLoading] = useState(mayAuthor);
  const [failed, setFailed] = useState(false);
  const [interrupted, setInterrupted] = useState(false);

  const loadResearch = useCallback(async ({ quiet = false }: { quiet?: boolean } = {}) => {
    // Quiet: the list stays on screen while it is read again.
    if (!quiet) setLoading(true);
    setFailed(false);
    setInterrupted(false);
    try {
      const { data } = await recordsApi.mine();
      setResearch(Array.isArray(data) ? data : []);
    } catch (error) {
      setFailed(true);
      setInterrupted(isRequestTimeout(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mayAuthor) void loadResearch();
  }, [mayAuthor, loadResearch]);
  // Live updates (ADR-073): the author's own papers, reloaded quietly.
  useLiveRefresh(["library"], () => { void loadResearch(); }, mayAuthor);
  // Closing Publish leaves the reader here (IR-1258), so the list is read
  // again: the draft may have been edited, submitted or deleted in it.
  const wasPublishing = useRef(publishing);
  useEffect(() => {
    if (wasPublishing.current && !publishing && mayAuthor) void loadResearch({ quiet: true });
    wasPublishing.current = publishing;
  }, [publishing, mayAuthor, loadResearch]);

  const selectTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    if (next === tabs[0].value) params.delete("section");
    else params.set("section", next);
    setSearchParams(params, { replace: true });
  };

  const openSubmissions = (filter: ResearchFilter) => {
    setResearchFilter(filter);
    selectTab("research");
  };

  const removeFromView = (ids: number[]) => {
    if (savedView.kind === "folder") {
      // Out of this folder only: the paper stays saved (IR-572).
      const folderId = savedView.id;
      ids.forEach((id) => void removeFromFolder(folderId, id));
    } else if (savedView.kind === "saved" || savedView.kind === "status") {
      // Unsaving takes a paper out of the library, folders included.
      ids.forEach((id) => void unsave(id));
    }
  };

  const statusFilter: StatusFilter | null = savedView.kind === "saved"
    ? "all"
    : savedView.kind === "status" ? savedView.status : null;

  /* Tabs follow the ARIA tabs pattern: arrows move between them. */
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ overview: null, research: null, saved: null, calls: null, downloads: null });
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const i = tabs.findIndex((t) => t.value === tab);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = tabs[(i + step + tabs.length) % tabs.length].value;
    selectTab(next);
    tabRefs.current[next]?.focus();
  };

  const savedPanel = (
    <div>
      {failure && (
        <p role="alert" className="mb-3 flex flex-wrap items-center gap-x-2 rounded-card border border-stone-300 bg-surface px-3 py-2 text-small text-brand">
          {failure.message}
          <button type="button" onClick={dismissFailure} className={cn("ml-auto rounded-control px-2 py-1 font-semibold hover:bg-stone-100", FOCUS_RING)}>
            Dismiss
          </button>
        </p>
      )}
      <div key={viewKey(savedView)} className="motion-safe:animate-fade-in">
        <SavedView
          view={savedView}
          folders={folders}
          library={library}
          libraryLoad={libraryLoad}
          libraryInterrupted={libraryInterrupted}
          onRetryLibrary={retryLibrary}
          onRemove={removeFromView}
          onRename={(id, name) => void renameFolder(id, name)}
          onDelete={(id) => {
            void deleteFolder(id);
            if (isSameView(savedView, { kind: "folder", id })) setSavedView(ALL_SAVED);
          }}
          folderLimit={folderLimit}
          onOpenView={setSavedView}
          onCreateFolder={(name) => void createFolder(name)}
          // History opens from the Overview's Recently opened; a reader with
          // no Overview gets the link on the folders (ADR-044 amendment 2026-11-24).
          onManageHistory={mayAuthor ? undefined : () => setSavedView({ kind: "history" })}
          historyBack={mayAuthor ? { label: "Back to Overview", onClick: () => { setSavedView(ALL_SAVED); selectTab("overview"); } } : undefined}
          filters={
            <UnderlineFilters
              label="Reading status"
              options={STATUS_FILTERS}
              value={statusFilter}
              onChange={(value) => setSavedView(value === "all" ? ALL_SAVED : { kind: "status", status: value })}
            />
          }
        />
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="My Library"
        description={mayAuthor ? "Keep your research moving, from submission to the shelf." : "Papers you saved and opened, and your download requests."}
        actions={mayAuthor && (
          <Link to={publishHref("new")} className={cn(PILL_PRIMARY, FOCUS_RING)}>
            <i className="fas fa-plus text-label" aria-hidden />
            Publish
          </Link>
        )}
      />

      {/* A faint rule under the tabs keeps them apart from the page (IR-1325), like the cards' heading rules. */}
      <div className="mb-section-lg border-b border-stone-200 pb-2">
      <div role="tablist" aria-label="My Library" className="-mx-1 flex gap-1 overflow-x-auto overflow-y-hidden p-1 scrollbar-none">
        {tabs.map((t) => {
          const current = t.value === tab;
          return (
            <button
              key={t.value}
              ref={(el) => { tabRefs.current[t.value] = el; }}
              type="button"
              role="tab"
              id={`library-tab-${t.value}`}
              aria-selected={current}
              aria-controls={`library-panel-${t.value}`}
              tabIndex={current ? 0 : -1}
              onClick={() => selectTab(t.value)}
              onKeyDown={onTabKey}
              className={cn(
                // The current tab is filled maroon (IR-1324, the owner's choice B), with
                // the sidebar highlight's and search field's corner (IR-1329).
                "min-h-10 shrink-0 whitespace-nowrap rounded-control px-4 text-small font-semibold",
                COLOUR_TRANSITION,
                FOCUS_RING,
                current ? "bg-brand text-white" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      </div>

      <div
        key={tab}
        role="tabpanel"
        id={`library-panel-${tab}`}
        aria-labelledby={`library-tab-${tab}`}
        className="motion-safe:animate-fade-in"
      >
        {mayAuthor && tab === "overview" && (
          <LibraryOverview
            research={research}
            loading={loading}
            failed={failed}
            interrupted={interrupted}
            onRetry={() => void loadResearch()}
            history={history}
            onOpenSubmissions={openSubmissions}
            onManageHistory={() => {
              setSavedView({ kind: "history" });
              selectTab("saved");
            }}
            onDeleted={dropDeleted}
          />
        )}
        {mayAuthor && tab === "research" && (
          <MyResearchList
            items={research}
            loading={loading}
            failed={failed}
            interrupted={interrupted}
            onRetry={() => void loadResearch()}
            filter={researchFilter}
            onFilterChange={setResearchFilter}
            onDeleted={dropDeleted}
          />
        )}
        {tab === "saved" && savedPanel}
        {tab === "calls" && <SavedCallsSection />}
        {tab === "downloads" && <DownloadRequestsView />}
      </div>
    </div>
  );
}
