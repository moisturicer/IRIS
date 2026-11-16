import { useEffect, useRef, useState } from "react";

import { Select } from "@/components/ui/Select";
import type { ReadingStatus } from "@/api/library";
import { MAX_FOLDER_NAME, atFolderLimit, type LibraryFolder } from "@/store/library.store";

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

interface FolderPickerProps {
  folders:      LibraryFolder[];
  /** How many folders the account may hold, when the server has said. */
  limit:        number | null;
  view:         LibraryView;
  onViewChange: (view: LibraryView) => void;
  onCreate:     (name: string) => void;
}

const NEW_FOLDER = "__new__";
const HISTORY = "__history__";

/**
 * The reader's own folders as one picker in the Saved papers toolbar,
 * beside Sort, rather than a second panel to navigate. They are the account's
 * (IR-572), read from the server with the saves. "New folder…" swaps the
 * picker for a name field in place, and is offered only while the account
 * has room for another. Renaming and deleting a folder happen in the
 * folder's own view. History (IR-756) is here too, because its pause switch
 * lives in its view and every reader, author or not, has this toolbar.
 */
export function FolderPicker({ folders, limit, view, onViewChange, onCreate }: FolderPickerProps) {
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

  if (creating) {
    return (
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
        placeholder="Folder name, then Enter"
        maxLength={MAX_FOLDER_NAME}
        className="min-h-9 w-48 rounded-control border border-field bg-white px-3 text-small placeholder:text-stone-600 focus:border-brand focus:outline-none"
      />
    );
  }

  const value = view.kind === "folder" ? `folder:${view.id}` : view.kind === "history" ? HISTORY : "";
  const full = atFolderLimit(folders, limit);

  return (
    <Select
      label="Folder"
      size="sm"
      inline
      value={value}
      onChange={(e) => {
        const next = e.target.value;
        if (next === NEW_FOLDER) setCreating(true);
        else if (next === HISTORY) onViewChange({ kind: "history" });
        else if (next.startsWith("folder:")) onViewChange({ kind: "folder", id: Number(next.slice("folder:".length)) });
        else onViewChange({ kind: "saved" });
      }}
      className="max-w-[12rem]"
    >
      <option value="">All saved papers</option>
      <option value={HISTORY}>History</option>
      {folders.length > 0 && (
        <optgroup label="Your folders">
          {folders.map((f) => <option key={f.id} value={`folder:${f.id}`}>{f.name}</option>)}
        </optgroup>
      )}
      {full
        ? <option value={NEW_FOLDER} disabled>{`No room for a new folder (${limit} is the most)`}</option>
        : <option value={NEW_FOLDER}>+ New folder…</option>}
    </Select>
  );
}
