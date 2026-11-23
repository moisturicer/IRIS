import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { isRequestTimeout } from "@/api/requestPolicy";
import { FOCUS_RING } from "@/components/ui/interaction";
import { SavedCallsSection } from "@/features/opportunities/SavedCallsSection";
import { PUBLISH_PARAM, usePublishHref } from "@/features/publish/publishLink";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { canAuthor } from "@/lib/access";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useLibraryStore } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import { DownloadRequestsView } from "./DownloadRequestsView";
import { LibraryRail } from "./LibraryRail";
import { isReadingView, paramsForView, viewFromParams, viewKey, type LibraryView } from "./libraryViews";
import { MyResearchList } from "./MyResearchList";
import type { ResearchFilter } from "./researchSections";
import { SavedView } from "./SavedView";
import { useLibrary, useReadingHistory } from "./useLibrary";
import { ViewHeader } from "./ViewHeader";

const RESEARCH_HEADINGS: Record<ResearchFilter, { title: string; note: string }> = {
  all:      { title: "All research", note: "Everything you wrote, what waits on you first." },
  waiting:  { title: "Needs your action", note: "A reviewer needs something from you before review can go on." },
  review:   { title: "In review", note: "With your Adviser or an office. Nothing for you to do yet." },
  drafts:   { title: "Drafts", note: "Not yet submitted." },
  finished: { title: "Finished", note: "Accepted, published, kept unlisted or archived." },
};

const PANE_KEY = "iris-library-pane";

function readPaneOpen(): boolean {
  try { return localStorage.getItem(PANE_KEY) !== "closed"; } catch { return true; }
}

function savePaneOpen(open: boolean) {
  try { localStorage.setItem(PANE_KEY, open ? "open" : "closed"); } catch { /* per-browser convenience */ }
}

/**
 * My Library (IR-410; spec §4.9 as amended 2026-10-11; IR-1311): an author's
 * own research and everyone's saved reading, as one list chosen from one rail.
 * A reader who cannot author has the reading, folder and request lists only
 * (IR-743, IR-1096).
 *
 * Owned research comes from `/records/mine/`; saves, Reading status (IR-566,
 * ADR-044), the reader's own folders (IR-572, ADR-070) and reading history
 * (IR-756) from the account. The list is in the address (`?section=`, and
 * `&folder=` for a folder), and every value the tabs used still opens the same
 * list: `research` (where the retired `/workspace` lands), `saved`, `calls`
 * and `downloads`.
 */
