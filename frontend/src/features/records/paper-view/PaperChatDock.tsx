import { useEffect, useId, useMemo, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type Ref } from "react";
import type { RecordDetail } from "@/types/records";
import type { AnswerReturn } from "@/lib/citedPage";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { runtimeReader, type ReaderConversationSummary } from "@/api/runtimeReader";
import { RuntimeReader } from "@/features/ai/components/RuntimeReader";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { Button } from "@/components/ui";
import { RecentChats } from "./RecentChats";
import { CONTROL_BASE, CONTROL_ON } from "./controls";

export const PANEL_WIDTH_KEY = "iris_ask_iris_width";

/** 360px, the first width, and a quarter more (IR-569). */
export const PANEL_WIDTH_DEFAULT = 450;
export const PANEL_WIDTH_MIN = 320;

function readWidth(): number {
  try {
    const n = Number(localStorage.getItem(PANEL_WIDTH_KEY));
    return n >= PANEL_WIDTH_MIN ? n : PANEL_WIDTH_DEFAULT;
  } catch {
    return PANEL_WIDTH_DEFAULT;
  }
}

/**
 * The reader's width, held to what the layout can spare: at most half the
 * workspace, and in the Paper workspace what leaves the paper 640px. Never
 * under the minimum.
 */
export function fitPanelWidth(preferred: number, room: number): number {
  return Math.round(Math.max(PANEL_WIDTH_MIN, Math.min(preferred, room)));
}

/**
 * Open and size state for Ask IRIS beside a paper.
 *
 * Held by the page, not the panel: the page lays out around it, and closing
 * the panel must keep the draft and the width the reader chose.
 */
export function usePaperChat() {
  const [open, setOpenState] = useState(false);
  // A followed citation tucks the panel away to a bar when it would cover the
  // passage (IR-354). Opening or closing always starts it unminimized.
  const [minimized, setMinimized] = useState(false);
  const [draft, setDraft] = useState("");
  const [width, setWidthState] = useState(readWidth);

  const setOpen = (next: boolean) => {
    setOpenState(next);
    setMinimized(false);
  };

  const setWidth = (next: number) => {
    const clamped = Math.round(Math.max(PANEL_WIDTH_MIN, next));
    setWidthState(clamped);
    try {
      localStorage.setItem(PANEL_WIDTH_KEY, String(clamped));
    } catch {
      /* per-browser convenience only */
    }
  };

  return { open, setOpen, minimized, setMinimized, draft, setDraft, width, setWidth };
}

/**
 * How the page's current record was reached (IR-355). `key` is unique per
 * navigation; `fromPaperChat` says it followed a citation inside this panel.
 */
export interface PaperChatArrival {
  key: string;
  fromPaperChat: boolean;
}

interface PaperChatPanelProps {
  /** The record the page is showing. */
  record: RecordDetail;
  /**
   * How the page got to `record`, or `null` while it is still loading the
   * record it is going to, when `record` is still the one it is leaving.
   * Absent, the panel stays on the paper it opened on.
   */
  arrival?: PaperChatArrival | null;
  onClose: () => void;
  /**
   * Tucked away to a bar, so the paper under the bottom sheet can be read
   * (IR-354). The conversation stays mounted, and where the transcript was
   * scrolled to comes back with it, so the reader returns to the answer
   * they followed a citation from.
   */
  minimized?: boolean;
  /** Activating the minimized bar. */
  onRestore?: () => void;
  /** Positioning is the caller's job — the panel only styles its own interior. */
  className?: string;
  /**
   * The earlier version the reader has open beside the chat, or null for
   * the current paper (IR-416). Answers are always about the current paper,
   * so the panel says so while an earlier one is open.
   */
  viewingVersion?: number | null;
  /** The composer's text, held by the page so a close keeps it (IR-569). */
  draft?: string;
  onDraftChange?: (draft: string) => void;
  /** One view at a time (IR-569): the way back to the paper. */
  onBackToPaper?: () => void;
  /** The panel itself, for the page to move focus into. */
  panelRef?: Ref<HTMLElement>;
  /** Over or instead of the paper (IR-569): a modal dialog, not a side panel. */
  modal?: boolean;
  /** Set by the page where the panel has a width of its own. */
  style?: CSSProperties;
  /** Where the reader drags the panel's edge; absent where it is not a column. */
  resize?: { width: number; max: number; onChange: (width: number) => void };
  /**
   * Back to the answer a citation was followed from (IR-578): that
   * Conversation, shown at that Turn. `key` makes a second request for the
   * same answer a request again.
   */
  returnTo?: AnswerReturn | null;
}

