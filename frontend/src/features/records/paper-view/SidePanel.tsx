import type { ComponentProps } from "react";

import type { AnswerReturn } from "@/lib/citedPage";
import type { RecordDetail } from "@/types/records";
import { AskIrisFab, NotesFab } from "./AskIrisFab";
import { NotesPanel } from "./NotesPanel";
import { PaperChatPanel, PANEL_WIDTH_MIN, type usePaperChat } from "./PaperChatDock";
import type { ReadableHighlight, useReadingHighlights } from "./useReadingHighlights";
import type { useSidePanel } from "./useSidePanel";

interface SidePanelProps {
  record: RecordDetail;
  chat: ReturnType<typeof usePaperChat>;
  /** Where the panel stands and what it does (useSidePanel). */
  panel: ReturnType<typeof useSidePanel>;
  /** The arrival Paper Chat is told of; null while the next Record loads. */
  arrival: ComponentProps<typeof PaperChatPanel>["arrival"];
  onReviewTab: boolean;
  askOffered: boolean;
  /** Notes is kept on published papers only (IR-1326). */
  notesOffered: boolean;
  highlights: ReturnType<typeof useReadingHighlights>;
  onOpenHighlight: (h: ReadableHighlight) => void;
  /** An earlier version the reader may open a highlight in. */
  canOpenVersion: (n: number) => boolean;
  /** The version open in the reader, null for the current paper. */
  viewingVersion: number | null;
  /** The answer Paper Chat should reopen at (useCitationLanding). */
  chatReturn: AnswerReturn | null;
}

/**
 * Paper View's side panel, rendered (IR-1271, moved out of the page
 * unchanged): the scrim over the paper, Ask IRIS or Notes, and, while
 * closed, their two round buttons. useSidePanel decides its state.
 */
export function SidePanel({
  record,
  chat,
  panel,
  arrival,
  onReviewTab,
  askOffered,
  notesOffered,
  highlights,
  onOpenHighlight,
  canOpenVersion,
  viewingVersion,
  chatReturn,
}: SidePanelProps) {
  const { chatModal, chatMinimized, panelWidth, panelRoom, panelRef, closeChat, backToPaper } = panel;
  return (
    <>
      {/* Over the paper, the rest of the page waits behind a scrim. */}
      {chatModal && (
        <div
          aria-hidden
          onClick={closeChat}
          className="hidden reading-split:block reading-wide:hidden absolute inset-0 z-30 bg-stone-900/25"
        />
      )}
      {chat.open && chat.tool === "ask" && askOffered && (
        <PaperChatPanel
          record={record}
          // Whether a citation inside the chat brought the reader here, which
          // keeps its conversation open (IR-355); withheld until the record
          // this navigation is going to has arrived. Keyed by arrival, so a
          // change of section is not one.
          arrival={arrival}
          onClose={closeChat}
          onBackToPaper={backToPaper}
          panelRef={panelRef}
          modal={chatModal}
          draft={chat.draft}
          onDraftChange={chat.setDraft}
          resize={
            panelWidth && !chatMinimized
              ? {
                  width: panelWidth,
                  max: Math.max(PANEL_WIDTH_MIN, panelRoom),
                  onChange: chat.setWidth,
                }
              : undefined
          }
          style={panelWidth && !chatMinimized ? { width: panelWidth } : undefined}
          minimized={chatMinimized}
          onRestore={panel.restore}
          viewingVersion={viewingVersion}
          returnTo={chatReturn}
          onOpenNotes={onReviewTab || !notesOffered ? undefined : panel.openNotes}
          selection={chat.selection}
          onSelectionChange={chat.setSelection}
          className={panel.panelClass}
        />
      )}
      {chat.open && chat.tool === "notes" && notesOffered && !onReviewTab && (
        <NotesPanel
          record={record}
          note={panel.note}
          highlights={highlights}
          onOpenHighlight={onOpenHighlight}
          canOpenVersion={canOpenVersion}
          onClose={closeChat}
          onBackToPaper={backToPaper}
          onOpenAsk={askOffered ? panel.openAskFromNotes : undefined}
          panelRef={panelRef}
          modal={chatModal}
          resize={
            panelWidth
              ? { width: panelWidth, max: Math.max(PANEL_WIDTH_MIN, panelRoom), onChange: chat.setWidth }
              : undefined
          }
          style={panelWidth ? { width: panelWidth } : undefined}
          className={panel.panelClass}
        />
      )}
      {/* Closed: two round icons at the bottom right, Notes above Ask IRIS
          (IR-569, IR-1079). On the bar while minimized, which is its way back. */}
      {!chat.open && !onReviewTab && (
        <>
          {notesOffered && <NotesFab onOpen={panel.openNotes} buttonRef={panel.notesButtonRef} />}
          {askOffered && <AskIrisFab onOpen={panel.openAsk} buttonRef={panel.askButtonRef} />}
        </>
      )}
    </>
  );
}
