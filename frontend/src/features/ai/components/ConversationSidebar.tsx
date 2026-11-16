import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { Link } from "react-router-dom";
import { cn, formatDate } from "@/lib/utils";
import { TITLE_MAX, TITLE_TOO_LONG, type ReaderConversationSummary } from "@/api/runtimeReader";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { HERE } from "@/components/ui/highlightRoles";
import { EarlierConversationList } from "./EarlierConversations";
import { usePinnedConversations, type Pin } from "../hooks/usePinnedConversations";

/** The history search and paging, from `useConversationHistory`. */
export interface HistorySearch {
  text:        string;
  onText:      (text: string) => void;
  query:       string;
  state:       "loading" | "ready" | "error";
  hasMore:     boolean;
  loadingMore: boolean;
  onMore:      () => void;
}

/** Saves a title; resolves to a message for the reader, or null once saved (IR-1160). */
export type RenameConversation = (id: string, title: string) => Promise<string | null>;

export const SIDEBAR_MIN = 220;
export const SIDEBAR_MAX = 480;
export const SIDEBAR_DEFAULT = 280;

interface ConversationSidebarProps {
  conversations:    ReaderConversationSummary[];
  activeId:         string | null;
  open:             boolean;
  search:           HistorySearch;
  onDelete:         (id: string) => void;
  onRename:         RenameConversation;
  onNewChat:        () => void;
  onCollapse:       () => void;
  /** The column's width, which the reader drags or arrows (`SIDEBAR_MIN`–`SIDEBAR_MAX`). */
  width:            number;
  onResize:         (width: number) => void;
}

const NAV_ITEM =
  "flex min-h-10 w-full min-w-0 items-center gap-3 rounded-control px-3 text-body text-stone-700 " +
  "hover:bg-stone-200/70 hover:text-stone-900 " + COLOUR_TRANSITION + " " + FOCUS_RING;

export function ConversationSidebar({
  conversations, activeId, open, search, onDelete, onRename, onNewChat, onCollapse, width, onResize,
}: ConversationSidebarProps) {
  return (
    <aside
      style={{ width: open ? width : 0 }}
      className={cn(
        "relative shrink-0 flex flex-col bg-stone-50",
        // `invisible` also drops the collapsed panel out of the tab order.
        open ? "border-r border-stone-200" : "border-r-0 invisible overflow-hidden",
      )}
      aria-label="Chat history"
      aria-hidden={!open}
    >
      <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
        <ConversationHistoryList conversations={conversations} activeId={activeId} search={search}
          onDelete={onDelete} onRename={onRename} onNewChat={onNewChat} onCollapse={onCollapse} />
      </div>
      {open && <SidebarResizer width={width} onChange={onResize} />}
    </aside>
  );
}

/** The column's right edge: drag, or arrow keys; double-click resets. */
function SidebarResizer({ width, onChange }: { width: number; onChange: (width: number) => void }) {
  const clamp = (n: number) => Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, Math.round(n)));
  return <div
    role="separator" aria-orientation="vertical" aria-label="Resize chat history"
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
 * New chat, Search (IR-1161), Pinned and Recents, each Conversation a link to
 * its own address with Pin, Rename (IR-1160) and Delete. Beside the answer on
 * a wide page, and in the history drawer on a phone (IR-570).
 */
