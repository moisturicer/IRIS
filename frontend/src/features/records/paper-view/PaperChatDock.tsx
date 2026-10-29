import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type Ref } from "react";
import { aiApi } from "@/api/ai";
import type { RecordDetail } from "@/types/records";
import type { ChatMessage } from "@/types/chat";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import { CitationConversationContext, CitationOriginContext, type AnswerReturn } from "@/lib/citedPage";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { ChatMessageBubble } from "@/features/ai/components/ChatMessageBubble";
import { StreamingMessageBubble } from "@/features/ai/components/StreamingMessageBubble";
import { AskIrisNotice } from "@/features/ai/components/AskIrisNotice";
import { useAskStream } from "@/features/ai/hooks/useAskStream";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import {
  CONTROL_BASE,
  CONTROL_FILLED,
  CONTROL_ON,
  CONTROL_OUTLINE,
  CONTROL_SHAPE,
  CONTROL_SQUARE,
} from "./controls";

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
 * Where a reader who does not know what to ask can start (IR-356). They
 * fill the composer rather than sending, so the reader can edit one first.
 */
const STARTER_QUESTIONS = [
  "What problem does this paper address?",
  "Summarise the methodology",
  "What are the key findings?",
] as const;

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
 * The paper a Paper Chat conversation is about, and, when the reader came
 * back to one by its address, which of the paper's Conversations (IR-578).
 */
type ChatSubject = Pick<RecordDetail, "id" | "title"> & { conversationId?: number };

function subjectOf(record: RecordDetail): ChatSubject {
  return { id: record.id, title: record.title };
}

/**
 * Paper Chat — a Conversation scoped to the record being viewed (IR-298).
 *
 * Same model, same API as Ask IRIS (ADR-019): opening the panel finds or
 * starts the Conversation for this Record, and history persists across a
 * panel close, a reload, and another device. Retrieval is filtered to this
 * Record's own passages by default — the backend consults the Conversation's
 * `record`, not a title glued onto the question — until the reader turns on
 * "All papers" for a question that needs one.
 *
 * The conversation is about the paper it opened on, usually the page's
 * record. Following one of its citations to a different paper keeps it open,
 * pinned, so the reader does not lose the answer they followed (IR-355,
 * ADR-026 section 9 as amended). The pin holds only across that navigation:
 * "Chat about this paper instead", closing the panel, and reaching a paper
 * any other way all bring back the page's own record.
 */
