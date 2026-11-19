import { NotificationBell } from "@/components/layout/NotificationBell";
import { DownloadConversation } from "./DownloadConversation";
import type { ConversationFile } from "@/api/runtimeReader";
import { ConversationsToggle, SOURCES_TOGGLE_CLASS } from "./ConversationSidebar";
import { PanelRightIcon } from "./AskIrisIcons";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/utils";

interface ChatToolbarProps {
  sessionTitle:     string;
  /**
   * On a phone only (IR-1233): the pane is not beside the chat, so the header
   * carries the way to it, opening it as a dialog over the answer. Absent on
   * wider pages, where the pane's own toggle is the only one.
   */
  phoneHistory?:    { open: boolean; onOpen: () => void };
  /**
   * The Sources panel's toggle (IR-1237), at the header's right edge: named Show or
   * Hide sources, with `aria-expanded`, and `aria-controls` while it sits beside the chat.
   */
  sources?:         { open: boolean; onToggle: () => void; controls?: string; asDialog: boolean };
  /** The open Conversation as Markdown (IR-1167); absent for a new chat. */
  onDownload?:      () => Promise<ConversationFile>;
}

export function ChatToolbar({
  sessionTitle,
  phoneHistory,
  sources,
  onDownload,
}: ChatToolbarProps) {
  // min-h-[56px] is shared with ConversationSidebar's header so both border-b
  // rules land on the same line -- this toolbar's two-line title block made it
  // naturally taller, and the divider visibly stepped down at the split.
  return (
    <header className="shrink-0 flex items-center gap-2 px-3 py-2.5 min-h-[56px] border-b border-stone-200/80">
      {phoneHistory && <ConversationsToggle open={phoneHistory.open} onClick={phoneHistory.onOpen} asDialog />}

      <div className="min-w-0 flex-1 px-1">
        <p className="text-label font-semibold text-stone-600">
          Ask IRIS
        </p>
        <h1 className="break-words text-body font-semibold text-stone-900">{sessionTitle}</h1>
      </div>

      {onDownload && <DownloadConversation download={onDownload} />}

      {sources && <Tooltip label={sources.open ? "Hide sources" : "Show sources"} className="shrink-0">
        <button type="button" onClick={sources.onToggle} aria-label={sources.open ? "Hide sources" : "Show sources"}
          aria-expanded={sources.open} aria-controls={sources.open ? sources.controls : undefined}
          aria-haspopup={sources.asDialog ? "dialog" : undefined}
          className={cn(SOURCES_TOGGLE_CLASS, sources.asDialog && "size-11")}>
          <PanelRightIcon />
        </button>
      </Tooltip>}


      {/* Phones only: Ask IRIS fills the window, so AppShell draws no phone bar
          here, and this is where the bell goes instead. On a desktop the bell
          is at the top of the sidebar (IR-519). Same component, same store. */}
      <div className="md:hidden">
        <NotificationBell />
      </div>
    </header>
  );
}