export function ConversationHistoryList({
  conversations, activeId, search, onDelete, onRename, onNewChat, onCollapse,
}: {
  conversations: ReaderConversationSummary[];
  activeId:      string | null;
  search:        HistorySearch;
  onDelete:      (id: string) => void;
  /** Absent, a row offers no Rename. */
  onRename?:     RenameConversation;
  onNewChat?:    () => void;
  onCollapse?:   () => void;
}) {
  const searchId = useId();
  const searchRef = useRef<HTMLInputElement>(null);
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
      {onNewChat && <div className="flex items-center gap-1">
        <button type="button" onClick={onNewChat} className={NAV_ITEM}>
          <i className="fas fa-plus w-4 text-center text-label" aria-hidden />
          <span className="font-medium">New chat</span>
        </button>
        {onCollapse && <button type="button" onClick={onCollapse} aria-label="Hide chat history" title="Hide history"
          className={cn("inline-flex size-10 shrink-0 items-center justify-center rounded-control text-stone-500 transition-colors hover:bg-stone-200/70 hover:text-stone-800", FOCUS_RING)}>
          <i className="fas fa-angles-left text-small" aria-hidden />
        </button>}
      </div>}
      <label htmlFor={searchId} className={cn(NAV_ITEM, "cursor-text focus-within:bg-stone-200/70")}>
        <i className="fas fa-magnifying-glass w-4 text-center text-label" aria-hidden />
        <span className="sr-only">Search your past conversations</span>
        <input id={searchId} ref={searchRef} type="search" value={search.text} onChange={e => search.onText(e.target.value)}
          onKeyDown={e => { if (e.key === "Escape") { search.onText(""); e.currentTarget.blur(); } }}
          placeholder="Search" autoComplete="off" maxLength={200}
          className="min-w-0 flex-1 bg-transparent text-body text-stone-900 placeholder:text-stone-700 focus:outline-none" />
        <kbd aria-hidden className="shrink-0 font-sans text-2xs text-stone-500">Ctrl+K</kbd>
      </label>
      <p role="status" aria-live="polite" className="px-3 text-label text-stone-600">
        {search.query && search.state === "ready" ? `${conversations.length}${search.hasMore ? "+" : ""} found` : ""}
      </p>
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
      {search.state === "error" && (
        <p className="px-3 py-3 text-small text-stone-700">Could not load your conversations. Try again.</p>
      )}
      {conversations.length === 0 && search.state === "ready" && (
        <p className="px-3 py-6 text-small text-stone-500 text-center">
          {search.query ? `No conversations match “${search.query}”.` : "Your past chats will appear here."}
        </p>
      )}
      {recents.length > 0 && <nav aria-label="Past conversations">
        <ul className="space-y-0.5">{recents.map(c => row(c, c.updated_at))}</ul>
      </nav>}
      {search.hasMore && (
        <button type="button" onClick={search.onMore} disabled={search.loadingMore}
          className="mt-1 min-h-11 w-full rounded-card text-small text-brand underline focus-visible:outline-brand">
          {search.loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
    {/* Conversations Django answered before IR-957, read-only. */}
    <EarlierConversationList />
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
  const renameRef = useRef<HTMLButtonElement>(null);
  const problemId = useId();
  const title = entry.title || "New conversation";

  const start = () => { setValue(entry.title); setProblem(null); setEditing(true); };
  const stop = () => { setEditing(false); setProblem(null); requestAnimationFrame(() => renameRef.current?.focus()); };
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

  return <li className={cn("group relative flex items-center rounded-control",
    active ? HERE : "text-stone-700 hover:bg-stone-200/70")}>
    {/* A link to the conversation's own address (IR-548), so it opens in a new tab and survives a refresh. */}
    <Link to={`/ai/conversations/${entry.id}`} aria-current={active ? "page" : undefined} title={title}
      className={cn("block min-h-10 min-w-0 flex-1 rounded-control px-3 py-2 text-left", FOCUS_RING)}>
      <span className={cn("block truncate text-body", active ? "font-semibold" : "font-normal")}>{title}</span>
      {updatedAt && <span className="sr-only">{formatDate(updatedAt, "MMM d · h:mm a")}</span>}
    </Link>
    <span className="absolute right-1 flex items-center rounded-control opacity-0 transition-opacity
      group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:static [@media(hover:none)]:opacity-100">
      <RowAction label={pinned ? `Unpin ${title}` : `Pin ${title}`} hint={pinned ? "Unpin" : "Pin"} onClick={onPin}>
        <i className={cn("fas fa-thumbtack text-2xs", pinned && "text-brand")} aria-hidden />
      </RowAction>
      {onRename && <RowAction label={`Rename ${title}`} hint="Rename" onClick={start} buttonRef={renameRef}>
        <i className="fas fa-pen text-2xs" aria-hidden />
      </RowAction>}
      <RowAction label={`Delete ${title}`} hint="Delete" onClick={onDelete}>
        <i className="fas fa-trash text-2xs" aria-hidden />
      </RowAction>
    </span>
  </li>;
}

function RowAction({ label, hint, onClick, children, buttonRef }: {
  label: string; hint: string; onClick: () => void; children: ReactNode; buttonRef?: Ref<HTMLButtonElement>;
}) {
  return <button ref={buttonRef} type="button" onClick={onClick} aria-label={label} title={hint}
    className={cn("flex size-7 items-center justify-center rounded-control text-stone-500 hover:bg-stone-300/60 hover:text-stone-900",
      "[@media(hover:none)]:size-11", FOCUS_RING)}>
    {children}
  </button>;
}

/** Starts a new conversation; heads the history list wherever it is shown. */
export function NewChatButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="inline-flex min-h-10 min-w-0 flex-1 items-center justify-center gap-2 rounded-card bg-brand px-3 text-control font-semibold text-white transition-colors hover:bg-brand-dark">
      <i className="fas fa-plus text-label" aria-hidden />
      New chat
    </button>
  );
}
