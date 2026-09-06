import { useEffect, useRef, useState } from "react";
import type { RecordListItem } from "@/types/records";
import {
  addCollection,
  getCollections,
  toggleRecordInCollection,
  type Collection,
} from "./discoverUtils";
import { cn } from "@/lib/utils";

interface PaperSaveDropdownProps {
  record: RecordListItem;
}

/**
 * Save a record into a reading collection.
 *
 * IRIS has no server-side bookmark endpoint — `storageApi` stores uploaded
 * files, not reading lists — so collections live in this browser's
 * localStorage only. The menu says so, rather than implying it syncs.
 */
export function PaperSaveDropdown({ record }: PaperSaveDropdownProps) {
  const [open, setOpen] = useState(false);
  const [collections, setCollections] = useState<Collection[]>(() => getCollections());
  const [newName, setNewName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

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

  const savedCount = collections.filter((c) => c.recordIds.includes(record.id)).length;
  const isSaved = savedCount > 0;

  const handleCreate = () => {
    if (!newName.trim()) return;
    const next = addCollection(collections, newName);
    // Drop the record straight into the collection the user just made.
    const created = next[next.length - 1];
    setCollections(toggleRecordInCollection(next, created.id, record.id));
    setNewName("");
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
        aria-label={isSaved ? `Saved to ${savedCount} collection(s)` : "Save to collection"}
        title={isSaved ? `Saved to ${savedCount} collection(s)` : "Save to collection"}
        className={cn(
          "w-[30px] h-[30px] rounded-lg border flex items-center justify-center transition-colors",
          isSaved
            ? "border-brand-200 bg-brand-50 text-brand"
            : "border-slate-200 text-slate-400 hover:text-brand hover:border-brand-200",
        )}
      >
        <i className={cn(isSaved ? "fas" : "far", "fa-bookmark text-[12px]")} aria-hidden />
      </button>

      {open && (
        <div
          // The card itself navigates on click; keep menu interaction local.
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 top-full mt-1.5 w-60 bg-white rounded-lg shadow-card-md border border-slate-200/90 py-1.5 z-40"
        >
          <p className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Save to collection
          </p>

          <div className="max-h-48 overflow-y-auto">
            {collections.map((collection) => {
              const checked = collection.recordIds.includes(record.id);
              return (
                <button
                  key={collection.id}
                  type="button"
                  onClick={() =>
                    setCollections(
                      toggleRecordInCollection(collections, collection.id, record.id),
                    )
                  }
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition text-left"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <i
                      className={cn(
                        "fa-folder text-[11px] shrink-0",
                        checked ? "fas text-brand" : "far text-slate-300",
                      )} aria-hidden />
                    <span className="truncate">{collection.name}</span>
                  </span>
                  {checked && <i className="fas fa-check text-brand text-xs shrink-0" aria-hidden />}
                </button>
              );
            })}
          </div>

          {/* New collection */}
          <div className="border-t border-slate-100 mt-1 pt-2 px-3 pb-1">
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
                placeholder="New collection…"
                className="flex-1 min-w-0 px-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs outline-none focus:border-brand"
              />
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newName.trim()}
                className="w-7 h-7 shrink-0 rounded-lg bg-brand text-white disabled:opacity-30 flex items-center justify-center transition"
                aria-label="Create collection"
              >
                <i className="fas fa-plus text-[10px]" aria-hidden />
              </button>
            </div>
            <p className="mt-2 mb-1 text-[10px] text-slate-400 leading-snug">
              Saved in this browser only — collections don&apos;t sync across devices yet.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
