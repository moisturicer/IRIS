import { useEffect, useRef, useState } from "react";
import type { RecordListItem } from "@/types/records";
import {
  addCollection,
  getCollections,
  removeFromCollections,
  toggleRecordInCollection,
  type Collection,
} from "@/lib/recordLibrary";
import { cn } from "@/lib/utils";
import { PILL_PRIMARY, PILL_SECONDARY, PILL_SELECTED } from "@/components/ui/pillStyles";
import { READING_STATUSES, useLibraryStore } from "@/store/library.store";
import { useLibrary } from "@/features/library/useLibrary";

interface PaperSaveDropdownProps {
  record: RecordListItem;
  /**
   * `icon` for a card (Discover); `pill` for a page's action row, labelled
   * and sized like its neighbours (IR-356).
   */
  variant?: "icon" | "pill";
  /** For `pill`: whether it is the row's one filled action (IR-356). */
  emphasis?: "primary" | "secondary";
}

/**
 * Save a record, give it a Reading status, or file it in a folder.
 *
 * Saves and Reading status belong to the signed-in account (IR-566,
 * ADR-044) and come from the one library store, so this menu, the Record page
 * and My Library always agree. The reader's own folders stay in this browser
 * until IR-572, and the menu says so where they are listed.
 */
export function PaperSaveDropdown({ record, variant = "icon", emphasis = "secondary" }: PaperSaveDropdownProps) {
  const [open, setOpen] = useState(false);
  const [folders, setFolders] = useState<Collection[]>(() => getCollections());
  const [newName, setNewName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const { load, retry } = useLibrary();
  const item = useLibraryStore((s) => s.items[record.id]);
  const failure = useLibraryStore((s) => (s.failure?.recordId === record.id ? s.failure : null));
  const save = useLibraryStore((s) => s.save);
  const unsave = useLibraryStore((s) => s.unsave);

  useEffect(() => {
    if (!open) return;
    setFolders(getCollections());

    function handlePointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const isSaved = Boolean(item);
  const status = item?.readingStatus ?? null;
  const label = isSaved ? "Saved" : "Save";

  const fileInFolder = (next: Collection[], folderId: string) => {
    const updated = toggleRecordInCollection(next, folderId, record.id);
    setFolders(updated);
    // Filing a paper saves it: a folder holds saved papers.
    const nowIn = updated.find((f) => f.id === folderId)?.recordIds.includes(record.id);
    if (nowIn && !isSaved) void save(record.id, undefined, record);
  };

  const handleCreate = () => {
    if (!newName.trim()) return;
    const next = addCollection(folders, newName);
    fileInFolder(next, next[next.length - 1].id);
    setNewName("");
  };

  const handleRemove = () => {
    setFolders(removeFromCollections(folders, [record.id]));
    void unsave(record.id);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        aria-label={label}
        title={label}
        className={cn(
          "flex items-center justify-center transition-colors",
          variant === "pill"
            ? isSaved
              ? PILL_SELECTED
              : emphasis === "primary"
                ? PILL_PRIMARY
                : PILL_SECONDARY
            : cn(
                "w-11 h-11 [@media(pointer:fine)]:w-9 [@media(pointer:fine)]:h-9 rounded-lg border",
                isSaved
                  ? "border-stone-300 bg-stone-100 text-brand"
                  : "border-stone-200 bg-white text-stone-600 hover:text-brand hover:border-stone-400 hover:bg-stone-50",
              ),
        )}
      >
        <i className={cn(isSaved ? "fas" : "far", "fa-bookmark text-xs")} aria-hidden />
        {variant === "pill" && <span aria-hidden>{label}</span>}
      </button>

      {failure && !open && (
        <p role="alert" className="absolute top-full mt-1.5 right-0 w-60 z-40 rounded-lg border border-brand-200 bg-white px-3 py-2 text-2xs text-brand shadow-card-md">
          {failure.message}
        </p>
      )}

      {open && (
        <div
          // The card itself navigates on click; keep menu interaction local.
          onClick={(e) => e.stopPropagation()}
          className={cn("absolute top-full mt-1.5 w-64", variant === "pill" ? "left-0" : "right-0", "bg-white rounded-lg shadow-card-md border border-stone-200/90 py-1.5 z-40")}
        >
          {failure && (
            <p role="alert" className="mx-3 mb-1.5 rounded-md bg-brand-50 px-2 py-1.5 text-2xs text-brand">
              {failure.message}
            </p>
          )}
          {load === "error" && (
            <p className="mx-3 mb-1.5 text-2xs text-stone-600">
              Your library did not load.{" "}
              <button type="button" onClick={retry} className="font-semibold text-brand underline">Try again</button>
            </p>
          )}

          <p className="px-3 py-1.5 text-2xs font-bold uppercase tracking-wider text-stone-500">
            Reading status
          </p>
          {READING_STATUSES.map((option) => {
            const checked = status === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={checked}
                onClick={() => void save(record.id, checked ? null : option.value, record)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 text-xs text-stone-700 hover:bg-stone-50 transition text-left"
              >
                <span className="flex items-center gap-2 min-w-0">
                  <i className={cn(checked ? "fas text-brand" : "far text-stone-300", option.icon, "text-2xs shrink-0")} aria-hidden />
                  <span className="truncate">{option.label}</span>
                </span>
                {checked && <i className="fas fa-check text-brand text-xs shrink-0" aria-hidden />}
              </button>
            );
          })}

          <div className="border-t border-stone-100 mt-1 pt-1">
            {isSaved ? (
              <button
                type="button"
                onClick={handleRemove}
                className="w-full px-3 py-2 text-left text-xs text-stone-700 hover:bg-stone-50 transition"
              >
                Remove from My Library
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void save(record.id, undefined, record)}
                className="w-full px-3 py-2 text-left text-xs font-semibold text-brand hover:bg-stone-50 transition"
              >
                Save to My Library
              </button>
            )}
          </div>

          <div className="border-t border-stone-100 mt-1 pt-1">
            <p className="px-3 py-1.5 text-2xs font-bold uppercase tracking-wider text-stone-500">
              Your folders
            </p>
            <div className="max-h-40 overflow-y-auto">
              {folders.map((folder) => {
                const checked = folder.recordIds.includes(record.id);
                return (
                  <button
                    key={folder.id}
                    type="button"
                    aria-pressed={checked}
                    onClick={() => fileInFolder(folders, folder.id)}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-xs text-stone-700 hover:bg-stone-50 transition text-left"
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <i className={cn("fa-folder text-2xs shrink-0", checked ? "fas text-brand" : "far text-stone-300")} aria-hidden />
                      <span className="truncate">{folder.name}</span>
                    </span>
                    {checked && <i className="fas fa-check text-brand text-xs shrink-0" aria-hidden />}
                  </button>
                );
              })}
            </div>
            <div className="px-3 pt-1 pb-1">
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleCreate();
                    }
                  }}
                  placeholder="New folder…"
                  aria-label="New folder name"
                  className="flex-1 min-w-0 px-2 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-xs outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!newName.trim()}
                  className="w-7 h-7 shrink-0 rounded-lg bg-brand text-white disabled:opacity-30 flex items-center justify-center transition"
                  aria-label="Create folder"
                >
                  <i className="fas fa-plus text-2xs" aria-hidden />
                </button>
              </div>
              <p className="mt-2 mb-1 text-2xs text-stone-500 leading-snug">
                Saves and reading status follow your account. Your folders stay in this browser for now.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
