import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import {
  isStatusFolder,
  STATUS_FOLDER_ICONS,
  type Collection,
  type ReadingVisit,
  type StatusFolderId,
} from "@/lib/recordLibrary";
import { cn, formatDate } from "@/lib/utils";

/**
 * Which part of My Library the main column shows. `research` is the owner's
 * own records; the rest are this browser's saved reading. "folder" covers the
 * three reading-status folders and the reader's own folders alike: they
 * differ in how a record enters them, not in how they are read.
 */
export type LibraryView =
  | { kind: "research" }
  | { kind: "folder"; id: string }
  | { kind: "starred" }
  | { kind: "history" };

export function isSameView(a: LibraryView, b: LibraryView): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "folder" && b.kind === "folder") return a.id === b.id;
  return true;
}

interface ReadingPanelProps {
  collections: Collection[];
  history:     ReadingVisit[];
  view:        LibraryView;
  onViewChange: (view: LibraryView) => void;
  onCreate:    (name: string) => void;
}

/** How many recent papers the panel lists before pointing at History. */
const RECENT = 3;

/**
 * "Your reading": saved folders, liked papers and history, all stored in this
 * browser (IR-410). It stays beside the owner's research rather than behind a
 * tab, so saved reading is never hidden. Renaming and deleting a folder
 * happen in the folder's own view, not on hover here.
 */
export function ReadingPanel({ collections, history, view, onViewChange, onCreate }: ReadingPanelProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (creating) input.current?.focus();
  }, [creating]);

  const submit = () => {
    const trimmed = name.trim();
    if (trimmed) onCreate(trimmed);
    setName("");
    setCreating(false);
  };

  const item = (target: LibraryView, label: string, icon: string) => {
    const active = isSameView(view, target);
    return (
      <li key={target.kind === "folder" ? target.id : target.kind}>
        <button
          type="button"
          onClick={() => onViewChange(target)}
          aria-current={active ? "page" : undefined}
          className={cn(
            "flex w-full min-h-10 items-center gap-3 rounded-lg px-3 text-left text-small",
            COLOUR_TRANSITION,
            FOCUS_RING,
            active ? "bg-brand-50 font-semibold text-brand" : "text-stone-700 hover:bg-stone-50",
          )}
        >
          <i className={cn("fas w-4 text-center", icon, active ? "text-brand" : "text-stone-500")} aria-hidden />
          <span className="min-w-0 flex-1 truncate">{label}</span>
        </button>
      </li>
    );
  };

  const statusFolders = collections.filter((c) => isStatusFolder(c.id));
  const ownFolders = collections.filter((c) => !isStatusFolder(c.id));

  return (
    <section
      id="your-reading"
      aria-labelledby="your-reading-title"
      className="rounded-2xl border border-stone-200 bg-white p-card-compact md:p-card scroll-mt-24"
    >
      <h2 id="your-reading-title" className="font-display text-title font-semibold text-stone-900">
        Your reading
      </h2>
      <p className="mt-0.5 text-small text-stone-600">Saved in this browser only.</p>

      <ul className="mt-4 space-y-0.5" aria-label="Saved folders">
        {statusFolders.map((c) =>
          item({ kind: "folder", id: c.id }, c.name, STATUS_FOLDER_ICONS[c.id as StatusFolderId] ?? "fa-folder"),
        )}
        {ownFolders.map((c) => item({ kind: "folder", id: c.id }, c.name, "fa-folder"))}
        {item({ kind: "starred" }, "Liked papers", "fa-star")}
        {item({ kind: "history" }, "History", "fa-clock-rotate-left")}
      </ul>

      <div className="mt-2">
        {creating ? (
          <input
            ref={input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={submit}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") {
                setName("");
                setCreating(false);
              }
            }}
            aria-label="New folder name"
            placeholder="Folder name"
            className="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-small placeholder:text-stone-500 focus:border-brand focus:outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className={cn(
              "inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-small font-semibold text-brand hover:bg-brand-50",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <i className="fas fa-plus text-label" aria-hidden />
            New folder
          </button>
        )}
      </div>

      {history.length > 0 && (
        <div className="mt-5 border-t border-stone-100 pt-4">
          <h3 className="text-label font-semibold text-stone-600">Recently opened</h3>
          <ul className="mt-2 space-y-3">
            {history.slice(0, RECENT).map((visit) => (
              <li key={visit.recordId}>
                <Link
                  to={`/records/${visit.recordId}`}
                  className={cn(
                    "block rounded-sm font-display text-heading font-semibold leading-snug text-stone-900 hover:text-brand",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                  )}
                >
                  {visit.title}
                </Link>
                <p className="text-label text-stone-600">Opened {formatDate(visit.viewedAt)}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