/**
 * Paper Chat: Ask IRIS scoped to the record being viewed. The AI runtime
 * answers it (IR-957), through the same reader as Ask IRIS, with research
 * kept to this paper. The conversation's address is held for this tab only.
 */
export function PaperChatPanel(props: PaperChatPanelProps) {
  return <RuntimePaperChatPanel key={props.record.id} {...props} />;
}

function RuntimePaperChatPanel(props: PaperChatPanelProps) {
  const userId = useAuthStore(s => s.user?.id);
  // Research kept to this paper, or across every paper the reader can read: each its own conversation.
  const [allPapers, setAllPapers] = useState(false);
  const storageKey = `iris-runtime-paper:${userId}:${props.record.id}${allPapers ? ":all" : ""}`;
  const [conversationId, setConversationId] = useState<string | undefined>(() => {
    try { return sessionStorage.getItem(storageKey) ?? undefined; } catch { return undefined; }
  });
  useEffect(() => {
    try { setConversationId(sessionStorage.getItem(storageKey) ?? undefined); } catch { setConversationId(undefined); }
  }, [storageKey]);
  const [fresh, setFresh] = useState(0);
  const [recent, setRecent] = useState<ReaderConversationSummary[]>([]);
  const [recentOpen, setRecentOpen] = useState(false);
  const api = useMemo(() => runtimeReader(props.record.id), [props.record.id]);
  const headingId = useId();

  // The reader's own chats about this paper. A failure shows none.
  useEffect(() => {
    let cancelled = false;
    void api.list().then(items => { if (!cancelled) setRecent(items.filter(c => c.record_id === props.record.id)); })
      .catch(() => { if (!cancelled) setRecent([]); });
    return () => { cancelled = true; };
  }, [api, props.record.id, conversationId]);

  const remember = (id: string | undefined) => {
    setConversationId(id);
    try { if (id) sessionStorage.setItem(storageKey, id); else sessionStorage.removeItem(storageKey); } catch { /* optional */ }
  };
  const newChat = () => { setRecentOpen(false); remember(undefined); setFresh(n => n + 1); };

  return <aside ref={props.panelRef} style={props.style} tabIndex={-1} aria-labelledby={headingId}
    role={props.modal ? "dialog" : undefined} aria-modal={props.modal || undefined}
    className={cn("bg-canvas flex flex-col overflow-hidden focus:outline-none motion-safe:animate-panel-in", props.className)}>
    {props.resize && !props.minimized && <ResizeEdge {...props.resize} />}
    {props.minimized && <button type="button" onClick={props.onRestore} aria-label="Ask IRIS: back to the answer"
      className="flex min-h-14 w-full items-center gap-3 px-4 py-2 text-left transition-colors duration-200 hover:bg-stone-100">
      <AskIrisMark className="h-5 w-5 shrink-0 text-brand" />
      <span className="min-w-0 flex-1">
        <span className="block font-display text-lg font-semibold leading-tight text-stone-900">Ask IRIS</span>
        <span className="block truncate text-2xs text-stone-500">Back to the answer</span>
      </span>
      <i className="fas fa-chevron-up text-xs text-stone-500" aria-hidden />
    </button>}

    <div className="shrink-0 border-b border-stone-200 bg-stone-100 px-4 pb-3 pt-3" hidden={props.minimized}>
      {props.onBackToPaper && <button type="button" onClick={props.onBackToPaper}
        className={cn("reading-split:hidden -ml-2 mb-1 px-2 text-brand", CONTROL_BASE)}>
        <i className="fas fa-arrow-left text-2xs" aria-hidden />Back to paper
      </button>}
      <div className="flex items-center gap-2">
        <AskIrisMark className="h-5 w-5 shrink-0 text-brand" />
        <h2 id={headingId} className="font-display text-xl font-semibold leading-none text-stone-900">Ask IRIS</h2>
        <span className="rounded border border-stone-300 px-1 text-3xs font-semibold uppercase tracking-wider text-stone-600">AI</span>
        <span className="flex-1" />
        <Button variant="ghost" size="icon" onClick={props.onClose} aria-label="Close Ask IRIS" className="-mr-2">
          <i className="fas fa-xmark" aria-hidden />
        </Button>
      </div>
      <p className="mt-2 truncate text-2xs text-stone-600">{props.record.title}</p>
      {props.viewingVersion != null && <p className="mt-1 text-2xs text-stone-700">
        Answers are about the current version, not v{props.viewingVersion}.</p>}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setRecentOpen(v => !v)} aria-expanded={recentOpen} disabled={recent.length === 0}
          className={cn("px-3", CONTROL_BASE, CONTROL_ON)}>
          Recent chats{recent.length > 0 ? ` (${recent.length})` : ""}
        </button>
        <button type="button" onClick={newChat} className={cn("px-3", CONTROL_BASE, CONTROL_ON)}>
          <i className="fas fa-plus text-2xs" aria-hidden />New chat
        </button>
      </div>
      {recentOpen && <RecentChats className="mt-2 max-h-48 overflow-y-auto" chats={recent} activeId={conversationId ?? null}
        onChoose={chat => { setRecentOpen(false); remember(chat.id); }} />}
    </div>

    <div className={props.minimized ? "hidden" : "min-h-0 flex-1"}>
      <RuntimeReader key={`${allPapers}:${conversationId ?? "new"}:${fresh}`} dense conversationId={conversationId}
        recordId={allPapers ? undefined : props.record.id}
        scopeToggle={{ allPapers, onChange: next => { setRecentOpen(false); setAllPapers(next); } }}
        initialDraft={props.draft} onDraftChange={props.onDraftChange} onConversation={remember} />
    </div>
  </aside>;
}

