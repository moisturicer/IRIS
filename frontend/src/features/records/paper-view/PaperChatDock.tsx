import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { aiApi } from "@/api/ai";
import type { RecordDetail } from "@/types/records";
import type { SemanticSearchResult } from "@/types/ai";
import { AskIrisEmblem, AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import { cn } from "@/lib/utils";

export type DockMode = "left" | "right" | "floating";

const DOCK_KEY = "iris_paper_chat_dock";

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SemanticSearchResult[];
}

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
 * Paper Chat — Ask IRIS scoped to the record being viewed.
 *
 * Questions are prefixed with the record's title so retrieval is anchored on
 * this paper. Answers come from the same grounded endpoint as Ask IRIS, so a
 * cited record is always one the reader can open.
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
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const send = async () => {
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setTurns((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: question }]);
    setBusy(true);
    try {
      const { data } = await aiApi.ask(`${record.title}. ${question}`);
      setTurns((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.answer ?? data.message ?? "No matching record found.",
          sources: data.sources,
        },
      ]);
    } catch {
      setTurns((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "IRIS could not answer right now.",
        },
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
        {turns.length === 0 && (
          <div className="text-center py-8 px-4">
            <AskIrisEmblem className="w-10 h-10 mx-auto mb-3" />
            <p className="text-[12px] text-stone-500 leading-relaxed">
              Ask about this paper's methodology, findings or datasets. Answers are grounded in
              CIT-U records.
            </p>
          </div>
        )}

        {turns.map((turn) =>
          turn.role === "user" ? (
            <div key={turn.id} className="flex justify-end">
              <p className="max-w-[85%] bg-brand text-white rounded-2xl rounded-br-sm px-3 py-2 text-[12px] leading-relaxed">
                {turn.content}
              </p>
            </div>
          ) : (
            <div
              key={turn.id}
              className="bg-white border border-stone-200 rounded-2xl rounded-bl-sm px-3 py-2.5"
            >
              <p className="text-[12px] text-stone-700 whitespace-pre-wrap leading-relaxed">
                {turn.content}
              </p>
              {turn.sources && turn.sources.length > 0 && (
                <div className="mt-2.5 pt-2 border-t border-stone-100">
                  <p className="text-[9px] font-bold uppercase tracking-wider text-stone-400 mb-1.5">
                    Referenced source{turn.sources.length === 1 ? "" : "s"}
                  </p>
                  {turn.sources.slice(0, 3).map((s) => (
                    <Link
                      key={s.id}
                      to={`/records/${s.id}`}
                      className="block bg-stone-50 border border-stone-200 rounded-lg px-2.5 py-1.5 mb-1.5 hover:border-brand/30 transition-colors"
                    >
                      <span className="block text-[11px] font-semibold text-stone-800 truncate">
                        {s.title}
                      </span>
                      <span className="text-[10px] text-stone-400">
                        Record #{s.id} · View Paper →
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ),
        )}

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
          <span className="flex items-center gap-1.5 text-[10px] text-stone-400">
            <i className="fas fa-file-lines text-[9px]" aria-hidden />
            Referencing this paper
          </span>
          <button
            type="button"
            onClick={send}
            disabled={!input.trim() || busy}
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
