import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
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
import { useLibraryStore } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import { MyResearchList } from "./MyResearchList";
import { ReadingPanel, isSameView, viewKey, type LibraryView } from "./ReadingPanel";
import { SavedView } from "./SavedView";
import { useLibrary } from "./useLibrary";

const ALL_SAVED: LibraryView = { kind: "saved" };

/**
 * My Library (IR-410; spec §4.9 as amended 2026-10-11): an author's own
 * research, grouped by who has each record now, beside their saved reading.
 *
 * Owned research comes from `/records/mine/`, and saves and Reading status
 * from the account library (IR-566, ADR-044). The reader's own folders and
 * history still live in this browser and say so. Authors open on their
 * research, everyone else on All saved. `?section=research` (where the
 * retired `/workspace` lands) and `?section=saved` pick one explicitly.
 */
export default function MyLibraryPage() {
  const role = useAuthStore((state) => state.user?.role_name);
  const canAuthor = canAccess(role as RoleName | undefined, "submit");
  const [searchParams] = useSearchParams();
  const section = searchParams.get("section");

  const [view, setView] = useState<LibraryView>(() =>
    canAuthor && section !== "saved" ? { kind: "research" } : ALL_SAVED,
  );
  const [collections, setCollections] = useState<Collection[]>(() => getCollections());
  const [history, setHistory] = useState<ReadingVisit[]>(() => getReadingHistory());

  const { load: libraryLoad, retry: retryLibrary } = useLibrary();
  const library = useLibraryStore((s) => s.items);
  const failure = useLibraryStore((s) => s.failure);
  const unsave = useLibraryStore((s) => s.unsave);
  const dismissFailure = useLibraryStore((s) => s.dismissFailure);

  const [research, setResearch] = useState<MyResearchItem[]>([]);
  const [loading, setLoading] = useState(canAuthor);
  const [failed, setFailed] = useState(false);

  // A bookmark or the retired Workspace URL may arrive while this page is mounted.
  useEffect(() => {
    if (section === "research" && canAuthor) setView({ kind: "research" });
    if (section === "saved") setView(ALL_SAVED);
  }, [section, canAuthor]);

  const loadResearch = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await recordsApi.mine();
      setResearch(Array.isArray(data) ? data : []);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canAuthor) void loadResearch();
  }, [canAuthor, loadResearch]);

  const removeFromView = (ids: number[]) => {
    if (view.kind === "folder") {
      setCollections(removeFromCollections(collections, ids, view.id));
    } else if (view.kind === "saved" || view.kind === "status") {
      // Unsaving takes a paper out of the library, folders included.
      setCollections(removeFromCollections(collections, ids));
      ids.forEach((id) => void unsave(id));
    }
  };

  const showingResearch = view.kind === "research";

  return (
    <div>
      <PageHeader
        title="My Library"
        description={canAuthor ? "Where your research is, and what you are reading." : "Papers you saved and opened."}
        actions={canAuthor && (
          <>
            {showingResearch && (
              <a href="#your-reading" className={cn("rounded-lg px-3 py-2 text-small font-semibold text-stone-700 hover:bg-stone-100 lg:hidden", COLOUR_TRANSITION, FOCUS_RING)}>
                Your reading
              </a>
            )}
            <Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>
          </>
        )}
      />

      <div className="grid gap-section-lg lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
        <section key={viewKey(view)} className="min-w-0 motion-safe:animate-fade-in" aria-label={showingResearch ? "Your research" : "Saved reading"}>
          {!showingResearch && canAuthor && (
            <button
              type="button"
              onClick={() => setView({ kind: "research" })}
              className={cn("mb-3 inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-small font-semibold text-brand hover:bg-brand-50", COLOUR_TRANSITION, FOCUS_RING)}
            >
              <i className="fas fa-arrow-left text-label" aria-hidden />
              Back to your research
            </button>
          )}
          {failure && !showingResearch && (
            <p role="alert" className="mb-3 flex flex-wrap items-center gap-x-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-small text-brand">
              {failure.message}
              <button type="button" onClick={dismissFailure} className={cn("ml-auto rounded-md px-2 py-1 font-semibold hover:bg-brand-100", FOCUS_RING)}>
                Dismiss
              </button>
            </p>
          )}
          {showingResearch ? (
            <MyResearchList items={research} loading={loading} failed={failed} onRetry={() => void loadResearch()} />
          ) : (
            <SavedView
              view={view}
              collections={collections}
              history={history}
              library={library}
              libraryLoad={libraryLoad}
              onRetryLibrary={retryLibrary}
              onRemove={removeFromView}
              onRename={(id, name) => setCollections(renameCollection(collections, id, name))}
              onDelete={(id) => {
                setCollections(deleteCollection(collections, id));
                if (isSameView(view, { kind: "folder", id })) setView(canAuthor ? { kind: "research" } : ALL_SAVED);
              }}
              onClearHistory={() => { clearReadingHistory(); setHistory([]); }}
            />
          )}
        </section>

        {/* Sticks 24px from the top of the window: there is no app header above
            it since IR-519 (IR-351: sticky works because AppShell is not a
            scroll container). */}
        <aside className="lg:sticky lg:top-6">
          <ReadingPanel
            collections={collections}
            history={history}
            view={view}
            onViewChange={setView}
            onCreate={(name) => setCollections(addCollection(collections, name))}
          />
        </aside>
      </div>
    </div>
  );
}
