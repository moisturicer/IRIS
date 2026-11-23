import { useEffect, useRef, useState } from "react";

import { HERE } from "@/components/ui/highlightRoles";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Select } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import { MAX_FOLDER_NAME, READING_STATUSES, atFolderLimit, type LibraryFolder } from "@/store/library.store";

import { isSameView, viewFromKey, viewKey, type LibraryView } from "./libraryViews";

interface RailItem {
  view: LibraryView;
  label: string;
  icon: string;
}

interface RailGroup {
  id: string;
  label: string;
  items: RailItem[];
}

const STATUS_ICON: Record<string, string> = { want_to_read: "fa-clock", reading: "fa-book-open", completed: "fa-circle-check" };

function railGroups(mayAuthor: boolean, folders: LibraryFolder[]): RailGroup[] {
  return [
    ...(mayAuthor ? [{
      id: "research",
      label: "Your research",
      items: [
        { view: { kind: "research", filter: "all" }, label: "All research", icon: "fa-layer-group" },
        { view: { kind: "research", filter: "waiting" }, label: "Needs your action", icon: "fa-circle-exclamation" },
        { view: { kind: "research", filter: "review" }, label: "In review", icon: "fa-hourglass-half" },
        { view: { kind: "research", filter: "drafts" }, label: "Drafts", icon: "fa-pen" },
        { view: { kind: "research", filter: "finished" }, label: "Finished", icon: "fa-circle-check" },
      ] satisfies RailItem[],
    }] : []),
    {
      id: "reading",
      label: "Reading",
      items: [
        { view: { kind: "saved" }, label: "All saved", icon: "fa-bookmark" },
        ...READING_STATUSES.map((s) => ({ view: { kind: "status", status: s.value } as LibraryView, label: s.label, icon: STATUS_ICON[s.value] })),
        { view: { kind: "history" }, label: "History", icon: "fa-clock-rotate-left" },
      ],
    },
    {
      id: "folders",
      label: "Folders",
      items: folders.map((f) => ({ view: { kind: "folder", id: f.id } as LibraryView, label: f.name, icon: "fa-folder" })),
    },
    {
      id: "requests",
      label: "Requests",
      items: [
        { view: { kind: "calls" }, label: "Saved calls", icon: "fa-bullhorn" },
        { view: { kind: "downloads" }, label: "Download requests", icon: "fa-file-arrow-down" },
      ],
    },
  ];
}

interface LibraryRailProps {
  view: LibraryView;
  onSelect: (view: LibraryView) => void;
  mayAuthor: boolean;
  /** Records waiting on the owner: the one count shown, since each is a thing to do. */
  waiting: number;
  folders: LibraryFolder[];
  /** How many folders the account may hold, when the server has said. */
  folderLimit: number | null;
  onCreateFolder: (name: string) => void;
}

const NEW_FOLDER = "__new__";

/** The new folder's name, in place of the control that asked for it. */
function FolderNameField({ onDone }: { onDone: (name: string | null) => void }) {
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  return (
    <input
      ref={input}
      value={name}
      onChange={(e) => setName(e.target.value)}
      onBlur={() => onDone(name.trim() || null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onDone(name.trim() || null);
        if (e.key === "Escape") onDone(null);
      }}
      aria-label="New folder name"
      placeholder="Folder name, then Enter"
      maxLength={MAX_FOLDER_NAME}
      className="min-h-10 w-full rounded-control border border-field bg-white px-3 text-small placeholder:text-stone-600 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
    />
  );
}

/**
 * My Library's rail (IR-1311): every list the page can show, named once and
 * grouped by what it holds, in place of the tabs, the Reading status chips and
 * the Folder picker. The current list takes the Here look (IR-1097). Only
 * Needs your action carries a count, because each one is a thing to do. From
 * the page's own `library` width of 52rem it stands beside the list; below
 * that it is one native picker, which a phone's own chooser opens.
 */
