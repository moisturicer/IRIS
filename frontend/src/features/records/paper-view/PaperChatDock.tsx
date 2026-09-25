import { useEffect, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import type { RecordDetail } from "@/types/records";
import type { ChatMessage } from "@/types/chat";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import { AskIrisEmblem, AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { ChatMessageBubble } from "@/features/ai/components/ChatMessageBubble";
import { StreamingMessageBubble } from "@/features/ai/components/StreamingMessageBubble";
import { useAskStream } from "@/features/ai/hooks/useAskStream";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { PANE_HEIGHT, PANE_TOP } from "./paneLayout";

export type DockMode = "left" | "right" | "floating";

export const DOCK_KEY = "iris_paper_chat_dock";

function readDock(): DockMode {
  try {
    const v = localStorage.getItem(DOCK_KEY);
    return v === "left" || v === "right" || v === "floating" ? v : "floating";
  } catch {
    return "floating";
  }
}

/**
 * Open/position state for Paper Chat.
 *
 * This lives in the page rather than the panel because a *docked* panel takes
 * part in the page layout — the page has to know the mode in order to make room
 * for it. Only the floating mode overlays.
 */
export function usePaperChat() {
  const [open, setOpen] = useState(false);
  const [dock, setDock] = useState<DockMode>(readDock);

  const setDockMode = (mode: DockMode) => {
    setDock(mode);
    try {
      localStorage.setItem(DOCK_KEY, mode);
    } catch {
      /* per-browser convenience only */
    }
  };

  return { open, setOpen, dock, setDockMode };
}

/** Closed-state affordance. Floats clear of the content in every dock mode. */
export function PaperChatLauncher({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title="Ask IRIS about this paper"
      className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 h-14 pl-3 pr-3 sm:pr-5 rounded-full bg-white ring-1 ring-stone-200 shadow-card-md hover:ring-brand/40 hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 transition-all duration-200"
    >
      <AskIrisEmblem className="w-8 h-8" />
      {/* The visible label is the accessible name (WCAG 2.5.3); below `sm`
          it stays in the tree for screen readers but not on screen. */}
      <span className="sr-only sm:not-sr-only text-sm font-semibold text-stone-800">Ask about this paper</span>
    </button>
  );
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

interface PaperChatPanelProps {
  record: RecordDetail;
  dock: DockMode;
  onDockChange: (mode: DockMode) => void;
  onClose: () => void;
  /** Positioning is the caller's job — the panel only styles its own interior. */
  className?: string;
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
 */
export function PaperChatPanel({
  record,
  dock,
  onDockChange,
  onClose,
  className,
}: PaperChatPanelProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [widen, setWiden] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const { streaming, ask } = useAskStream();

  // Find or start the Conversation for this Record. Re-runs if the reader
  // navigates to a different paper while the panel stays open.
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setWiden(false);

    (async () => {
      try {
        const { data: conversation } = await aiApi.conversations.findOrCreateForRecord(record.id);
        if (cancelled) return;
        setConversationId(conversation.id);
        setMessages(conversation.turns.flatMap(turnToMessages));
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => { cancelled = true; };
  }, [record.id]);

  // Scroll the transcript itself, never with `scrollIntoView` (IR-351): that
  // scrolls every scrollable ancestor too, the window included, and threw a
  // reader at page 6 back to the top of the paper just for opening the panel.
  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [messages, busy, streaming]);

  const send = async () => {
    const question = input.trim();
    if (!question || busy || !conversationId) return;

    setInput("");
    setMessages((prev) => [...prev, newChatMessage("user", question)]);
    setBusy(true);
    try {
      const { message } = await ask(question, { conversationId, widen });
      setMessages((prev) => [...prev, message]);
    } catch {
      setMessages((prev) => [
        ...prev,
        newChatMessage("assistant", "IRIS could not answer right now."),
      ]);
    } finally {
      setBusy(false);
    }
  };

  const chooseStarter = (question: string) => {
    setInput(question);
    composerRef.current?.focus();
  };

  return (
    <aside
      className={cn(
        "bg-white ring-1 ring-stone-200 flex flex-col overflow-hidden",
        className,
      )}
      aria-label="Paper Chat"
    >
      {/* Header: what this is (labelled AI, always), which paper, and
          what the answers are drawn from (IR-356). */}
      <div className="shrink-0 border-b border-stone-200">
        <div className="flex items-center gap-3 px-4 pt-3 pb-2">
          <span className="w-9 h-9 rounded-full bg-brand/10 flex items-center justify-center shrink-0" aria-hidden>
            <AskIrisMark className="w-5 h-5 text-brand" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-2 leading-tight">
              <span className="font-display text-lg font-semibold text-stone-900">Paper Chat</span>
              <span className="px-1.5 py-0.5 rounded-full bg-brand-50 text-brand text-2xs font-semibold ring-1 ring-brand-200">
                IRIS AI
              </span>
            </p>
            <p className="text-2xs text-stone-500 truncate">{record.title}</p>
          </div>

          <div className="relative">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Panel position"
              aria-expanded={menuOpen}
              title="Panel position"
            >
              <i className="fas fa-ellipsis" aria-hidden />
            </Button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-44 bg-white rounded-xl shadow-card-md ring-1 ring-stone-200 py-1 z-50">
                {(
                  [
                    { id: "left", label: "Dock left", icon: "fa-arrow-left" },
                    { id: "right", label: "Dock right", icon: "fa-arrow-right" },
                    { id: "floating", label: "Floating", icon: "fa-window-restore" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      onDockChange(opt.id);
                      setMenuOpen(false);
                    }}
                    className="w-full flex items-center justify-between gap-2 px-3 min-h-11 text-sm text-stone-700 hover:bg-stone-50"
                  >
                    <span className="flex items-center gap-2">
                      <i className={cn("fas", opt.icon, "text-2xs text-stone-500")} aria-hidden />
                      {opt.label}
                    </span>
                    {dock === opt.id && <i className="fas fa-check text-brand text-2xs" aria-hidden />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close Paper Chat">
            <i className="fas fa-xmark" aria-hidden />
          </Button>
        </div>

        {/* The scope control (IR-298, ADR-026 section 9): visible, and the
            only thing that ever widens retrieval past this paper. Resets to
            "this paper" whenever the panel switches to a different one. */}
        <div className="flex items-center gap-2 px-4 pb-2.5 text-2xs text-stone-500">
          <span>Answers from</span>
          <button
            type="button"
            onClick={() => setWiden((v) => !v)}
            aria-pressed={widen}
            title={widen ? "Searching every paper — click to search only this one" : "Searching only this paper — click to search every paper"}
            className={cn(
              "inline-flex items-center gap-1.5 font-semibold px-3 min-h-11 lg:min-h-7 rounded-full ring-1 transition-colors duration-200",
              widen
                ? "bg-brand text-white ring-brand"
                : "bg-white text-stone-700 ring-stone-300 hover:ring-brand/40 hover:text-brand",
            )}
          >
            <i className="fas fa-layer-group text-2xs" aria-hidden />
            {widen ? "All papers" : "This paper"}
          </button>
        </div>
      </div>

      {/* Transcript */}
      <div ref={transcriptRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-5 bg-stone-50/60">
        {ready && messages.length === 0 && (
          <div className="py-4 text-center">
            <AskIrisEmblem className="w-12 h-12 mx-auto mb-3" />
            <p className="font-display text-xl font-semibold text-stone-900">Ask about this paper</p>
            <p className="text-sm text-stone-600 leading-relaxed mt-1 px-2">
              {widen
                ? "Answers come from every paper in the repository, with citations you can open."
                : "Answers come from this paper’s own text, with citations you can open."}
            </p>
            <div role="group" aria-label="Suggested questions" className="mt-5 flex flex-col gap-2 text-left">
              {STARTER_QUESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => chooseStarter(question)}
                  className="min-h-11 px-3.5 py-2.5 rounded-xl bg-white ring-1 ring-stone-200 text-sm text-stone-700 hover:ring-brand/40 hover:text-brand transition-colors duration-200"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatMessageBubble key={m.id} message={m} compact />
        ))}

        {busy && streaming && <StreamingMessageBubble state={streaming} compact />}
      </div>

      {/* Composer */}
      <div className="shrink-0 border-t border-stone-200 bg-white p-3">
        <div className="flex items-end gap-2 rounded-2xl bg-stone-50 ring-1 ring-stone-200 focus-within:bg-white focus-within:ring-2 focus-within:ring-brand/40 pl-3.5 pr-1.5 py-1.5 transition-colors duration-200">
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
            aria-label="Ask about this paper"
            placeholder="Ask about methodology, findings, datasets…"
            className="flex-1 resize-none bg-transparent py-1.5 text-sm text-stone-800 placeholder-stone-500 outline-none"
          />
          <button
            type="button"
            onClick={send}
            disabled={!input.trim() || busy || !conversationId}
            aria-label="Send"
            className="w-11 h-11 lg:w-9 lg:h-9 shrink-0 rounded-full bg-brand text-white flex items-center justify-center hover:bg-brand-light disabled:opacity-30 transition-colors duration-200"
          >
            <i className="fas fa-arrow-up text-xs" aria-hidden />
          </button>
        </div>
        <p className="mt-1.5 px-1 text-2xs text-stone-500">Enter to send · Shift+Enter for a new line</p>
      </div>
    </aside>
  );
}

/**
 * Positioning for a docked panel.
 *
 * Docked means *in flow*: at `lg` and up the panel becomes a sticky column
 * beside the page content, so it can never cover the app sidebar, the header,
 * or the record's own rail. Below `lg` there is no room for a second column,
 * so it falls back to a bottom sheet.
 *
 * It shares the reader pane's offsets (`paneLayout.ts`): it sits below the
 * fixed header, so its own header and composer are never hidden (IR-351),
 * and it is exactly as tall as the reader beside it (IR-352).
 */
export const DOCKED_PANEL_CLASS =
  "fixed inset-x-0 bottom-0 z-40 h-[70vh] rounded-t-2xl " +
  `lg:sticky lg:inset-x-auto lg:bottom-auto ${PANE_TOP} lg:z-auto ` +
  `${PANE_HEIGHT} lg:w-[22rem] lg:shrink-0 lg:rounded-2xl`;

/** Positioning for the floating panel — deliberately overlays the page. */
export const FLOATING_PANEL_CLASS =
  "fixed bottom-6 right-6 z-40 w-[min(94vw,26rem)] h-[min(80vh,34rem)] rounded-2xl shadow-card-md";
