import { NotificationBell } from "@/components/layout/NotificationBell";

interface ChatToolbarProps {
  sessionTitle:     string;
  historyOpen:      boolean;
  onToggleHistory:  () => void;
  /**
   * History and sources open as drawers over the answer rather than beside it
   * (IR-570): the toggles say they open a dialog, and take a full 44px touch
   * target.
   */
  asDrawers?:       boolean;
}

export function ChatToolbar({
  sessionTitle,
  historyOpen,
  onToggleHistory,
  asDrawers = false,
}: ChatToolbarProps) {
  const touch = asDrawers ? "min-w-11 min-h-11 justify-center" : "";

  // min-h-[56px] is shared with ConversationSidebar's header so both border-b
  // rules land on the same line -- this toolbar's two-line title block made it
  // naturally taller, and the divider visibly stepped down at the split.
  return (
    <header className="shrink-0 flex items-center gap-2 px-3 py-2.5 min-h-[56px] border-b border-stone-200/80">
      {/* Beside the list the collapse control lives in the sidebar itself; here
          it is only the way back in, or the way to the drawer on a narrow page. */}
      {(asDrawers || !historyOpen) && <button
        type="button"
        onClick={onToggleHistory}
        className={`inline-flex items-center p-2 rounded-lg text-[13px] transition-colors ${touch}
          ${historyOpen
            ? "bg-stone-100 text-stone-800"
            : "text-stone-500 hover:bg-stone-50 hover:text-stone-800"
          }`}
        aria-pressed={asDrawers ? undefined : historyOpen}
        aria-expanded={historyOpen}
        aria-haspopup={asDrawers ? "dialog" : undefined}
        aria-label={historyOpen ? "Hide chat history" : "Show chat history"}
        title={historyOpen ? "Hide history" : "Show history"}
      >
        <i className={historyOpen ? "fas fa-angles-left" : "fas fa-bars-staggered"} aria-hidden />
      </button>}

      <div className="min-w-0 flex-1 px-1">
        <p className="text-[12px] font-semibold uppercase tracking-wider text-stone-600 truncate">
          Ask IRIS
        </p>
        <p className="text-[15px] font-semibold text-stone-900 truncate">{sessionTitle}</p>
      </div>


      {/* Phones only: Ask IRIS fills the window, so AppShell draws no phone bar
          here, and this is where the bell goes instead. On a desktop the bell
          is at the top of the sidebar (IR-519). Same component, same store. */}
      <div className="md:hidden">
        <NotificationBell />
      </div>
    </header>
  );
}
