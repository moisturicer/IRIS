import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Modal } from "@/components/ui/Modal";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { ReadingStatus } from "@/api/library";
import { MAX_FOLDER_NAME, atFolderLimit, type LibraryFolder } from "@/store/library.store";
import { RowMenu } from "@/features/accounts/RowMenu";

/**
 * Which part of My Library the main column shows. `research` is the owner's
 * own records. `saved` and `status` are the account's saves (IR-566,
 * ADR-044), `folder` one of the reader's own folders, which follow the
 * account too (IR-572, ADR-070), and `history` the account's reading history
 * (IR-756).
 */
export type LibraryView =
  | { kind: "research" }
  | { kind: "saved" }
  | { kind: "status"; status: ReadingStatus }
  | { kind: "folder"; id: number }
  | { kind: "history" };

export function isSameView(a: LibraryView, b: LibraryView): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "folder" && b.kind === "folder") return a.id === b.id;
  if (a.kind === "status" && b.kind === "status") return a.status === b.status;
  return true;
}

export function viewKey(view: LibraryView): string {
  if (view.kind === "folder") return `folder:${view.id}`;
  if (view.kind === "status") return `status:${view.status}`;
  return view.kind;
}

interface FolderShelfProps {
  folders:      LibraryFolder[];
  /** How many folders the account may hold, when the server has said. */
  limit:        number | null;
  /**
   * A reader with no Overview reaches History from here (IR-1324); an author
   * reaches it from the Overview's Recently opened.
   */
  onManageHistory?: () => void;
  onOpen:       (view: LibraryView) => void;
  onCreate:     (name: string) => void;
  onRename:     (id: number, name: string) => void;
  onDelete:     (id: number) => void;
}

/** A closed folder, drawn in greys like a desktop folder (IR-1324). */
function FolderGlyph() {
  return (
    <svg viewBox="0 0 48 40" className="h-10 w-12" aria-hidden>
      <path d="M2 6a4 4 0 0 1 4-4h11.5l5 5H42a4 4 0 0 1 4 4v3H2z" className="fill-stone-300" />
      <path d="M2 12h44v22a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4z" className={cn("fill-stone-400 group-hover:fill-stone-500", COLOUR_TRANSITION)} />
    </svg>
  );
}

const papers = (n: number) => `${n} ${n === 1 ? "paper" : "papers"}`;

const TILE = cn(
  "group flex h-full w-full flex-col items-start gap-2 rounded-card border border-stone-200 bg-white p-3 text-left hover:border-stone-300 hover:bg-stone-50",
  COLOUR_TRANSITION,
  FOCUS_RING,
);

/**
 * Naming a folder, new or renamed, in a dialog (IR-1324). Closing it by
 * Cancel, the close button, Escape or a click outside just closes it: nothing
 * is saved and nothing asks first.
 */
function FolderNameDialog({ open, title, initial = "", submitLabel, onClose, onSubmit }: {
  open:        boolean;
  title:       string;
  initial?:    string;
  submitLabel: string;
  onClose:     () => void;
  onSubmit:    (name: string) => void;
}) {
  const formId = useId();
  const [name, setName] = useState(initial);
  useEffect(() => {
    if (open) setName(initial);
  }, [open, initial]);
  const trimmed = name.trim();
  const ready = trimmed.length > 0 && trimmed !== initial;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" form={formId} disabled={!ready}>{submitLabel}</Button>
        </>
      }
    >
      <form
        id={formId}
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready) return;
          onSubmit(trimmed);
          onClose();
        }}
      >
        <Input
          label="Folder name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={MAX_FOLDER_NAME}
          autoFocus
          required
        />
      </form>
    </Modal>
  );
}

/**
 * Saved Papers' folders as tiles (IR-1324), replacing the Folder picker
 * (IR-1313): each of the reader's own folders (IR-572) with its name and how
 * many papers it holds. History (IR-756) is not a folder: it opens from the
 * Overview's Recently opened, or from here for a reader with no Overview
 * (ADR-044 amendment 2026-11-24). **+ Folder** names a new
 * folder in a dialog and is greyed once the account has no room for another.
 * Each folder's "⋯" menu renames it (in a dialog) or deletes it; deleting a
 * folder never unsaves its papers.
 */
export function FolderShelf({ folders, limit, onManageHistory, onOpen, onCreate, onRename, onDelete }: FolderShelfProps) {
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<LibraryFolder | null>(null);
  const full = atFolderLimit(folders, limit);

  return (
    <section aria-labelledby="saved-folders" className="mb-section-lg">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="saved-folders" className="font-display text-title font-semibold text-stone-900">Folders</h2>
          <p className="text-small text-stone-600">
            Saves and folders follow your account.
            {onManageHistory && (
              <>
                {" "}
                <button type="button" onClick={onManageHistory} className={cn("rounded-control font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
                  Manage reading history
                </button>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          disabled={full}
          className={cn(PILL_SECONDARY, "min-h-9 px-4 disabled:cursor-not-allowed disabled:opacity-60", FOCUS_RING)}
        >
          <i className="fas fa-plus text-label" aria-hidden />
          Folder
        </button>
      </div>
      {full && <p className="-mt-1 mb-3 text-small text-stone-600">You have {limit} folders, the most an account can hold.</p>}

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        {folders.length === 0 && (
          <li className="col-span-2 flex items-center gap-3 rounded-card border border-dashed border-stone-300 p-3">
            <FolderGlyph />
            <p className="text-small text-stone-600">
              No folders yet. <span className="font-semibold text-stone-800">+ Folder</span> makes one; file papers into it from their Save menu.
            </p>
          </li>
        )}
        {folders.map((folder) => (
          <li key={folder.id} className="relative">
            <button
              type="button"
              onClick={() => onOpen({ kind: "folder", id: folder.id })}
              aria-label={`${folder.name}, ${papers(folder.recordIds.length)}`}
              className={cn(TILE, "pr-11")}
            >
              <FolderGlyph />
              <span className="break-words text-small font-semibold text-stone-900">{folder.name}</span>
              <span className="mt-auto text-label text-stone-600">{papers(folder.recordIds.length)}</span>
            </button>
            <div className="absolute right-1.5 top-1.5">
              <RowMenu
                small
                label={`Actions for ${folder.name}`}
                items={[
                  { key: "rename", label: "Rename", onSelect: () => setRenaming(folder) },
                  { key: "delete", label: "Delete folder", danger: true, onSelect: () => onDelete(folder.id) },
                ]}
              />
            </div>
          </li>
        ))}
      </ul>

      <FolderNameDialog
        open={creating}
        title="New folder"
        submitLabel="Create folder"
        onClose={() => setCreating(false)}
        onSubmit={onCreate}
      />
      <FolderNameDialog
        open={renaming !== null}
        title="Rename folder"
        initial={renaming?.name ?? ""}
        submitLabel="Rename"
        onClose={() => setRenaming(null)}
        onSubmit={(name) => { if (renaming) onRename(renaming.id, name); }}
      />
    </section>
  );
}