export default function MyLibraryPage() {
  // The server's `can_author` (IR-1096), not the role name.
  const mayAuthor = useAuthStore((state) => canAuthor(state.user));
  const [searchParams, setSearchParams] = useSearchParams();
  const view = viewFromParams(searchParams, mayAuthor);
  // Publish opens over this page (IR-1258), so its links keep the list.
  const publishHref = usePublishHref();
  const publishing = searchParams.get(PUBLISH_PARAM) != null;
  useReadingHistory();

  const { load: libraryLoad, interrupted: libraryInterrupted, retry: retryLibrary } = useLibrary();
  const library = useLibraryStore((s) => s.items);
  const folders = useLibraryStore((s) => s.folders);
  const folderLimit = useLibraryStore((s) => s.folderLimit);
  const failure = useLibraryStore((s) => s.failure);
  const save = useLibraryStore((s) => s.save);
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

  const waiting = useMemo(
    () => research.filter((item) => item.submitter_status.waiting_on_you.length > 0).length,
    [research],
  );

  const [paneOpen, setPaneOpen] = useState(readPaneOpen);
  const togglePane = () => {
    setPaneOpen(!paneOpen);
    savePaneOpen(!paneOpen);
  };

  const select = (next: LibraryView) => setSearchParams(paramsForView(searchParams, next, mayAuthor), { replace: true });

  const removeFromView = (ids: number[]) => {
    if (view.kind === "folder") {
      // Out of this folder only: the paper stays saved (IR-572).
      ids.forEach((id) => void removeFromFolder(view.id, id));
    } else {
      // Unsaving takes a paper out of the library, folders included.
      ids.forEach((id) => void unsave(id));
    }
  };

  let content;
  if (view.kind === "research") {
    const heading = RESEARCH_HEADINGS[view.filter];
    content = (
      <>
        <ViewHeader title={heading.title} name={heading.title} note={heading.note} />
        <MyResearchList
          items={research}
          loading={loading}
          failed={failed}
          interrupted={interrupted}
          onRetry={() => void loadResearch()}
          filter={view.filter}
          onDeleted={dropDeleted}
        />
      </>
    );
  } else if (isReadingView(view)) {
    content = (
      <SavedView
        view={view}
        folders={folders}
        library={library}
        libraryLoad={libraryLoad}
        libraryInterrupted={libraryInterrupted}
        onRetryLibrary={retryLibrary}
        onRemove={removeFromView}
        onRename={(id, name) => void renameFolder(id, name)}
        onDelete={(id) => {
          void deleteFolder(id);
          if (view.kind === "folder" && view.id === id) select({ kind: "saved" });
        }}
        onSetStatus={(record, status) => void save(record.id, status, record)}
      />
    );
  } else if (view.kind === "calls") {
    content = (
      <>
        <ViewHeader title="Saved calls" name="Saved calls" note="Calls for papers you bookmarked in Calls & Conferences." />
        <SavedCallsSection />
      </>
    );
  } else {
    content = (
      <>
        <ViewHeader title="Download requests" name="Download requests" note="Copies you asked RDCO for, and each answer." />
        <DownloadRequestsView />
      </>
    );
  }

  return (
    <div className="[container-type:inline-size] [container-name:library]">
      <div
        className={cn(
          "grid library-wide:min-h-screen library-wide:transition-[grid-template-columns] library-wide:duration-200 library-wide:ease-out motion-reduce:transition-none",
          paneOpen ? "library-wide:grid-cols-[17.5rem_minmax(0,1fr)]" : "library-wide:grid-cols-[3.75rem_minmax(0,1fr)]",
        )}
      >
        {/* Docked like Ask IRIS's conversations: the page's name, what it is for, then its lists. */}
        <aside className="min-w-0 overflow-hidden border-b border-stone-200 bg-stone-50 library-wide:sticky library-wide:top-0 library-wide:h-screen library-wide:border-b-0 library-wide:border-r">
          {/* Its own width, so the lists do not reflow while the column animates. */}
          <div className={cn("flex h-full min-h-0 flex-col", paneOpen ? "library-wide:w-[17.5rem]" : "library-wide:w-[calc(3.75rem-1px)]")}>
            <LibraryRail
              view={view}
              onSelect={select}
              mayAuthor={mayAuthor}
              waiting={waiting}
              folders={folders}
              folderLimit={folderLimit}
              publishHref={mayAuthor ? publishHref("new") : undefined}
              title="My Library"
              collapsed={!paneOpen}
              onToggle={togglePane}
              onCreateFolder={(name) => {
                void createFolder(name).then((made) => {
                  if (made) select({ kind: "folder", id: made.id });
                });
              }}
            />
          </div>
        </aside>

        <div className="min-w-0 p-4 sm:p-7">
          {failure && (
            <p role="alert" className="mb-section flex flex-wrap items-center gap-x-2 rounded-card border border-stone-300 bg-surface px-3 py-2 text-small text-brand">
              {failure.message}
              <button type="button" onClick={dismissFailure} className={cn("ml-auto rounded-control px-2 py-1 font-semibold hover:bg-stone-100", FOCUS_RING)}>
                Dismiss
              </button>
            </p>
          )}
          <div key={viewKey(view)} className="motion-safe:animate-fade-in">{content}</div>
        </div>
      </div>
    </div>
  );
}