/**
 * The panel's left edge, which the reader drags (or arrows) to size it
 * (IR-569). The panel is anchored to the right, so its width is how far the
 * pointer is from the right edge.
 */
function ResizeEdge({
  width,
  max,
  onChange,
}: {
  width: number;
  max: number;
  onChange: (width: number) => void;
}) {
  const clampTo = (n: number) => Math.max(PANEL_WIDTH_MIN, Math.min(n, max));
  const drag = (e: PointerEvent<HTMLDivElement>) => {
    if (!e.currentTarget.hasPointerCapture?.(e.pointerId)) return;
    const right = e.currentTarget.parentElement?.getBoundingClientRect().right ?? 0;
    onChange(clampTo(right - e.clientX));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 80 : 24;
    if (e.key === "ArrowLeft") onChange(clampTo(width + step));
    else if (e.key === "ArrowRight") onChange(clampTo(width - step));
    else if (e.key === "Home") onChange(PANEL_WIDTH_MIN);
    else if (e.key === "End") onChange(max);
    else return;
    e.preventDefault();
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize Ask IRIS"
      aria-valuemin={PANEL_WIDTH_MIN}
      aria-valuemax={max}
      aria-valuenow={width}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={(e) => e.currentTarget.setPointerCapture?.(e.pointerId)}
      onPointerMove={drag}
      onDoubleClick={() => onChange(clampTo(PANEL_WIDTH_DEFAULT))}
      className="hidden reading-split:block absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none transition-colors hover:bg-brand/30 focus-visible:bg-brand/40 focus:outline-none"
    />
  );
}

/**
 * Ask IRIS in the Paper workspace (IR-569), by the workspace's width: the
 * whole workspace below `reading-split`; a drawer over the paper below
 * `reading-wide`; from there a flush column beside it. The page sets the
 * width of the last two (the reader's choice, held to leave the paper 640px).
 */
export const PAPER_WORKSPACE_PANEL_CLASS =
  "absolute inset-0 z-40 " +
  "reading-split:left-auto reading-split:border-l reading-split:border-stone-300 " +
  "reading-split:shadow-[-12px_0_32px_rgb(41_37_36/0.12)] " +
  "reading-wide:relative reading-wide:z-auto reading-wide:shadow-none reading-wide:shrink-0";

/**
 * Everywhere else on the record page: the same panel as a column the page
 * makes room for, so it never covers what it sits beside. Stuck below the
 * record bar and as tall as what is left of the window.
 */
export const DOCKED_PANEL_CLASS =
  "fixed inset-0 z-40 " +
  "reading-split:sticky reading-split:inset-auto reading-split:top-14 reading-split:z-20 reading-split:self-start " +
  "reading-split:h-[calc(100dvh-3.5rem)] reading-split:shrink-0 reading-split:border-l reading-split:border-stone-300";

/**
 * A minimized panel (IR-354): a bar along the bottom of the screen, no taller
 * than it needs, so a followed citation's passage is not under it. Only where
 * the panel would cover the paper; a column beside it is never minimized.
 */
export const MINIMIZED_SHEET_CLASS =
  "fixed inset-x-0 bottom-0 z-40 rounded-t-2xl border border-stone-200 shadow-card-md";
