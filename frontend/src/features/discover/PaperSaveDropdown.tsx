import { useEffect, useRef, useState } from "react";
import type { RecordListItem } from "@/types/records";
import { cn } from "@/lib/utils";
import { PILL_PRIMARY, PILL_SECONDARY, PILL_SELECTED } from "@/components/ui/pillStyles";
import { MAX_FOLDER_NAME, READING_STATUSES, atFolderLimit, useLibraryStore } from "@/store/library.store";
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
 * Saves, Reading status (IR-566, ADR-044) and the reader's own folders
 * (IR-572, ADR-070) belong to the signed-in account and come from the one
 * library store, so this menu, the Record page and My Library always agree.
 * Filing a paper saves it; taking it out of a folder leaves it saved.
 */
export function PaperSaveDropdown({ record, variant = "icon", emphasis = "secondary" }: PaperSaveDropdownProps) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const { load, retry } = useLibrary();
  const item = useLibraryStore((s) => s.items[record.id]);
  const failure = useLibraryStore((s) => (s.failure?.recordId === record.id ? s.failure : null));
  const save = useLibraryStore((s) => s.save);
  const unsave = useLibraryStore((s) => s.unsave);
  const folders = useLibraryStore((s) => s.folders);
  const folderLimit = useLibraryStore((s) => s.folderLimit);
  const createFolder = useLibraryStore((s) => s.createFolder);
  const fileInFolder = useLibraryStore((s) => s.fileInFolder);
  const removeFromFolder = useLibraryStore((s) => s.removeFromFolder);

  useEffect(() => {
    if (!open) return;

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

  const full = atFolderLimit(folders, folderLimit);

  const toggleFolder = (folderId: number, filed: boolean) => {
    // Filing a paper saves it (a folder holds saved papers); taking it out of
    // a folder leaves it saved.
    if (filed) void removeFromFolder(folderId, record.id);
    else void fileInFolder(folderId, record.id, record);
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name || full) return;
    setNewName("");
    const made = await createFolder(name, record.id);
    if (made && !made.recordIds.includes(record.id)) await fileInFolder(made.id, record.id, record);
  };

  // Unsaving takes the paper out of every folder too.
  const handleRemove = () => void unsave(record.id);

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
                "w-11 h-11 [@media(pointer:fine)]:w-9 [@media(pointer:fine)]:h-9 rounded-control border",
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
        <p role="alert" className="absolute top-full mt-1.5 right-0 w-60 z-40 rounded-control border border-stone-300 bg-white px-3 py-2 text-2xs text-brand shadow-card-md">
          {failure.message}
        </p>
      )}

      {open && (
        <div
          // The card itself navigates on click; keep menu interaction local.
          onClick={(e) => e.stopPropagation()}
          className={cn("absolute top-full mt-1.5 w-64", variant === "pill" ? "left-0" : "right-0", "bg-white rounded-control shadow-card-md border border-stone-200/90 py-1.5 z-40")}
        >
          {failure && (
            <p role="alert" className="mx-3 mb-1.5 rounded-control border border-stone-300 bg-surface px-2 py-1.5 text-2xs text-brand">
              {failure.message}
            </p>
          )}
          {load === "error" && (
            <p className="mx-3 mb-1.5 text-2xs text-stone-600">
              Your library did not load.{" "}
              <button type="button" onClick={retry} className="font-semibold text-brand underline">Try again</button>
            </p>
          )}

          <p className="px-3 py-1.5 text-2xs font-bold text-stone-500">
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
            <p className="px-3 py-1.5 text-2xs font-bold text-stone-500">
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
                    onClick={() => toggleFolder(folder.id, checked)}
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
                      void handleCreate();
                    }
                  }}
                  placeholder="New folder…"
                  aria-label="New folder name"
                  maxLength={MAX_FOLDER_NAME}
                  disabled={full}
                  className="flex-1 min-w-0 px-2 py-1.5 bg-stone-50 border border-field rounded-control text-xs outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={full || !newName.trim()}
                  className="w-7 h-7 shrink-0 rounded-control bg-brand text-white disabled:opacity-30 flex items-center justify-center transition"
                  aria-label="Create folder"
                >
                  <i className="fas fa-plus text-2xs" aria-hidden />
                </button>
              </div>
              <p className="mt-2 mb-1 text-2xs text-stone-500 leading-snug">
                {full
                  ? `You have ${folderLimit} folders, the most an account holds. Delete one in My Library to make another.`
                  : "Saves, reading status and folders follow your account."}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
