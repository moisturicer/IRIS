interface ChatToolbarProps {
  sessionTitle:     string;
  historyOpen:      boolean;
  sourcesOpen:      boolean;
  sourcesAvailable: boolean;
  onToggleHistory:  () => void;
  onToggleSources:  () => void;
  onNewChat:        () => void;
}

export function ChatToolbar({
  sessionTitle,
  historyOpen,
  sourcesOpen,
  sourcesAvailable,
  onToggleHistory,
  onToggleSources,
  onNewChat,
}: ChatToolbarProps) {
  return (
    <header className="shrink-0 flex items-center gap-2 px-3 py-2.5 border-b border-stone-200/80 bg-white">
      <button
        type="button"
        onClick={onToggleHistory}
        className={`p-2 rounded-lg text-[12px] transition-colors
          ${historyOpen
            ? "bg-stone-100 text-stone-800"
            : "text-stone-500 hover:bg-stone-50 hover:text-stone-800"
          }`}
        aria-pressed={historyOpen}
        aria-expanded={historyOpen}
        aria-label={historyOpen ? "Hide chat history" : "Show chat history"}
        title={historyOpen ? "Hide history" : "Show history"}
      >
        <i className={historyOpen ? "fas fa-angles-left" : "fas fa-bars-staggered"} />
      </button>

      <div className="min-w-0 flex-1 px-1">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 truncate">
          Ask IRIS
        </p>
        <p className="text-[13px] font-semibold text-stone-900 truncate">{sessionTitle}</p>
      </div>

      <button
        type="button"
        onClick={onNewChat}
        className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold
          text-stone-600 hover:bg-stone-50 border border-stone-200"
      >
        <i className="fas fa-plus text-[10px]" />
        New chat
      </button>

      <button
        type="button"
        onClick={onToggleSources}
        disabled={!sourcesAvailable}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-colors
          ${sourcesOpen && sourcesAvailable
            ? "bg-[#6B0F12]/10 text-[#6B0F12] ring-1 ring-[#6B0F12]/20"
            : "text-stone-600 hover:bg-stone-50 border border-stone-200"
          }
          disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent`}
        aria-pressed={sourcesOpen}
        aria-label={sourcesOpen ? "Hide sources" : "Show sources"}
        title={sourcesAvailable ? (sourcesOpen ? "Hide sources" : "Show sources") : "Sources appear after IRIS responds"}
      >
        <i className="fas fa-layer-group text-[11px]" />
        <span className="hidden sm:inline">Sources</span>
      </button>
    </header>
  );
}
