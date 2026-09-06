import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  isStatusFolder,
  STATUS_FOLDER_ICONS,
  type Collection,
  type StatusFolderId,
} from "@/lib/recordLibrary";
import { cn } from "@/lib/utils";

/**
 * Which slice of the library the main column is showing.
 *
 * "folder" covers both the three reading-status folders and custom topics —
 * they differ in how a record enters them, not in how they are read.
 */
export type LibraryView =
  | { kind: "folder"; id: string }
  | { kind: "starred" }
  | { kind: "history" };

export function isSameView(a: LibraryView, b: LibraryView): boolean {
  if (a.kind !== b.kind) return false;
  return a.kind === "folder" && b.kind === "folder" ? a.id === b.id : true;
}

interface LibraryFolderRailProps {
  collections: Collection[];
  view: LibraryView;
  onViewChange: (view: LibraryView) => void;
  onCreate: (name: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  starredCount: number;
  historyCount: number;
  /** Records the signed-in user owns. `null` until it loads. */
  disclosureCount: number | null;
  onCollapse: () => void;
}

export function LibraryFolderRail({
  collections,
  view,
  onViewChange,
  onCreate,
  onRename,
  onDelete,
  starredCount,
  historyCount,
  disclosureCount,
  onCollapse,
}: LibraryFolderRailProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const createRef = useRef<HTMLInputElement>(null);
  const renameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (creating) createRef.current?.focus();
  }, [creating]);

  useEffect(() => {
    if (renamingId) renameRef.current?.select();
  }, [renamingId]);

  const statusFolders = collections.filter((c) => isStatusFolder(c.id));
  const topicFolders = collections.filter((c) => !isStatusFolder(c.id));

  const submitCreate = () => {
    const name = newName.trim();
    if (name) onCreate(name);
    setNewName("");
    setCreating(false);
  };

  const submitRename = (id: string) => {
    const name = renameValue.trim();
    if (name) onRename(id, name);
    setRenamingId(null);
  };

  const renderFolder = (collection: Collection, icon: string) => {
    const active = view.kind === "folder" && view.id === collection.id;
    const removable = !isStatusFolder(collection.id);

    if (renamingId === collection.id) {
      return (
        <li key={collection.id} className="px-2">
          <input
            ref={renameRef}
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={() => submitRename(collection.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitRename(collection.id);
              if (e.key === "Escape") setRenamingId(null);
            }}
            aria-label={`Rename ${collection.name}`}
            className="w-full px-2.5 py-1.5 bg-white border border-brand/40 rounded-lg text-[13px] outline-none"
          />
        </li>
      );
    }

    return (
      <li key={collection.id} className="group/folder relative px-2">
        <button
          type="button"
          onClick={() => onViewChange({ kind: "folder", id: collection.id })}
          aria-current={active ? "true" : undefined}
          className={cn(
            "w-full flex items-center gap-2.5 pl-3 pr-2 py-2 rounded-lg text-[13px] transition-colors text-left",
            active
              ? "bg-brand-50 text-brand font-semibold"
              : "text-stone-600 hover:bg-stone-50",
          )}
        >
          <i
            className={cn("fas", icon, "text-[13px] shrink-0", active ? "text-brand" : "text-stone-400")} aria-hidden />
          <span className="truncate flex-1">{collection.name}</span>
          <span
            className={cn(
              "shrink-0 min-w-[20px] px-1.5 py-0.5 rounded text-[10px] font-bold text-center",
              active ? "bg-white text-brand" : "bg-stone-100 text-stone-500",
              // The row's own controls take this space on hover.
              removable && "group-hover/folder:invisible",
            )}
          >
            {collection.recordIds.length}
          </span>
        </button>

        {removable && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 hidden group-hover/folder:flex items-center gap-0.5">
            <button
              type="button"
              onClick={() => {
                setRenamingId(collection.id);
                setRenameValue(collection.name);
              }}
              aria-label={`Rename ${collection.name}`}
              title="Rename"
              className="p-1 rounded text-stone-400 hover:text-stone-700 hover:bg-white"
            >
              <i className="fas fa-pen text-[10px]" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => onDelete(collection.id)}
              aria-label={`Delete ${collection.name}`}
              title="Delete folder"
              className="p-1 rounded text-stone-400 hover:text-brand hover:bg-white"
            >
              <i className="fas fa-trash text-[10px]" aria-hidden />
            </button>
          </span>
        )}
      </li>
    );
  };

  const secondaryLink = (
    label: string,
    icon: string,
    count: number | null,
    onClick?: () => void,
    to?: string,
    active?: boolean,
  ) => {
    const inner = (
      <>
        <i className={cn("fas", icon, "text-[13px] shrink-0", active ? "text-brand" : "text-stone-400")} aria-hidden />
        <span className="flex-1 truncate">{label}</span>
        {count !== null && (
          <span
            className={cn(
              "shrink-0 min-w-[20px] px-1.5 py-0.5 rounded text-[10px] font-bold text-center",
              active ? "bg-white text-brand" : "bg-stone-100 text-stone-500",
            )}
          >
            {count}
          </span>
        )}
      </>
    );

    const className = cn(
      "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors text-left",
      active ? "bg-brand-50 text-brand font-semibold" : "text-stone-600 hover:bg-stone-50",
    );

    return to ? (
      <Link to={to} className={className}>
        {inner}
      </Link>
    ) : (
      <button type="button" onClick={onClick} className={className}>
        {inner}
      </button>
    );
  };

  return (
    <div className="flex flex-col h-full bg-white border border-stone-200 rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400">
          Folders
          <span className="ml-1.5 text-stone-300">{collections.length}</span>
        </h2>
        <button
          type="button"
          onClick={onCollapse}
          aria-label="Hide folders"
          title="Hide folders"
          className="p-1.5 rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-700"
        >
          <i className="fas fa-angles-left text-[12px]" aria-hidden />
        </button>
      </div>

      <div className="px-2 pb-2">
        {creating ? (
          <input
            ref={createRef}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onBlur={submitCreate}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitCreate();
              if (e.key === "Escape") {
                setNewName("");
                setCreating(false);
              }
            }}
            placeholder="Folder name…"
            aria-label="New folder name"
            className="w-full px-3 py-2 bg-white border border-brand/40 rounded-lg text-[13px] outline-none placeholder-stone-400"
          />
        ) : (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-brand-200 text-brand text-[13px] font-semibold hover:bg-brand-50 transition-colors"
          >
            <i className="fas fa-folder-plus text-[12px]" aria-hidden />
            New Folder
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto pb-2">
        <ul className="space-y-0.5">
          {statusFolders.map((c) =>
            renderFolder(c, STATUS_FOLDER_ICONS[c.id as StatusFolderId] ?? "fa-folder"),
          )}
        </ul>

        <p className="px-5 pt-4 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-stone-400">
          Custom topics
        </p>
        {topicFolders.length === 0 ? (
          <p className="px-5 pb-2 text-[12px] text-stone-400 leading-snug">
            No topic folders yet. Create one to group papers by theme.
          </p>
        ) : (
          <ul className="space-y-0.5">{topicFolders.map((c) => renderFolder(c, "fa-folder"))}</ul>
        )}
      </div>

      <div className="border-t border-stone-100 p-2 space-y-0.5">
        {secondaryLink("Liked Papers", "fa-star", starredCount, () => onViewChange({ kind: "starred" }), undefined, view.kind === "starred")}
        {secondaryLink("Reading History", "fa-clock-rotate-left", historyCount, () => onViewChange({ kind: "history" }), undefined, view.kind === "history")}
        {secondaryLink("My Disclosures", "fa-file-lines", disclosureCount, undefined, "/workspace", false)}
      </div>
    </div>
  );
}
