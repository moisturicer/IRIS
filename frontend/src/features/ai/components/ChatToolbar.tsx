import { NotificationBell } from "@/components/layout/NotificationBell";
import { DownloadConversation } from "./DownloadConversation";
import type { ConversationFile } from "@/api/runtimeReader";
import { PANE_TITLE } from "@/components/layout/paneTitle";
import { cn } from "@/lib/utils";
import { ConversationsToggle } from "./ConversationSidebar";

interface ChatToolbarProps {
  sessionTitle:     string;
  /**
   * On a phone only (IR-1233): the pane is not beside the chat, so the header
   * carries the way to it, opening it as a dialog over the answer. Absent on
   * wider pages, where the pane's own toggle is the only one.
   */
  phoneHistory?:    { open: boolean; onOpen: () => void; id?: string };
  /**
   * On a phone while a conversation is open (IR-1234): the pane's own button is
   * out of sight, so the header carries the one New conversation icon. Absent
   * otherwise, so a screen never shows two.
   */
  onNewConversation?: () => void;
  /** Shown above the title once there is a conversation to name; an empty page's title is "Ask IRIS" itself. */
  eyebrow?:         boolean;
  /** The open Conversation as Markdown (IR-1167); absent for a new conversation. */
  onDownload?:      () => Promise<ConversationFile>;
}

export function ChatToolbar({
  sessionTitle,
  phoneHistory,
  onNewConversation,
  eyebrow = true,
  onDownload,
}: ChatToolbarProps) {
  // min-h-[56px] is shared with ConversationSidebar's header so both border-b
  // rules land on the same line -- this toolbar's two-line title block made it
  // naturally taller, and the divider visibly stepped down at the split.
  return (
    <header className="shrink-0 flex items-center gap-2 px-3 py-2.5 min-h-[56px] border-b border-stone-200/80">
      {phoneHistory && <ConversationsToggle id={phoneHistory.id} open={phoneHistory.open} onClick={phoneHistory.onOpen} asDialog />}

      {/* The tool's name in the pane's title face; an open conversation's own title follows it. */}
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 px-1">
        {eyebrow && <p className={cn("shrink-0", PANE_TITLE)}>Ask IRIS</p>}
        <h1 className={cn("min-w-0 break-words", eyebrow ? "text-body font-medium text-stone-600" : PANE_TITLE)}>{sessionTitle}</h1>
      </div>

      {onNewConversation && <button type="button" onClick={onNewConversation} aria-label="New conversation"
        className="inline-flex size-11 shrink-0 items-center justify-center rounded-control text-stone-600 hover:bg-stone-200/70 hover:text-stone-900 focus-visible:outline-brand">
        <i className="fas fa-plus text-label" aria-hidden />
      </button>}
      {onDownload && <DownloadConversation download={onDownload} />}


      {/* Phones only: Ask IRIS fills the window, so AppShell draws no phone bar
          here, and this is where the bell goes instead. On a desktop the
          sidebar's Notifications link carries the count. Same store. */}
      <div className="md:hidden">
        <NotificationBell />
      </div>
    </header>
  );
}
