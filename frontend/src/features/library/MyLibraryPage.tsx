import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import type { ReadingStatus } from "@/api/library";
import { canAccess } from "@/lib/access";
import type { RoleName } from "@/lib/constants";
import {
  addCollection,
  clearReadingHistory,
  deleteCollection,
  getCollections,
  getReadingHistory,
  removeFromCollections,
  renameCollection,
  type Collection,
  type ReadingVisit,
} from "@/lib/recordLibrary";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { READING_STATUSES, useLibraryStore } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import { DownloadRequestsView } from "./DownloadRequestsView";
import { FilterChips } from "./FilterChips";
import { LibraryOverview } from "./LibraryOverview";
import { MyResearchList } from "./MyResearchList";
import { FolderPicker, isSameView, viewKey, type LibraryView } from "./ReadingPanel";
import type { ResearchFilter } from "./researchSections";
import { isRequestTimeout } from "@/api/requestPolicy";
import { SavedView } from "./SavedView";
import { useLibrary } from "./useLibrary";

type Tab = "overview" | "research" | "saved" | "downloads";
type SavedViewKind = Exclude<LibraryView, { kind: "research" }>;

const AUTHOR_TABS: { value: Tab; label: string }[] = [
  { value: "overview",  label: "Overview" },
  { value: "research",  label: "My submissions" },
  { value: "saved",     label: "Saved papers" },
  { value: "downloads", label: "Download requests" },
];
/** Every reader has their saves and their download requests (IR-743). */
const READER_TABS = AUTHOR_TABS.filter((t) => t.value === "saved" || t.value === "downloads");

type StatusFilter = "all" | ReadingStatus;
const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All saved" },
  ...READING_STATUSES.map((s) => ({ value: s.value as StatusFilter, label: s.label })),
];

const ALL_SAVED: SavedViewKind = { kind: "saved" };

function tabFromSection(section: string | null, canAuthor: boolean): Tab {
  if (section === "saved" || section === "downloads") return section;
  if (!canAuthor) return "saved";
  return section === "research" ? section : "overview";
}

/**
 * My Library (IR-410; spec §4.9 as amended 2026-10-11): an author's own
 * research and their saved reading, in tabs: Overview, My submissions, Saved
 * papers and Download requests. A reader who cannot author sees Saved papers
 * and Download requests (IR-743).
 *
 * Owned research comes from `/records/mine/`, and saves and Reading status
 * from the account library (IR-566, ADR-044). The reader's own folders and
 * history still live in this browser and say so. `?section=research` (where
 * the retired `/workspace` lands), `?section=saved` and `?section=downloads`
 * pick a tab.
 */