export function PaperChatPanel({
  record,
  arrival,
  onClose,
  minimized = false,
  onRestore,
  className,
  viewingVersion = null,
  draft,
  onDraftChange,
  onBackToPaper,
  panelRef,
  modal = false,
  style,
  resize,
  returnTo = null,
}: PaperChatPanelProps) {
  const headingId = useId();
  const [ownInput, setOwnInput] = useState("");
  const input = draft ?? ownInput;
  const setInput = onDraftChange ?? setOwnInput;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [widen, setWiden] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const transcriptScrollTop = useRef(0);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const { streaming, ask, cancel } = useAskStream();
  const [subject, setSubject] = useState<ChatSubject>(() => subjectOf(record));
  const pinned = subject.id !== record.id;
  // Read after an answer arrives: the reader may have switched conversations
  // while it streamed, and it belongs to the one it was asked in.
  const subjectId = useRef(subject.id);
  subjectId.current = subject.id;
  /** The Conversation on screen, once there is one; its citations name it (IR-578). */
  const [conversationId, setConversationId] = useState<number | null>(null);
  const shownConversation = useRef<number | null>(null);
  shownConversation.current = conversationId;
  /** The Turn to show once the transcript has it (IR-578). */
  const pendingTurn = useRef<number | null>(null);

  // A citation followed from this panel keeps its conversation; any other
  // arrival brings the page's record. Decided once the page has the record
  // it was going to (`arrival` set), never against the one it is leaving.
  useEffect(() => {
    if (!arrival || arrival.fromPaperChat) return;
    setSubject((current) => (current.id === record.id ? current : subjectOf(record)));
    // `arrival.key` changes on every navigation, including a second visit
    // to the record already shown, which is still "another way" to it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record.id, arrival?.key]);

  // Find the subject's Conversation; none yet is an empty one, started by
  // the first question (IR-569). Re-runs when the subject changes, and
  // resets the scope with it: the conversation owns its scope, so the page
  // moving to another paper leaves it alone (IR-355).
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setWiden(false);
    // Nothing of the old conversation may receive or show anything meanwhile.
    setMessages([]);
    setConversationId(null);

    (async () => {
      try {
        const conversation = subject.conversationId
          ? (await aiApi.conversations.get(subject.conversationId)).data
          : await aiApi.conversations.findForRecord(subject.id);
        if (cancelled || !conversation) return;
        setConversationId(conversation.id);
        setMessages(conversation.turns.flatMap(turnToMessages));
      } catch {
        // No conversation to show: the panel starts empty, as with none yet.
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => { cancelled = true; };
  }, [subject.id, subject.conversationId]);

  // Back to an answer (IR-578). The one on screen scrolls to it; another is
  // opened first, about the paper it belongs to, which may not be this one.
  useEffect(() => {
    if (!returnTo) return;
    pendingTurn.current = returnTo.turnId;
    // On screen already: the scroll below, keyed by the same request, does it.
    if (shownConversation.current === returnTo.conversationId) return;
    let cancelled = false;
    aiApi.conversations
      .get(returnTo.conversationId)
      .then(({ data }) => {
        if (cancelled) return;
        setSubject({
          id: data.record ?? record.id,
          title: data.record_title ?? record.title,
          conversationId: data.id,
        });
      })
      .catch(() => { pendingTurn.current = null; });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [returnTo?.key]);

  /** The subject's Conversation, started now if this is its first question. */
  const conversationFor = async (askedAbout: number): Promise<number> => {
    if (subject.conversationId && subject.id === askedAbout) return subject.conversationId;
    const { data } = await aiApi.conversations.create({ record: askedAbout, reuse_default: true });
    if (subjectId.current === askedAbout) {
      // Another tab may have started this default after our initial GET.
      setConversationId(data.id);
      setMessages([...data.turns.flatMap(turnToMessages)]);
    }
    return data.id;
  };

  // Scroll the transcript itself, never with `scrollIntoView` (IR-351): that
  // scrolls every scrollable ancestor too, the window included, and threw a
  // reader at page 6 back to the top of the paper just for opening the panel.
  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) return;
    const turn = pendingTurn.current;
    const answer = turn == null ? null : transcript.querySelector(`[data-turn="${turn}"]`);
    if (answer) {
      // The answer returned to, at the top of the transcript (IR-578).
      pendingTurn.current = null;
      transcript.scrollTop += answer.getBoundingClientRect().top - transcript.getBoundingClientRect().top;
      transcriptScrollTop.current = transcript.scrollTop;
      return;
    }
    transcript.scrollTop = transcript.scrollHeight;
  }, [messages, busy, streaming, returnTo?.key]);

  // A hidden transcript has no scroll position of its own to keep, so the
  // last one seen is put back when the panel is restored, before it paints.
  useLayoutEffect(() => {
    const transcript = transcriptRef.current;
    if (!minimized && transcript) transcript.scrollTop = transcriptScrollTop.current;
  }, [minimized]);

  const sendQuestion = async (question: string, questionWiden: boolean) => {
    if (!question || sending.current || !ready) return;
    sending.current = true;
    const requestId = crypto.randomUUID();

    setBusy(true);
    const askedAbout = subject.id;
    // The answer is stored in the conversation it was asked in either way;
    // it is shown only if that is still the one on screen (IR-355).
    const show = (reply: ChatMessage) => {
      if (subjectId.current === askedAbout) setMessages((prev) => [...prev, reply]);
    };
    try {
      const conversationId = await conversationFor(askedAbout);
      if (subjectId.current === askedAbout) setMessages((prev) => [...prev, newChatMessage("user", question)]);
      const { message } = await ask(question, { conversationId, widen: questionWiden, requestId });
      show(message);
    } catch {
      show(newChatMessage("assistant", "IRIS could not answer right now."));
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };

  const send = () => {
    const question = input.trim();
    if (!question || busy || !ready) return;
    setInput("");
    return sendQuestion(question, widen);
  };

  const chooseStarter = (question: string) => {
    setInput(question);
    composerRef.current?.focus();
  };

  return (
    // The canvas behind one border; the heading, not a white card, says what
    // it is (IR-569). Focusable only by script, for the page's focus moves.
    <aside
      ref={panelRef}
      style={style}
      tabIndex={-1}
      role={modal ? "dialog" : undefined}
      aria-modal={modal || undefined}
      className={cn(
        "bg-canvas flex flex-col overflow-hidden focus:outline-none motion-safe:animate-panel-in",
        className,
      )}
      aria-labelledby={headingId}
    >
      {resize && !minimized && <ResizeEdge {...resize} />}

      {/* The minimized bar (IR-354): what this is, and one tap back to it.
          Its name is its two visible lines, so it is heard as Back to the
          answer (IR-570) and its visible label is in it (WCAG 2.5.3). */}
      {minimized && (
        <button
          type="button"
          onClick={onRestore}
          aria-label="Ask IRIS: back to the answer"
          className="flex items-center gap-3 w-full min-h-14 px-4 py-2 text-left hover:bg-stone-100 transition-colors duration-200"
        >
          <AskIrisMark className="w-5 h-5 text-brand shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="block font-display text-lg font-semibold text-stone-900 leading-tight">Ask IRIS</span>
            <span className="block text-2xs text-stone-500 truncate">Back to the answer</span>
          </span>
          <i className="fas fa-chevron-up text-xs text-stone-500" aria-hidden />
        </button>
      )}

      {/* What this is (an AI, said so), which paper, and the scope (IR-356). */}
      <div className="shrink-0 px-4 pt-3 pb-3 border-b border-stone-200 bg-stone-100" hidden={minimized}>
        {onBackToPaper && (
          // Only where the panel is the one view (below `reading-split`).
          <button
            type="button"
            onClick={onBackToPaper}
            className={cn("reading-split:hidden -ml-2 mb-1 px-2 text-brand", CONTROL_BASE)}
          >
            <i className="fas fa-arrow-left text-2xs" aria-hidden />
            Back to paper
          </button>
        )}
        <div className="flex items-center gap-2">
          <AskIrisMark className="w-5 h-5 text-brand shrink-0" />
          <h2 id={headingId} className="font-display text-xl font-semibold text-stone-900 leading-none">Ask IRIS</h2>
          <span className="px-1 rounded border border-stone-300 text-3xs font-semibold uppercase tracking-wider text-stone-500">
            AI
          </span>
          <span className="flex-1" />

          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close Ask IRIS" className="-mr-2">
            <i className="fas fa-xmark" aria-hidden />
          </Button>
        </div>

        <p className="mt-2 truncate text-2xs text-stone-500">
          {pinned ? `Chatting about ${subject.title}` : record.title}
        </p>
        {viewingVersion != null && !pinned && (
          <p className="mt-1 text-2xs text-stone-700">
            Answers are about the current version, not v{viewingVersion}.
          </p>
        )}

        {/* Pinned to another paper (IR-355): one step to this one's own. */}
        {pinned && (
          <button
            type="button"
            onClick={() => setSubject(subjectOf(record))}
            className={cn("mt-1 -ml-2 px-2 text-brand hover:bg-brand-50", CONTROL_BASE)}
          >
            <i className="fas fa-arrow-right-arrow-left text-2xs" aria-hidden />
            Chat about this paper instead
          </button>
        )}
      </div>

      {/* Transcript */}
      <div
        ref={transcriptRef}
        hidden={minimized}
        // Only while shown: hiding it is not the reader scrolling it.
        onScroll={minimized ? undefined : (e) => { transcriptScrollTop.current = e.currentTarget.scrollTop; }}
        className="flex-1 overflow-y-auto px-4 py-5 space-y-5"
      >
        {ready && messages.length === 0 && (
          <div className="pt-2">
            <p className="font-display text-2xl font-semibold leading-tight text-stone-900">Ask about this paper.</p>
            <p className="mt-2 text-small text-stone-600 leading-relaxed">
              {widen
                ? "Answers come from every paper in the repository, with citations you can open."
                : "Answers come from this paper’s own text, with citations that open the passage."}
            </p>
            <div role="group" aria-label="Suggested questions" className="mt-5 grid gap-2">
              {STARTER_QUESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => chooseStarter(question)}
                  className={cn("px-3 text-left font-normal hover:bg-brand-50", CONTROL_BASE, CONTROL_OUTLINE)}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Its citations say they came from here, which is what keeps this
            conversation open on the paper they lead to (IR-355). */}
        <CitationOriginContext.Provider value="paper-chat">
        <CitationConversationContext.Provider value={conversationId}>
          {messages.map((m) => (
            <ChatMessageBubble key={m.id} message={m} compact retryDisabled={busy || !ready} />
          ))}

          {busy && streaming && <StreamingMessageBubble state={streaming} compact onStop={() => void cancel()} />}
        </CitationConversationContext.Provider>
        </CitationOriginContext.Provider>
      </div>

      {/* Composer: the question, then its scope and Send (IR-569). */}
      <div className="shrink-0 border-t border-stone-200 p-3" hidden={minimized}>
        <div className="rounded-lg border border-stone-300 focus-within:border-brand/60 focus-within:ring-2 focus-within:ring-brand/20 transition-colors duration-200">
          <textarea
            ref={composerRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            // The composer's only label, so it names the pinned paper too:
            // a screen reader on Y must not hear "this paper" and mean X.
            aria-label={pinned ? `Ask about ${subject.title}` : "Ask about this paper"}
            placeholder="Ask about methodology, findings, datasets…"
            className="block w-full resize-none bg-transparent px-3 pt-2.5 text-sm text-stone-800 placeholder-stone-500 outline-none"
          />
          <div className="flex items-center justify-between gap-2 px-2 pb-2">
            {/* The scope control (IR-298, ADR-026 section 9): visible, and the
                only thing that ever widens retrieval past this paper. Resets
                with the conversation, not with the page's paper. */}
            <button
              type="button"
              onClick={() => setWiden((v) => !v)}
              aria-pressed={widen}
              title={
                widen
                  ? `Searching every paper — click to search only ${pinned ? subject.title : "this one"}`
                  : `Searching only ${pinned ? subject.title : "this paper"} — click to search every paper`
              }
              className={cn(
                "min-w-0 max-w-[14rem] px-3",
                CONTROL_BASE,
                widen ? CONTROL_FILLED : CONTROL_ON,
              )}
            >
              <span aria-hidden className={cn("w-1.5 h-1.5 rounded-full shrink-0", widen ? "bg-white" : "bg-brand")} />
              {/* While pinned, "this paper" would read as the one on screen, so
                  the chip names the conversation's own paper (IR-355). */}
              <span className="truncate">
                {widen ? "All papers" : pinned ? subject.title : "This paper"}
              </span>
            </button>
            <button
              type="button"
              onClick={send}
              disabled={!input.trim() || busy || !ready}
              aria-label="Send"
              className={cn("shrink-0 inline-flex items-center justify-center transition-colors duration-200", CONTROL_SQUARE, CONTROL_SHAPE, CONTROL_FILLED)}
            >
              <i className="fas fa-arrow-up text-xs" aria-hidden />
            </button>
          </div>
        </div>
        <p className="mt-1.5 px-1 text-2xs text-stone-500">Enter to send · Shift+Enter for a new line</p>
        <AskIrisNotice className="mt-1 px-1 text-2xs" />
      </div>
    </aside>
  );
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
