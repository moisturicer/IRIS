import { useEffect, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import type { RecordDetail } from "@/types/records";
import type { ChatMessage } from "@/types/chat";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import { AskIrisEmblem, AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import { ChatMessageBubble } from "@/features/ai/components/ChatMessageBubble";
import { cn } from "@/lib/utils";

export type DockMode = "left" | "right" | "floating";

const DOCK_KEY = "iris_paper_chat_dock";

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
      aria-label="Open Paper Chat"
      title="Ask IRIS about this paper"
      className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-white border border-stone-200 shadow-card-md flex items-center justify-center hover:border-brand/40 transition-colors"
    >
      <AskIrisEmblem className="w-8 h-8" />
    </button>
  );
}

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
  const bottomRef = useRef<HTMLDivElement>(null);

  // Find or start the Conversation for this Record. Re-runs if the reader
  // navigates to a different paper while the panel stays open.
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setWiden(false);

    (async () => {
      try {
        const { data: existing } = await aiApi.conversations.list({ record: record.id });
        const conversation = existing[0]
          ? (await aiApi.conversations.get(existing[0].id)).data
          : (await aiApi.conversations.create({ record: record.id })).data;
        if (cancelled) return;
        setConversationId(conversation.id);
        setMessages(conversation.turns.flatMap(turnToMessages));
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => { cancelled = true; };
  }, [record.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async () => {
    const question = input.trim();
    if (!question || busy || !conversationId) return;

    setInput("");
    setMessages((prev) => [...prev, newChatMessage("user", question)]);
    setBusy(true);
    try {
      const { data } = await aiApi.ask(question, { conversationId, widen });
      setMessages((prev) => [
        ...prev,
        newChatMessage("assistant", data.answer ?? data.message ?? "No matching record found.", {
          citations: data.citations,
          sources:   data.sources,
          degraded:  data.degraded,
          widened:   data.widened,
        }),
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        newChatMessage("assistant", "IRIS could not answer right now."),
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside
      className={cn(
        "bg-white border border-stone-200 flex flex-col overflow-hidden",
        className,
      )}
      aria-label="Paper Chat"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-stone-200 shrink-0">
        <AskIrisMark className="w-4 h-4 text-brand shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-bold text-stone-900 leading-tight flex items-center gap-1.5">
            Paper Chat
            <span className="px-1.5 rounded bg-brand-50 text-brand text-[9px] font-bold border border-brand-200">
              IRIS AI
            </span>
          </p>
          <p className="text-[10px] text-stone-400 truncate">{record.title}</p>
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="Panel position"
            title="Panel position"
            className="p-1.5 rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          >
            <i className="fas fa-ellipsis text-[13px]" aria-hidden />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-card-md border border-stone-200 py-1 z-50">
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
                  className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-[12px] text-stone-700 hover:bg-stone-50"
                >
                  <span className="flex items-center gap-2">
                    <i className={cn("fas", opt.icon, "text-[10px] text-stone-400")} aria-hidden />
                    {opt.label}
                  </span>
                  {dock === opt.id && <i className="fas fa-check text-brand text-[10px]" aria-hidden />}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close Paper Chat"
          className="p-1.5 rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-700"
        >
          <i className="fas fa-xmark text-[13px]" aria-hidden />
        </button>
      </div>

      {/* Transcript */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-[#FBFCFD]">
        {ready && messages.length === 0 && (
          <div className="text-center py-8 px-4">
            <AskIrisEmblem className="w-10 h-10 mx-auto mb-3" />
            <p className="text-[12px] text-stone-500 leading-relaxed">
              Ask about this paper's methodology, findings or datasets. Answers are grounded in
              CIT-U records.
            </p>
          </div>
        )}

        {messages.map((m) => (
          <ChatMessageBubble key={m.id} message={m} />
        ))}

        {busy && (
          <div className="flex items-center gap-2 text-[12px] text-stone-400">
            <SynthesisIcon className="w-4 h-4" spinning />
            Searching the repository…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-stone-200 p-3 shrink-0">
        <textarea
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
          className="w-full resize-none bg-stone-50 border border-stone-200 rounded-xl px-3 py-2 text-[12px] text-stone-800 placeholder-stone-400 outline-none focus:bg-white focus:border-brand/40 transition-colors"
        />
        <div className="flex items-center justify-between mt-2">
          {/* The scope control (IR-298, ADR-026 §9): visible, and it is the
              only thing that ever widens retrieval past this paper. Resets
              to "this paper" whenever the panel switches to a different one. */}
          <button
            type="button"
            onClick={() => setWiden((v) => !v)}
            aria-pressed={widen}
            title={widen ? "Searching every paper — click to search only this one" : "Searching only this paper — click to search every paper"}
            className={cn(
              "flex items-center gap-1.5 text-[10px] font-semibold px-2 py-1 rounded-full border transition-colors",
              widen
                ? "bg-brand/10 text-brand border-brand/30"
                : "text-stone-400 border-stone-200 hover:text-stone-600",
            )}
          >
            <i className="fas fa-layer-group text-[9px]" aria-hidden />
            {widen ? "All papers" : "This paper"}
          </button>
          <button
            type="button"
            onClick={send}
            disabled={!input.trim() || busy || !conversationId}
            aria-label="Send"
            className="w-8 h-8 rounded-full bg-brand text-white flex items-center justify-center hover:bg-brand-light disabled:opacity-30 transition-colors"
          >
            <i className="fas fa-arrow-up text-[11px]" aria-hidden />
          </button>
        </div>
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
 */
export const DOCKED_PANEL_CLASS =
  "fixed inset-x-0 bottom-0 z-40 h-[70vh] rounded-t-2xl " +
  "lg:sticky lg:inset-x-auto lg:bottom-auto lg:top-6 lg:z-auto " +
  "lg:h-[calc(100vh-3rem)] lg:w-[22rem] lg:shrink-0 lg:rounded-2xl";

/** Positioning for the floating panel — deliberately overlays the page. */
export const FLOATING_PANEL_CLASS =
  "fixed bottom-6 right-6 z-40 w-[min(94vw,26rem)] h-[min(80vh,34rem)] rounded-2xl shadow-card-md";
