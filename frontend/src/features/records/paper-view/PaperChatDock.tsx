import { useId, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type Ref } from "react";
import type { RecordDetail } from "@/types/records";
import type { AnswerReturn } from "@/lib/citedPage";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { RuntimeReader } from "@/features/ai/components/RuntimeReader";

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
  const storageKey = `iris-runtime-paper:${userId}:${props.record.id}`;
  const [conversationId, setConversationId] = useState<string | undefined>(() => {
    try { return sessionStorage.getItem(storageKey) ?? undefined; } catch { return undefined; }
  });
  const headingId = useId();
  return <aside ref={props.panelRef} style={props.style} tabIndex={-1} aria-labelledby={headingId}
    role={props.modal ? "dialog" : undefined} aria-modal={props.modal || undefined}
    className={cn("bg-canvas flex flex-col overflow-hidden", props.className)}>
    {props.resize && !props.minimized && <ResizeEdge {...props.resize} />}
    {props.minimized && <button type="button" onClick={props.onRestore} aria-label="Ask IRIS: back to the answer"
      className="min-h-14 px-4 text-left">Ask IRIS: back to the answer</button>}
    <header className="flex items-start justify-between gap-3 border-b border-stone-200 p-4" hidden={props.minimized}>
      <div className="min-w-0">
        {props.onBackToPaper && <button type="button" onClick={props.onBackToPaper}
          className="reading-split:hidden -ml-2 mb-1 inline-flex min-h-11 items-center gap-1 px-2 text-sm text-brand">
          <i className="fas fa-arrow-left text-2xs" aria-hidden />Back to paper
        </button>}
        <h2 id={headingId} className="font-display text-xl text-stone-900">Ask IRIS</h2>
        <p className="text-sm text-stone-600 break-words">{props.record.title}</p>
        <p className="text-xs text-stone-500">Research stays within this paper.</p></div>
      <button type="button" aria-label="Close Ask IRIS" className="min-h-11 px-2 text-sm" onClick={props.onClose}>Close</button>
    </header>
    {props.viewingVersion != null && <p className="px-4 py-2 text-xs text-stone-600">Answers are about the current version, not v{props.viewingVersion}.</p>}
    <div className={props.minimized ? "hidden" : "min-h-0 flex-1"}>
      <RuntimeReader conversationId={conversationId} recordId={props.record.id}
        initialDraft={props.draft} onDraftChange={props.onDraftChange} onConversation={id => {
        setConversationId(id);
        try { sessionStorage.setItem(storageKey, id); } catch { /* optional address convenience */ }
      }} />
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
