import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import type { SavedFeed } from "@/api/library";
import { Input } from "@/components/ui";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Modal } from "@/components/ui/Modal";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import { useFeedsStore } from "@/store/feeds.store";

import { feedCriteria, feedQueryOf, type DiscoverQuery, type FeedLabelOptions } from "./discoverQuery";

/**
 * "My feeds": a reader's private saved feeds, in one menu beside Discover's
 * tabs (IR-577). No new navigation entry, and nothing public.
 *
 * A feed is Discover's own query under a name, so saving takes the filters on
 * screen and opening hands the stored query back to the page, which puts it in
 * the URL. The rules the server enforces (the limit, unique names, at least one
 * criterion, values that still exist) are shown where they bite, in the words
 * the server sent, with what the reader typed kept on screen.
 *
 * Saving is offered on Latest and Trending only: both are catalogue queries.
 * For you is a personal ranking whose order is not a query, and it ignores the
 * search box, so a feed saved from it would reopen in a different order.
 */
interface MyFeedsProps {
  /** The query on screen, tab included. */
  query:        DiscoverQuery;
  /** How many papers the filters on screen match, once the list has loaded. */
  matchCount:   number | null;
  options:      FeedLabelOptions;
  /** The feed the page is showing, if any. */
  activeFeedId: number | null;
  onOpen:       (feed: SavedFeed) => void;
  /** After a delete, so the page can leave a feed that no longer exists. */
  onDeleted:    (id: number) => void;
}

type Dialog =
  | { kind: "save" }
  | { kind: "rename"; feed: SavedFeed }
  | { kind: "delete"; feed: SavedFeed }
  | null;

const NO_CRITERIA = "Choose at least one filter or keyword before saving a feed.";

