import { useEffect, useRef, useState } from "react";

import { Select } from "@/components/ui/Select";
import type { ReadingStatus } from "@/api/library";
import type { Collection } from "@/lib/recordLibrary";

/**
 * Which part of My Library the main column shows. `research` is the owner's
 * own records. `saved` and `status` are the account's saves (IR-566,
 * ADR-044); `folder` is one of the reader's own folders and `history` this
 * browser's history, both still browser-only.
 */
export type LibraryView =
  | { kind: "research" }
  | { kind: "saved" }
  | { kind: "status"; status: ReadingStatus }
  | { kind: "folder"; id: string }
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
  collections:  Collection[];
  view:         LibraryView;
  onViewChange: (view: LibraryView) => void;
  onCreate:     (name: string) => void;
}

const NEW_FOLDER = "__new__";

/**
 * The reader's own folders as one picker in the Saved papers toolbar,
 * beside Sort, rather than a second panel to navigate. Folders are still
 * this browser's until IR-572; the toolbar says so. "New folder…" swaps the picker for a name field in place.
 * Renaming and deleting a folder happen in the folder's own view.
 */
export function FolderPicker({ collections, view, onViewChange, onCreate }: FolderPickerProps) {
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
        className="min-h-9 w-48 rounded-lg border border-brand-200 bg-white px-3 text-small placeholder:text-stone-500 focus:border-brand focus:outline-none"
      />
    );
  }

  const value = view.kind === "folder" ? `folder:${view.id}` : "";

  return (
    <Select
      label="Folder"
      size="sm"
      inline
      value={value}
      onChange={(e) => {
        const next = e.target.value;
        if (next === NEW_FOLDER) setCreating(true);
        else if (next.startsWith("folder:")) onViewChange({ kind: "folder", id: next.slice("folder:".length) });
        else onViewChange({ kind: "saved" });
      }}
      className="max-w-[12rem]"
    >
      <option value="">All saved papers</option>
      {collections.length > 0 && (
        <optgroup label="Your folders">
          {collections.map((c) => <option key={c.id} value={`folder:${c.id}`}>{c.name}</option>)}
        </optgroup>
      )}
      <option value={NEW_FOLDER}>+ New folder…</option>
    </Select>
  );
}
