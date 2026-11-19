import { NotificationBell } from "@/components/layout/NotificationBell";
import { DownloadConversation } from "./DownloadConversation";
import type { ConversationFile } from "@/api/runtimeReader";
import { ConversationsToggle } from "./ConversationSidebar";

interface ChatToolbarProps {
  sessionTitle:     string;
  /**
   * On a phone only (IR-1233): the pane is not beside the chat, so the header
   * carries the way to it, opening it as a dialog over the answer. Absent on
   * wider pages, where the pane's own toggle is the only one.
   */
  phoneHistory?:    { open: boolean; onOpen: () => void };
  /** The open Conversation as Markdown (IR-1167); absent for a new chat. */
  onDownload?:      () => Promise<ConversationFile>;
}

export function ChatToolbar({
  sessionTitle,
  phoneHistory,
  onDownload,
}: ChatToolbarProps) {
  // min-h-[56px] is shared with ConversationSidebar's header so both border-b
  // rules land on the same line -- this toolbar's two-line title block made it
  // naturally taller, and the divider visibly stepped down at the split.
  return (
    <header className="shrink-0 flex items-center gap-2 px-3 py-2.5 min-h-[56px] border-b border-stone-200/80">
      {phoneHistory && <ConversationsToggle open={phoneHistory.open} onClick={phoneHistory.onOpen} asDialog />}

      <div className="min-w-0 flex-1 px-1">
        <p className="text-label font-semibold text-stone-600 truncate">
          Ask IRIS
        </p>
        <h1 className="text-body font-semibold text-stone-900 truncate">{sessionTitle}</h1>
      </div>

      {onDownload && <DownloadConversation download={onDownload} />}


      {/* Phones only: Ask IRIS fills the window, so AppShell draws no phone bar
          here, and this is where the bell goes instead. On a desktop the bell
          is at the top of the sidebar (IR-519). Same component, same store. */}
      <div className="md:hidden">
        <NotificationBell />
      </div>
    </header>
  );
}
