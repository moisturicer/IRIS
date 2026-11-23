import { useEffect, useId, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { Link } from "react-router-dom";
import { cn, formatDate } from "@/lib/utils";
import { TITLE_MAX, TITLE_TOO_LONG, type ReaderConversationSummary } from "@/api/runtimeReader";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { HERE } from "@/components/ui/highlightRoles";
import { Tooltip } from "@/components/ui/Tooltip";
import { RowMenu, type RowMenuItem } from "@/features/accounts/RowMenu";
import { PanelLeftIcon } from "./AskIrisIcons";
import { IrisLoader } from "@/components/brand/IrisBrand";
import { usePinnedConversations, type Pin } from "../hooks/usePinnedConversations";
import type { TroubleKind } from "../runtime/trouble";

/** The history search and paging, from `useConversationHistory`. */
export interface HistorySearch {
  text:        string;
  onText:      (text: string) => void;
  query:       string;
  state:       "loading" | "ready" | "error";
  /** Why the list request failed, while `state` is "error" (IR-1238). */
  failure?:    TroubleKind;
  /** Asks for the first page again; the "Try again" of a failed list. */
  onRetry:     () => void;
  /** The chat is already telling the reader this failure, so the list stays quiet about it (IR-1238). */
  quiet?:      boolean;
  hasMore:     boolean;
  loadingMore: boolean;
  onMore:      () => void;
}

/** Saves a title; resolves to a message for the reader, or null once saved (IR-1160). */
export type RenameConversation = (id: string, title: string) => Promise<string | null>;

export const SIDEBAR_MIN = 220;
export const SIDEBAR_MAX = 480;
export const SIDEBAR_DEFAULT = 280;

/** The width of the strip the pane shrinks to while it is closed (IR-1233). */
export const STRIP_WIDTH = 60;
/** How long the open/close width animation is given before resizing follows the pointer again. */
const SETTLE_MS = 240;

interface ConversationSidebarProps {
  conversations:    ReaderConversationSummary[];
  activeId:         string | null;
  open:             boolean;
  search:           HistorySearch;
  /** The pane's id, which the toggle's `aria-controls` names. */
  id:               string;
  /** The search box, so the page can put focus in it when it opens the pane to search. */
  searchRef?:       RefObject<HTMLInputElement>;
  onDelete:         (id: string) => void;
  onRename:         RenameConversation;
  onNewConversation: () => void;
  /** The strip's Search: the page opens the pane and focuses the search box. */
  onSearch:         () => void;
  /** Opens a closed pane and closes an open one. */
  onToggle:         () => void;
  /** The column's width, which the reader drags or arrows (`SIDEBAR_MIN`–`SIDEBAR_MAX`). */
  width:            number;
  onResize:         (width: number) => void;
}

/**
 * The history search box (IR-1257): a fill and the field outline at rest,
 * since on the pane's stone-50 it vanished. Like every other search box in
 * IRIS (My submissions, a Saved folder), hovering changes nothing and typing
 * shows only in the outline: a brand border and ring, the fill unchanged.
 */
const SEARCH_BOX =
  "flex min-h-10 w-full min-w-0 cursor-text items-center gap-3 rounded-control border border-field bg-stone-100 px-3 text-body text-stone-700 " +
  "focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20 " + COLOUR_TRANSITION;

/** The hover every row in the pane shares (IR-1306): a low wash of the binding maroon. */
const MAROON_HOVER = "hover:bg-brand/[0.07] hover:text-brand-dark " + COLOUR_TRANSITION;

const ICON_BUTTON =
  "inline-flex size-10 shrink-0 items-center justify-center rounded-control text-stone-600 " +
  "hover:bg-stone-200/70 hover:text-stone-900 " + COLOUR_TRANSITION + " " + FOCUS_RING;

/**
 * The one toggle for the conversations pane (IR-1233): a left-panel icon at the
 * pane's top-left, in the same place open or closed, so a reader never hunts for
 * it and focus stays on it through the change. On a phone the same button sits in
 * the chat header and opens the pane as a dialog (`asDialog`).
 */
export function ConversationsToggle({ open, onClick, controls, asDialog = false }: {
  open: boolean;
  onClick: () => void;
  controls?: string;
  asDialog?: boolean;
}) {
  const label = open ? "Hide conversations" : "Show conversations";
  return <Tooltip label={label} className="shrink-0">
    <button type="button" onClick={onClick} aria-label={label} aria-expanded={open}
      aria-controls={controls} aria-haspopup={asDialog ? "dialog" : undefined}
      className={cn(ICON_BUTTON, asDialog && "size-11")}>
      <PanelLeftIcon />
    </button>
  </Tooltip>;
}

/**
 * The pane pushes the chat over, never covers it. Open it is the toggle and
 * New conversation over Search, Pinned and Recents; closed it narrows to a strip of the
 * toggle, a New conversation icon and a Search icon. The list keeps its own width while
 * the column animates, so it slides rather than reflows.
 */
export function ConversationSidebar({
  conversations, activeId, open, search, id, searchRef, onDelete, onRename, onNewConversation, onSearch, onToggle, width, onResize,
}: ConversationSidebarProps) {
  // A drag must follow the pointer, so the width eases only while the pane opens or closes.
  // Decided while rendering, so the render that changes the width already carries the transition.
  const [easing, setEasing] = useState(false);
  const [wasOpen, setWasOpen] = useState(open);
  if (wasOpen !== open) { setWasOpen(open); setEasing(true); }
  useEffect(() => {
    if (!easing) return;
    const timer = window.setTimeout(() => setEasing(false), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [easing]);

  return (
    <aside
      id={id}
      style={{ width: open ? width : STRIP_WIDTH }}
      className={cn(
        "relative shrink-0 flex flex-col bg-stone-50 border-r border-stone-200",
        easing && "transition-[width] duration-200 ease-out motion-reduce:transition-none",
      )}
      aria-label="Conversations"
    >
      <div className="h-full min-h-0 w-full overflow-hidden">
        {/* Fixed width, so the list does not reflow while the column animates. */}
        <div className="relative flex h-full min-h-0 flex-col" style={{ width: Math.max(width, STRIP_WIDTH) }}>
          <div className="flex h-14 shrink-0 items-center gap-1 border-b border-stone-200/80 px-2.5">
            <ConversationsToggle open={open} onClick={onToggle} controls={id} />
            {open && <h2 className="min-w-0 px-1 text-control font-semibold text-stone-800">Conversations</h2>}
          </div>

          {/* Hidden, not unmounted, so a search and the scroll position survive a close. */}
          <div aria-hidden={!open} {...(open ? {} : { inert: "" })}
            className={cn("flex min-h-0 flex-1 flex-col", !open && "invisible")}>
            <ConversationHistoryList conversations={conversations} activeId={activeId} search={search}
              searchRef={searchRef} onDelete={onDelete} onRename={onRename} onNewConversation={onNewConversation} />
          </div>

          {!open && <div className="absolute left-0 top-14 flex flex-col items-center gap-1 pt-3" style={{ width: STRIP_WIDTH }}>
            <Tooltip label="New conversation">
              <button type="button" onClick={onNewConversation} aria-label="New conversation" className={ICON_BUTTON}>
                <i className="fas fa-plus text-label" aria-hidden />
              </button>
            </Tooltip>
            <Tooltip label="Search conversations (Ctrl+K)">
              <button type="button" onClick={onSearch} aria-label="Search conversations" className={ICON_BUTTON}>
                <i className="fas fa-magnifying-glass text-label" aria-hidden />
              </button>
            </Tooltip>
          </div>}
        </div>
      </div>
      {open && <SidebarResizer width={width} onChange={onResize} />}
    </aside>
  );
}

/** The column's right edge: drag, or arrow keys; double-click resets. */
function SidebarResizer({ width, onChange }: { width: number; onChange: (width: number) => void }) {
  const clamp = (n: number) => Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, Math.round(n)));
  return <div
    role="separator" aria-orientation="vertical" aria-label="Resize conversations"
    aria-valuemin={SIDEBAR_MIN} aria-valuemax={SIDEBAR_MAX} aria-valuenow={width} tabIndex={0}
    onPointerDown={e => e.currentTarget.setPointerCapture?.(e.pointerId)}
    onPointerMove={e => {
      if (!e.currentTarget.hasPointerCapture?.(e.pointerId)) return;
      const left = e.currentTarget.parentElement?.getBoundingClientRect().left ?? 0;
      onChange(clamp(e.clientX - left));
    }}
    onDoubleClick={() => onChange(SIDEBAR_DEFAULT)}
    onKeyDown={e => {
      const step = e.shiftKey ? 80 : 24;
      if (e.key === "ArrowLeft") onChange(clamp(width - step));
      else if (e.key === "ArrowRight") onChange(clamp(width + step));
      else if (e.key === "Home") onChange(SIDEBAR_MIN);
      else if (e.key === "End") onChange(SIDEBAR_MAX);
      else return;
      e.preventDefault();
    }}
    className="absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize touch-none
      after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent after:transition-colors
      hover:after:bg-brand/40 focus-visible:outline-none focus-visible:after:w-0.5 focus-visible:after:bg-brand"
  />;
}

/**
 * Search (IR-1161), Pinned and Recents, each Conversation a link to its own
 * address with Pin, Rename (IR-1160) and Delete. Beside the answer on a wide
 * page, and in the history drawer on a phone (IR-570).
 */
export function ConversationHistoryList({
  conversations, activeId, search, onDelete, onRename, onNewConversation, searchRef: givenRef,
}: {
  conversations: ReaderConversationSummary[];
  activeId:      string | null;
  search:        HistorySearch;
  onDelete:      (id: string) => void;
  /** Absent, a row offers no Rename. */
  onRename?:     RenameConversation;
  /** Lets the page focus the search box; the list keeps its own when none is given. */
  searchRef?:    RefObject<HTMLInputElement>;
  /** Shown under the search box, above Pinned (IR-1306). */
  onNewConversation?: () => void;
}) {
  const searchId = useId();
  const ownRef = useRef<HTMLInputElement>(null);
  const searchRef = givenRef ?? ownRef;
  const [pinnedOpen, setPinnedOpen] = useState(true);
  const { pins, toggle, retitle, unpin } = usePinnedConversations();

  // A pin keeps the title the list last showed.
  useEffect(() => { conversations.forEach(c => retitle(c.id, c.title)); }, [conversations, retitle]);

  // Ctrl+K (⌘K on a Mac) goes to search.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && searchRef.current && !searchRef.current.closest("[aria-hidden=true]")) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const pinnedIds = new Set(pins.map(p => p.id));
  const recents = search.query ? conversations : conversations.filter(c => !pinnedIds.has(c.id));
  const row = (entry: Pin, updatedAt?: string) => (
    <HistoryRow key={entry.id} entry={entry} updatedAt={updatedAt} active={entry.id === activeId}
      pinned={pinnedIds.has(entry.id)} onPin={() => toggle(entry)} onRename={onRename}
      onDelete={() => { unpin(entry.id); onDelete(entry.id); }} />
  );

  return (<>
    <div className="shrink-0 space-y-0.5 px-2 pt-2">
      <label htmlFor={searchId} className={SEARCH_BOX}>
        <i className="fas fa-magnifying-glass w-4 text-center text-label" aria-hidden />
        <span className="sr-only">Search your past conversations</span>
        <input id={searchId} ref={searchRef} type="search" value={search.text} onChange={e => search.onText(e.target.value)}
          onKeyDown={e => { if (e.key === "Escape") { search.onText(""); e.currentTarget.blur(); } }}
          placeholder="Search" autoComplete="off" maxLength={200} disabled={search.state === "error"}
          className="min-w-0 flex-1 bg-transparent text-body text-stone-900 placeholder:text-stone-700 focus:outline-none" />
        {/* stone-600: stone-500 falls under 4.5:1 on the box's stone-100 fill (IR-1257). */}
        <kbd aria-hidden className="shrink-0 font-sans text-2xs text-stone-600">Ctrl+K</kbd>
      </label>
      <p role="status" aria-live="polite" className="px-3 text-label text-stone-600">
        {search.query && search.state === "ready" ? `${conversations.length}${search.hasMore ? "+" : ""} found` : ""}
      </p>
      {onNewConversation && <NewConversationButton onClick={onNewConversation} />}
    </div>

    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-thin px-2 pb-2">
      {!search.query && pins.length > 0 && <div className="mt-2">
        <button type="button" aria-expanded={pinnedOpen} onClick={() => setPinnedOpen(v => !v)}
          className={cn("flex items-center gap-1.5 rounded-control px-3 py-1 text-label font-medium text-stone-500 hover:text-stone-800", FOCUS_RING)}>
          Pinned
          <i className={cn("fas fa-chevron-down text-2xs transition-transform", !pinnedOpen && "-rotate-90")} aria-hidden />
        </button>
        {pinnedOpen && <nav aria-label="Pinned conversations">
          <ul className="mt-0.5 space-y-0.5">{pins.map(pin => row(pin))}</ul>
        </nav>}
      </div>}

      <p className="mt-3 px-3 py-1 text-label font-medium text-stone-500">{search.query ? "Results" : "Recents"}</p>
      {search.state === "error" && !search.quiet && (
        <div role="alert" className="space-y-1 px-3 py-3 text-small text-stone-700">
          <p>{"IRIS couldn't load your conversations. Your new questions still work."}</p>
          <button type="button" onClick={search.onRetry}
            className={cn("min-h-11 rounded-control text-brand underline", FOCUS_RING)}>Try again</button>
        </div>
      )}
      {conversations.length === 0 && search.state === "ready" && (
        <p className="px-3 py-6 text-small text-stone-500 text-center">
          {search.query ? `No conversations match “${search.query}”.` : "Your past conversations will appear here."}
        </p>
      )}
      {recents.length > 0 && <nav aria-label="Past conversations">
        <ul className="space-y-0.5">{recents.map(c => row(c, c.updated_at))}</ul>
      </nav>}
      {search.hasMore && <LoadOlder loading={search.loadingMore} onClick={search.onMore} />}
    </div>
  </>);
}

function HistoryRow({ entry, updatedAt, active, pinned, onPin, onRename, onDelete }: {
  entry: Pin;
  updatedAt?: string;
  active: boolean;
  pinned: boolean;
  onPin: () => void;
  onRename?: RenameConversation;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entry.title);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const rowRef = useRef<HTMLLIElement>(null);
  const titleRef = useRef<HTMLSpanElement>(null);
  // Whether the title is cut right now. Measured as the pointer or focus arrives,
  // when the ⋯ button has taken its room, so only a cut title offers its tooltip.
  const [cut, setCut] = useState(false);
  const measure = () => {
    const el = titleRef.current;
    setCut(!!el && el.scrollWidth > el.clientWidth);
  };
  const problemId = useId();
  const title = entry.title || "New conversation";

  const start = () => { setValue(entry.title); setProblem(null); setEditing(true); };
  // Back on the row's ⋯ menu, where Rename was chosen (IR-1253).
  const stop = () => {
    setEditing(false);
    setProblem(null);
    requestAnimationFrame(() => rowRef.current?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')?.focus());
  };
  const save = async () => {
    if (saving) return;
    if (value.trim() === entry.title) return stop();
    if (value.trim().length > TITLE_MAX) { setProblem(TITLE_TOO_LONG); return; }
    setSaving(true);
    const failure = await onRename!(entry.id, value);
    setSaving(false);
    if (failure) setProblem(failure);
    else stop();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); void save(); }
    else if (e.key === "Escape") { e.preventDefault(); stop(); }
  };

  if (editing) {
    return <li className="px-0.5 py-0.5">
      <input autoFocus value={value} onChange={e => { setValue(e.target.value); setProblem(null); }} onKeyDown={onKeyDown}
        disabled={saving} aria-label="Conversation title" aria-invalid={!!problem}
        aria-describedby={problem ? problemId : undefined}
        className="min-h-10 w-full rounded-control border border-brand/40 bg-surface px-3 text-body text-stone-900 focus:outline-none focus:ring-2 focus:ring-brand/30" />
      {problem && <p id={problemId} role="alert" className="px-1 pt-1 text-label text-brand-dark">{problem}</p>}
    </li>;
  }

  const items: RowMenuItem[] = [
    { key: "pin", label: pinned ? "Unpin" : "Pin", onSelect: onPin },
    ...(onRename ? [{ key: "rename", label: "Rename", onSelect: start }] : []),
    { key: "delete", label: "Delete", danger: true, onSelect: onDelete },
  ];

  // One line, ending in "…" when it doesn't fit: the seventh cut DESIGN.md's Full Text
  // Rule allows (IR-1253). The whole title stays the link's accessible name, shows in a
  // tooltip on hover and keyboard focus while it is cut (a `title` alone would not show
  // on focus), and the conversation shows it. Never wrapping is what keeps the row's
  // height still when the ⋯ menu appears on hover; wrapped, a long title reflowed.
  return <li ref={rowRef} onMouseEnter={measure} onFocus={measure}
    className={cn("group relative flex items-center rounded-control",
      active ? HERE : cn("text-stone-700", MAROON_HOVER))}>
    <Tooltip label={title} disabled={!cut} className="block min-w-0 flex-1">
      {/* A link to the conversation's own address (IR-548), so it opens in a new tab and survives a refresh. */}
      <Link to={`/ai/conversations/${entry.id}`} aria-current={active ? "page" : undefined}
        className={cn("block min-h-10 min-w-0 rounded-control px-3 py-2 text-left",
          "group-hover:pr-10 group-focus-within:pr-10 group-has-[[aria-expanded=true]]:pr-10", FOCUS_RING)}>
        <span ref={titleRef} className={cn("block truncate text-body", active ? "font-semibold" : "font-normal")}>{title}</span>
        {updatedAt && <span className="sr-only">{formatDate(updatedAt, "MMM d · h:mm a")}</span>}
      </Link>
    </Tooltip>
    {/* Shown on hover and focus, and kept while its menu is open; always shown on touch. */}
    <span className="absolute right-1 flex items-center opacity-0 transition-opacity
      group-hover:opacity-100 focus-within:opacity-100 has-[[aria-expanded=true]]:opacity-100
      [@media(hover:none)]:static [@media(hover:none)]:opacity-100">
      <RowMenu small label={`Actions for ${title}`} items={items} />
    </span>
  </li>;
}

