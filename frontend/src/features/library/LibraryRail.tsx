import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { PANE_TITLE } from "@/components/layout/paneTitle";
import { HERE } from "@/components/ui/highlightRoles";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Select } from "@/components/ui/Select";
import { Tooltip } from "@/components/ui/Tooltip";
import { PanelLeftIcon } from "@/features/ai/components/AskIrisIcons";
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
  /** Where Publish opens, for a reader who may author: a quiet row at the top, like New conversation. */
  publishHref?: string;
  /** The page's own name, at the top of the pane like Conversations. */
  title: string;
  /** Narrowed to a strip of icons, where the pane stands beside the list; a phone's picker has nothing to fold. */
  collapsed: boolean;
  onToggle: () => void;
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
export function LibraryRail({ view, onSelect, mayAuthor, waiting, folders, folderLimit, onCreateFolder, publishHref, title, collapsed, onToggle }: LibraryRailProps) {
  // Where the new folder was asked for: its field opens there, and only there.
  const [creating, setCreating] = useState<"rail" | "picker" | null>(null);
  const groups = railGroups(mayAuthor, folders);
  const full = atFolderLimit(folders, folderLimit);

  const finishCreating = (name: string | null) => {
    setCreating(null);
    if (name) onCreateFolder(name);
  };

  const iconRow = collapsed && "justify-center px-0";

  const newFolder = creating === "rail" && !collapsed ? <FolderNameField onDone={finishCreating} /> : full ? (
    <p className={cn("px-3 py-1 text-label text-stone-600", collapsed && "sr-only")}>{`No room for a new folder (${folderLimit} is the most)`}</p>
  ) : (
    <Tooltip label="New folder" disabled={!collapsed} className="block">
      <button
        type="button"
        onClick={() => {
          // The name needs the pane's width.
          if (collapsed) onToggle();
          setCreating("rail");
        }}
        className={cn("flex min-h-10 w-full items-center gap-3 rounded-control px-3 text-left text-body font-medium text-stone-600 hover:bg-brand/[0.07] hover:text-brand-dark touch:min-h-11", iconRow, COLOUR_TRANSITION, FOCUS_RING)}
      >
        <i className="fas fa-plus w-4 shrink-0 text-center text-label" aria-hidden />
        <span className={cn(collapsed && "sr-only")}>New folder</span>
      </button>
    </Tooltip>
  );

  const toggleLabel = collapsed ? "Show My Library lists" : "Hide My Library lists";

  return (
    <>
      <div className="flex h-14 shrink-0 items-center gap-1 border-b border-stone-200/80 px-4 library-wide:px-2.5">
        <h1 className={cn("mr-auto min-w-0 library-wide:pl-3.5", PANE_TITLE, collapsed && "library-wide:sr-only")}>{title}</h1>
        <Tooltip label={toggleLabel} className="hidden shrink-0 library-wide:block">
          <button
            type="button"
            onClick={onToggle}
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
            className={cn("inline-flex size-10 items-center justify-center rounded-control text-stone-600 hover:bg-brand/[0.07] hover:text-brand-dark", COLOUR_TRANSITION, FOCUS_RING)}
          >
            <PanelLeftIcon className="size-5" />
          </button>
        </Tooltip>
      </div>
      <div className={cn("min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-3 scrollbar-thin", collapsed && "library-wide:px-2.5")}>
        {publishHref && (
          <Tooltip label="Publish" disabled={!collapsed} className="block">
            <Link
              to={publishHref}
              className={cn(
                "group flex min-h-10 w-full items-center gap-3 rounded-control px-3 text-left text-body font-medium text-stone-700 hover:bg-brand/[0.07] hover:text-brand-dark touch:min-h-11",
                collapsed && "library-wide:justify-center library-wide:px-0",
                COLOUR_TRANSITION,
                FOCUS_RING,
              )}
            >
              <span aria-hidden className="inline-flex size-5 shrink-0 items-center justify-center rounded-full text-stone-600 ring-1 ring-stone-300 transition-colors duration-150 group-hover:bg-brand group-hover:text-white group-hover:ring-brand">
                <i className="fas fa-plus text-3xs" />
              </span>
              <span className={cn(collapsed && "library-wide:sr-only")}>Publish</span>
            </Link>
          </Tooltip>
        )}
        {/* A phone, or any narrow page: one picker, and New folder after it. */}
        <div className="mt-2 space-y-2 library-wide:hidden">
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
            <div key={group.id} className={collapsed ? "mt-2 border-t border-stone-200 pt-2" : "mt-5"}>
              <p id={`rail-${group.id}`} className={cn("mb-1 px-3 text-label font-semibold text-stone-600", collapsed && "sr-only")}>{group.label}</p>
              <ul aria-labelledby={`rail-${group.id}`} className="space-y-0.5">
                {group.items.map((item) => {
                  const current = isSameView(item.view, view);
                  const count = item.view.kind === "research" && item.view.filter === "waiting" ? waiting : 0;
                  return (
                    <li key={viewKey(item.view)}>
                      <Tooltip label={item.label} disabled={!collapsed} className="block">
                        <button
                          type="button"
                          aria-current={current ? "page" : undefined}
                          onClick={() => onSelect(item.view)}
                          className={cn(
                            "relative flex min-h-10 w-full items-center gap-3 rounded-control px-3 text-left text-body touch:min-h-11",
                            iconRow,
                            COLOUR_TRANSITION,
                            FOCUS_RING,
                            current ? HERE : "font-medium text-stone-700 hover:bg-brand/[0.07] hover:text-brand-dark",
                          )}
                        >
                          <i className={cn("fas w-4 shrink-0 text-center text-label", item.icon, current ? "text-brand" : "text-stone-500")} aria-hidden />
                          <span className={collapsed ? "sr-only" : "min-w-0 flex-1 break-words"}>{item.label}</span>
                          {count > 0 && (
                            <span
                              className={cn(
                                "inline-grid place-items-center rounded-full bg-brand font-semibold tabular-nums text-white",
                                collapsed ? "absolute right-0 top-0 h-4 min-w-4 px-1 text-3xs ring-2 ring-stone-50" : "h-5 min-w-5 px-1.5 text-label",
                              )}
                            >
                              {count}<span className="sr-only"> waiting</span>
                            </span>
                          )}
                        </button>
                      </Tooltip>
                    </li>
                  );
                })}
                {group.id === "folders" && <li>{newFolder}</li>}
              </ul>
            </div>
          ))}
        </nav>
      </div>
    </>
  );
}