export function MyFeeds({ query, matchCount, options, activeFeedId, onOpen, onDeleted }: MyFeedsProps) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [announcement, setAnnouncement] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const load = useFeedsStore((s) => s.load);
  const feeds = useFeedsStore((s) => s.feeds);
  const limit = useFeedsStore((s) => s.limit);
  const ensureLoaded = useFeedsStore((s) => s.ensureLoaded);

  // Reads when the store is empty, which is also true again after the account
  // changes, so the next reader's feeds are fetched and not left waiting.
  useEffect(() => { if (load === "idle") void ensureLoaded(); }, [load, ensureLoaded]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const choose = (next: Dialog) => { setOpen(false); setDialog(next); };
  const full = load === "ready" && feeds.length >= limit;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        className={cn("inline-flex h-11 items-center justify-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 text-small font-medium text-stone-700 hover:border-stone-400 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
      >
        <i className="fas fa-rss text-[12px]" aria-hidden />
        <span>My feeds</span>
        {feeds.length > 0 && <span className="text-stone-500" aria-hidden>{feeds.length}</span>}
      </button>
      {announcement && <p role="status" className="sr-only">{announcement}</p>}

      {open && (
        <div
          id={menuId}
          className="absolute left-0 top-full z-40 mt-1.5 w-72 max-w-[calc(100vw-2rem)] rounded-lg border border-stone-200/90 bg-white py-1.5 shadow-card-md"
        >
          {load === "error" && (
            <div role="alert" className="mx-3 my-1.5 text-small text-stone-700">
              <p>Your feeds could not be loaded right now.</p>
              <button type="button" onClick={() => void ensureLoaded(true)}
                className={cn("mt-1 font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
                Try again
              </button>
            </div>
          )}
          {(load === "loading" || load === "idle") && <p className="px-3 py-2 text-small text-stone-500">Loading your feeds…</p>}
          {load === "ready" && feeds.length === 0 && <p className="px-3 py-2 text-small text-stone-600">No saved feeds yet.</p>}
          {feeds.length > 0 && (
            <ul className="max-h-72 overflow-y-auto">
              {feeds.map((feed) => (
                <li key={feed.id} aria-label={feed.name} className="flex items-center gap-1 px-1.5">
                  <button
                    type="button"
                    aria-label={`Open ${feed.name}`}
                    aria-current={feed.id === activeFeedId ? "true" : undefined}
                    onClick={() => { setOpen(false); onOpen(feed); }}
                    className={cn("flex min-h-11 min-w-0 flex-1 flex-col items-start justify-center rounded-md px-2 text-left hover:bg-stone-50", FOCUS_RING)}
                  >
                    <span className={cn("max-w-full truncate text-small", feed.id === activeFeedId ? "font-semibold text-brand" : "text-stone-800")}>{feed.name}</span>
                    {Object.keys(feed.stale).length > 0 && <span className="text-2xs text-stone-600">Needs attention</span>}
                  </button>
                  <button type="button" aria-label={`Rename ${feed.name}`} onClick={() => choose({ kind: "rename", feed })}
                    className={cn("flex h-11 w-9 items-center justify-center rounded-md text-stone-600 hover:text-brand", FOCUS_RING)}>
                    <i className="fas fa-pen text-[11px]" aria-hidden />
                  </button>
                  <button type="button" aria-label={`Delete ${feed.name}`} onClick={() => choose({ kind: "delete", feed })}
                    className={cn("flex h-11 w-9 items-center justify-center rounded-md text-stone-600 hover:text-brand", FOCUS_RING)}>
                    <i className="fas fa-trash-can text-[11px]" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-1 border-t border-stone-200 px-3 pb-1.5 pt-2.5">
            {query.feed === "for_you" ? (
              <p className="text-small text-stone-600">
                To save these filters as a feed, switch to Latest or Trending.
              </p>
            ) : full ? (
              <p className="text-small text-stone-600">You have {limit} saved feeds. Delete one to save another.</p>
            ) : (
              <button type="button" onClick={() => choose({ kind: "save" })}
                className={cn("min-h-11 text-left text-small font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
                Save these filters as a feed…
              </button>
            )}
          </div>
        </div>
      )}

      {dialog?.kind === "save" && (
        <SaveFeedDialog
          query={query}
          matchCount={matchCount}
          options={options}
          onClose={() => setDialog(null)}
          onSaved={(feed) => {
            setDialog(null);
            setAnnouncement(`Saved “${feed.name}”. It is in My feeds.`);
            onOpen(feed);
          }}
        />
      )}
      {dialog?.kind === "rename" && (
        <RenameFeedDialog feed={dialog.feed} onClose={() => setDialog(null)}
          onRenamed={(feed) => { setDialog(null); setAnnouncement(`Renamed to “${feed.name}”.`); }} />
      )}
      {dialog?.kind === "delete" && (
        <DeleteFeedDialog feed={dialog.feed} onClose={() => setDialog(null)}
          onDeleted={(id) => { setDialog(null); setAnnouncement(`Deleted “${dialog.feed.name}”.`); onDeleted(id); }} />
      )}
    </div>
  );
}

const MAX_NAME_LENGTH = 60;

function SaveFeedDialog({ query, matchCount, options, onClose, onSaved }: {
  query: DiscoverQuery;
  matchCount: number | null;
  options: FeedLabelOptions;
  onClose: () => void;
  onSaved: (feed: SavedFeed) => void;
}) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const formId = useId();
  const create = useFeedsStore((s) => s.create);

  const stored = feedQueryOf(query);
  const criteria = feedCriteria(stored, options);
  // A sort alone is not a criterion: it would only reorder the whole catalogue.
  const hasCriteria = Object.keys(stored).some((key) => key !== "sort");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !hasCriteria || saving) return;
    setSaving(true);
    setError("");
    const result = await create(name.trim(), stored);
    setSaving(false);
    if (result.ok) onSaved(result.feed);
    else setError(result.message);
  };

  return (
    <Modal open onClose={onClose} title="Save these filters as a feed"
      footer={<div className="flex items-center justify-end gap-3">
        <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={onClose}>Cancel</button>
        <button type="submit" form={formId} className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={saving || !name.trim() || !hasCriteria}>
          {saving ? "Saving…" : "Save feed"}
        </button>
      </div>}>
      <form id={formId} onSubmit={(e) => void submit(e)} className="space-y-4 p-5">
        <Input label="Feed name" value={name} maxLength={MAX_NAME_LENGTH} autoFocus autoComplete="off"
          onChange={(e) => setName(e.target.value)} />
        {hasCriteria ? (
          <div>
            <p className="text-small font-semibold text-stone-800">Filters in this feed</p>
            <ul className="mt-1.5 space-y-1 text-small text-stone-700">
              {criteria.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className="mt-3 text-small text-stone-600">
              Papers match any one of the Areas or colleges chosen, and every other filter. Only papers you
              can read are listed, now and whenever you open the feed.
            </p>
            {matchCount !== null && (
              <p className="mt-2 text-small text-stone-700">
                {matchCount === 1 ? "1 paper matches" : `${matchCount} papers match`} right now.
              </p>
            )}
          </div>
        ) : (
          <p className="text-small text-stone-700">{NO_CRITERIA}</p>
        )}
        {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </form>
    </Modal>
  );
}

function RenameFeedDialog({ feed, onClose, onRenamed }: {
  feed: SavedFeed;
  onClose: () => void;
  onRenamed: (feed: SavedFeed) => void;
}) {
  const [name, setName] = useState(feed.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const formId = useId();
  const update = useFeedsStore((s) => s.update);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || saving) return;
    setSaving(true);
    setError("");
    // Only the name: renaming never touches the criteria, so a feed with a
    // value that no longer exists can still be renamed.
    const result = await update(feed.id, { name: name.trim() });
    setSaving(false);
    if (result.ok) onRenamed(result.feed);
    else setError(result.message);
  };

  return (
    <Modal open onClose={onClose} title="Rename feed"
      footer={<div className="flex items-center justify-end gap-3">
        <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={onClose}>Cancel</button>
        <button type="submit" form={formId} className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={saving || !name.trim()}>
          {saving ? "Saving…" : "Save name"}
        </button>
      </div>}>
      <form id={formId} onSubmit={(e) => void submit(e)} className="space-y-4 p-5">
        <Input label="Feed name" value={name} maxLength={MAX_NAME_LENGTH} autoFocus autoComplete="off"
          onChange={(e) => setName(e.target.value)} />
        {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </form>
    </Modal>
  );
}

function DeleteFeedDialog({ feed, onClose, onDeleted }: {
  feed: SavedFeed;
  onClose: () => void;
  onDeleted: (id: number) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const remove = useFeedsStore((s) => s.remove);

  const confirm = async () => {
    setDeleting(true);
    setError("");
    const result = await remove(feed.id);
    setDeleting(false);
    if (result.ok) onDeleted(feed.id);
    else setError(result.message);
  };

  return (
    <Modal open onClose={onClose} title="Delete this feed?"
      footer={<div className="flex items-center justify-end gap-3">
        <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={onClose}>Keep feed</button>
        <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={deleting} onClick={() => void confirm()}>
          {deleting ? "Deleting…" : "Delete feed"}
        </button>
      </div>}>
      <div className="space-y-3 p-5">
        <p className="text-small text-stone-700">
          Delete “{feed.name}”? This removes the feed only. No papers are affected, and your other feeds stay.
        </p>
        {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </div>
    </Modal>
  );
}