/**
 * Starts a new conversation (IR-1306): a quiet row under the search box, above
 * Pinned, laid out like the conversations it starts. It is the list's own action,
 * so it is not a filled button; the maroon wash on hover is the one the rows share.
 */
export function NewConversationButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={cn("group mt-1 flex min-h-10 w-full items-center gap-2.5 rounded-control px-3 text-left text-body font-medium text-stone-700",
        MAROON_HOVER, FOCUS_RING)}>
      <span aria-hidden className="inline-flex size-5 items-center justify-center rounded-full ring-1 ring-stone-300 text-stone-600
        transition-colors duration-150 group-hover:bg-brand group-hover:text-white group-hover:ring-brand">
        <i className="fas fa-plus text-3xs" />
      </span>
      New conversation
    </button>
  );
}

/**
 * Older conversations, a page at a time (IR-1306). A quiet full-width row that
 * says what it brings in, with the IRIS mark while it does.
 */
function LoadOlder({ loading, onClick }: { loading: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} disabled={loading} aria-busy={loading}
      className={cn("group mt-2 flex min-h-10 w-full items-center justify-center gap-2 rounded-control border border-dashed border-stone-300 px-3",
        "text-small font-medium text-stone-600 hover:border-brand/40 disabled:cursor-wait disabled:opacity-80",
        MAROON_HOVER, FOCUS_RING)}>
      {loading
        ? <><IrisLoader className="size-4 text-brand" />Loading older conversations…</>
        : <>Show older conversations
          <i aria-hidden className="fas fa-arrow-down text-3xs transition-transform duration-150 group-hover:translate-y-0.5 motion-reduce:transition-none" /></>}
    </button>
  );
}