export function LibraryRail({ view, onSelect, mayAuthor, waiting, folders, folderLimit, onCreateFolder }: LibraryRailProps) {
  // Where the new folder was asked for: its field opens there, and only there.
  const [creating, setCreating] = useState<"rail" | "picker" | null>(null);
  const groups = railGroups(mayAuthor, folders);
  const full = atFolderLimit(folders, folderLimit);

  const finishCreating = (name: string | null) => {
    setCreating(null);
    if (name) onCreateFolder(name);
  };

  const newFolder = creating === "rail" ? <FolderNameField onDone={finishCreating} /> : full ? (
    <p className="px-3 py-1 text-label text-stone-600">{`No room for a new folder (${folderLimit} is the most)`}</p>
  ) : (
    <button
      type="button"
      onClick={() => setCreating("rail")}
      className={cn("flex min-h-9 w-full items-center gap-3 rounded-control px-3 text-left text-small font-medium text-stone-600 hover:bg-stone-100 hover:text-stone-900 touch:min-h-11", COLOUR_TRANSITION, FOCUS_RING)}
    >
      <i className="fas fa-plus w-4 text-center text-label" aria-hidden />
      New folder
    </button>
  );

  return (
    <>
      {/* A phone, or any narrow page: one picker, and New folder after it. */}
      <div className="space-y-2 library-wide:hidden">
        <Select
          label="Show"
          value={viewKey(view)}
          onChange={(e) => {
            if (e.target.value === NEW_FOLDER) setCreating("picker");
            else {
              const next = viewFromKey(e.target.value);
              if (next) onSelect(next);
            }
          }}
        >
          {groups.map((group) => (
            <optgroup key={group.id} label={group.label}>
              {group.items.map((item) => (
                <option key={viewKey(item.view)} value={viewKey(item.view)}>
                  {item.label}{item.view.kind === "research" && item.view.filter === "waiting" && waiting > 0 ? ` (${waiting})` : ""}
                </option>
              ))}
              {group.id === "folders" && (full
                ? <option value={NEW_FOLDER} disabled>{`No room for a new folder (${folderLimit} is the most)`}</option>
                : <option value={NEW_FOLDER}>+ New folder…</option>)}
            </optgroup>
          ))}
        </Select>
        {creating === "picker" && <FolderNameField onDone={finishCreating} />}
      </div>

      <nav aria-label="My Library" className="hidden library-wide:block">
        {groups.map((group) => (
          <div key={group.id} className="mt-6 first:mt-0">
            <p id={`rail-${group.id}`} className="mb-1.5 px-3 font-display text-heading font-semibold text-stone-900">{group.label}</p>
            <ul aria-labelledby={`rail-${group.id}`} className="space-y-0.5">
              {group.items.map((item) => {
                const current = isSameView(item.view, view);
                const count = item.view.kind === "research" && item.view.filter === "waiting" ? waiting : 0;
                return (
                  <li key={viewKey(item.view)}>
                    <button
                      type="button"
                      aria-current={current ? "page" : undefined}
                      onClick={() => onSelect(item.view)}
                      className={cn(
                        "flex min-h-9 w-full items-center gap-3 rounded-control px-3 text-left text-small touch:min-h-11",
                        COLOUR_TRANSITION,
                        FOCUS_RING,
                        current ? HERE : "font-medium text-stone-700 hover:bg-stone-100 hover:text-stone-900",
                      )}
                    >
                      <i className={cn("fas w-4 shrink-0 text-center text-label", item.icon, current ? "text-brand" : "text-stone-500")} aria-hidden />
                      <span className="min-w-0 flex-1 break-words">{item.label}</span>
                      {count > 0 && (
                        <span className="inline-grid h-5 min-w-5 place-items-center rounded-full bg-white px-1.5 text-label font-semibold tabular-nums text-brand ring-1 ring-brand">
                          {count}<span className="sr-only"> waiting</span>
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
              {group.id === "folders" && <li>{newFolder}</li>}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}