export default function MyLibraryPage() {
  const role = useAuthStore((state) => state.user?.role_name);
  const canAuthor = canAccess(role as RoleName | undefined, "submit");
  const [searchParams, setSearchParams] = useSearchParams();
  const section = searchParams.get("section");

  const tab: Tab = tabFromSection(section, canAuthor);
  const tabs = canAuthor ? AUTHOR_TABS : READER_TABS;
  const [savedView, setSavedView] = useState<SavedViewKind>(ALL_SAVED);
  const [researchFilter, setResearchFilter] = useState<ResearchFilter>("all");
  const [collections, setCollections] = useState<Collection[]>(() => getCollections());
  const [history, setHistory] = useState<ReadingVisit[]>(() => getReadingHistory());

  const { load: libraryLoad, interrupted: libraryInterrupted, retry: retryLibrary } = useLibrary();
  const library = useLibraryStore((s) => s.items);
  const failure = useLibraryStore((s) => s.failure);
  const unsave = useLibraryStore((s) => s.unsave);
  const dismissFailure = useLibraryStore((s) => s.dismissFailure);

  const [research, setResearch] = useState<MyResearchItem[]>([]);
  const [loading, setLoading] = useState(canAuthor);
  const [failed, setFailed] = useState(false);
  const [interrupted, setInterrupted] = useState(false);

  const loadResearch = useCallback(async () => {
    setLoading(true);
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
    if (canAuthor) void loadResearch();
  }, [canAuthor, loadResearch]);

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

  const openSaved = (view: LibraryView) => {
    if (view.kind !== "research") setSavedView(view);
    selectTab("saved");
  };

  const removeFromView = (ids: number[]) => {
    if (savedView.kind === "folder") {
      setCollections(removeFromCollections(collections, ids, savedView.id));
    } else if (savedView.kind === "saved" || savedView.kind === "status") {
      // Unsaving takes a paper out of the library, folders included.
      setCollections(removeFromCollections(collections, ids));
      ids.forEach((id) => void unsave(id));
    }
  };

  const statusFilter: StatusFilter | null = savedView.kind === "saved"
    ? "all"
    : savedView.kind === "status" ? savedView.status : null;

  /* Tabs follow the ARIA tabs pattern: arrows move between them. */
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ overview: null, research: null, saved: null, downloads: null });
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
        <p role="alert" className="mb-3 flex flex-wrap items-center gap-x-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-small text-brand">
          {failure.message}
          <button type="button" onClick={dismissFailure} className={cn("ml-auto rounded-md px-2 py-1 font-semibold hover:bg-brand-100", FOCUS_RING)}>
            Dismiss
          </button>
        </p>
      )}
      <div key={viewKey(savedView)} className="motion-safe:animate-fade-in">
        <SavedView
          view={savedView}
          collections={collections}
          history={history}
          library={library}
          libraryLoad={libraryLoad}
          libraryInterrupted={libraryInterrupted}
          onRetryLibrary={retryLibrary}
          onRemove={removeFromView}
          onRename={(id, name) => setCollections(renameCollection(collections, id, name))}
          onDelete={(id) => {
            setCollections(deleteCollection(collections, id));
            if (isSameView(savedView, { kind: "folder", id })) setSavedView(ALL_SAVED);
          }}
          onClearHistory={() => { clearReadingHistory(); setHistory([]); }}
          folderControl={
            <FolderPicker
              collections={collections}
              view={savedView}
              onViewChange={(view) => { if (view.kind !== "research") setSavedView(view); }}
              onCreate={(name) => {
                const next = addCollection(collections, name);
                setCollections(next);
                const made = next.find((c) => !collections.some((old) => old.id === c.id));
                if (made) setSavedView({ kind: "folder", id: made.id });
              }}
            />
          }
          filters={
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <FilterChips
                label="Reading status"
                options={STATUS_FILTERS}
                value={statusFilter}
                onChange={(value) => setSavedView(value === "all" ? ALL_SAVED : { kind: "status", status: value })}
              />
              <p className="text-label text-stone-500">
                Saves follow your account. Folders stay in this browser.
              </p>
            </div>
          }
        />
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="My Library"
        description={canAuthor ? "Keep your research moving, from submission to the shelf." : "Papers you saved and opened, and your download requests."}
        actions={canAuthor && (
          <Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>
            <i className="fas fa-plus text-label" aria-hidden />
            Publish
          </Link>
        )}
      />

      <div role="tablist" aria-label="My Library" className="mb-section-lg flex gap-1 overflow-x-auto overflow-y-hidden border-b border-stone-200">
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
                "relative min-h-11 shrink-0 whitespace-nowrap rounded-t-lg px-3 text-small font-semibold",
                "after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:content-['']",
                COLOUR_TRANSITION,
                FOCUS_RING,
                current ? "text-brand after:bg-brand" : "text-stone-600 hover:text-stone-900 after:bg-transparent",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        key={tab}
        role="tabpanel"
        id={`library-panel-${tab}`}
        aria-labelledby={`library-tab-${tab}`}
        className="motion-safe:animate-fade-in"
      >
        {canAuthor && tab === "overview" && (
          <LibraryOverview
            research={research}
            loading={loading}
            failed={failed}
            interrupted={interrupted}
            onRetry={() => void loadResearch()}
            library={library}
            history={history}
            collections={collections}
            onOpenSubmissions={openSubmissions}
            onOpenSaved={openSaved}
          />
        )}
        {canAuthor && tab === "research" && (
          <MyResearchList
            items={research}
            loading={loading}
            failed={failed}
            interrupted={interrupted}
            onRetry={() => void loadResearch()}
            filter={researchFilter}
            onFilterChange={setResearchFilter}
          />
        )}
        {tab === "saved" && savedPanel}
        {tab === "downloads" && <DownloadRequestsView />}
      </div>
    </div>
  );
}
