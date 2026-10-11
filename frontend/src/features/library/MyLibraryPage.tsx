import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
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
  getStarredIds,
  removeFromAllCollections,
  renameCollection,
  toggleStarred,
  type Collection,
  type ReadingVisit,
} from "@/lib/recordLibrary";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { MyResearchItem } from "@/types/records";

import { MyResearchList } from "./MyResearchList";
import { ReadingPanel, isSameView, type LibraryView } from "./ReadingPanel";
import { SavedView } from "./SavedView";

const WANT_TO_READ: LibraryView = { kind: "folder", id: "want-to-read" };

/**
 * My Library (IR-410; spec §4.9 as amended 2026-10-11): an author's own
 * research, grouped by who has each record now, beside this browser's saved
 * reading.
 *
 * Owned research comes from `/records/mine/` and is account-backed; saved
 * folders, likes and history live in this browser and say so. Authors open on
 * their research, everyone else on Want to read. `?section=research` (where
 * the retired `/workspace` lands) and `?section=saved` pick one explicitly.
 */
export default function MyLibraryPage() {
  const role = useAuthStore((state) => state.user?.role_name);
  const canAuthor = canAccess(role as RoleName | undefined, "submit");
  const [searchParams] = useSearchParams();
  const section = searchParams.get("section");

  const [view, setView] = useState<LibraryView>(() =>
    canAuthor && section !== "saved" ? { kind: "research" } : WANT_TO_READ,
  );
  const [collections, setCollections] = useState<Collection[]>(() => getCollections());
  const [starredIds, setStarredIds] = useState<number[]>(() => getStarredIds());
  const [history, setHistory] = useState<ReadingVisit[]>(() => getReadingHistory());

  const [research, setResearch] = useState<MyResearchItem[]>([]);
  const [loading, setLoading] = useState(canAuthor);
  const [failed, setFailed] = useState(false);

  // A bookmark or the retired Workspace URL may arrive while this page is mounted.
  useEffect(() => {
    if (section === "research" && canAuthor) setView({ kind: "research" });
    if (section === "saved") setView(WANT_TO_READ);
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
    if (view.kind === "starred") {
      ids.forEach((id) => toggleStarred(id));
      setStarredIds(getStarredIds());
    } else if (view.kind === "folder") {
      setCollections(removeFromAllCollections(collections, ids));
    }
  };

  const showingResearch = view.kind === "research";

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-section-lg flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-display font-semibold text-stone-900">My Library</h1>
          <p className="mt-1 text-body text-stone-600">
            {canAuthor ? "Where your research is, and what you are reading." : "Papers you saved, liked and opened."}
          </p>
        </div>
        {canAuthor && (
          <div className="flex items-center gap-2">
            {showingResearch && (
              <a href="#your-reading" className={cn("rounded-lg px-3 py-2 text-small font-semibold text-stone-700 hover:bg-stone-100 lg:hidden", COLOUR_TRANSITION, FOCUS_RING)}>
                Your reading
              </a>
            )}
            <Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>
          </div>
        )}
      </header>

      <div className="grid gap-section-lg lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
        <section key={view.kind === "folder" ? `folder:${view.id}` : view.kind} className="min-w-0 motion-safe:animate-fade-in" aria-label={showingResearch ? "Your research" : "Saved reading"}>
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
          {showingResearch ? (
            <MyResearchList items={research} loading={loading} failed={failed} onRetry={() => void loadResearch()} />
          ) : (
            <SavedView
              view={view}
              collections={collections}
              starredIds={starredIds}
              history={history}
              onRemove={removeFromView}
              onToggleStar={(id) => { toggleStarred(id); setStarredIds(getStarredIds()); }}
              onRename={(id, name) => setCollections(renameCollection(collections, id, name))}
              onDelete={(id) => {
                setCollections(deleteCollection(collections, id));
                if (isSameView(view, { kind: "folder", id })) setView(canAuthor ? { kind: "research" } : WANT_TO_READ);
              }}
              onClearHistory={() => { clearReadingHistory(); setHistory([]); }}
            />
          )}
        </section>

        <aside className="lg:sticky lg:top-24">
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
