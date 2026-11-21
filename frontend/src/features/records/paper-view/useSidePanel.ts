import { useEffect, useRef, useState } from "react";

import {
  DOCKED_PANEL_CLASS,
  MINIMIZED_SHEET_CLASS,
  PAPER_WORKSPACE_PANEL_CLASS,
  fitPanelWidth,
  type usePaperChat,
} from "./PaperChatDock";
import type { ReadingTier } from "./paneLayout";
import { useReadingNote } from "./useReadingNote";

const TIER_RANK: Record<ReadingTier, number> = { single: 0, overlay: 1, wide: 2 };

type PaperChat = ReturnType<typeof usePaperChat>;

interface SidePanelInput {
  /** The page's Paper Chat state (Ask IRIS and Notes share one panel). */
  chat: PaperChat;
  /** The Record id from the route. */
  id: string | undefined;
  onPaperTab: boolean;
  onReviewTab: boolean;
  /** The reading tier the workspace's width picks; null until measured. */
  tier: ReadingTier | null;
  workspaceWidth: number;
  /** Ask IRIS is offered on this Record (published papers only). */
  askOffered: boolean;
  /** Still on the Record being left while the next one loads. */
  arriving: boolean;
  /** The page a citation or `?page=` asks for. */
  openAtPage: number | null;
  /** The location key of the last arrival (useViewLocation). */
  arrivalKey: string;
}

/**
 * Paper View's side panel, Ask IRIS and Notes (IR-1270, moved out of the
 * page unchanged): whether it is open, minimized or a modal over the page
 * at each reading tier, its width, opening Ask IRIS on entering Paper,
 * stepping aside when the workspace narrows or a citation lands, the modal
 * focus trap and Escape, where focus returns, and the reader's note with
 * the lines a highlight adds to it.
 */
export function useSidePanel({
  chat,
  id,
  onPaperTab,
  onReviewTab,
  tier,
  workspaceWidth,
  askOffered,
  arriving,
  openAtPage,
  arrivalKey,
}: SidePanelInput) {
  // The reader's private note (IR-580): held here so closing Notes keeps the
  // draft, and read only once Notes is first opened.
  const [notesWanted, setNotesWanted] = useState(false);
  const note = useReadingNote(Number(id), notesWanted);
  // Lines a Highlight's note adds to the reader's Notes once their note has loaded (IR-581).
  const pendingNote = useRef<string[]>([]);
  const noteRef = useRef(note);
  noteRef.current = note;
  const appendPendingNote = () => {
    const current = noteRef.current;
    if (current.phase !== "ready" || pendingNote.current.length === 0) return;
    const lines = pendingNote.current;
    pendingNote.current = [];
    current.setText([current.text.trimEnd(), ...lines].filter(Boolean).join("\n\n"));
  };
  useEffect(appendPendingNote, [note.phase]);
  // Focus follows a swap of Ask IRIS and Notes into the new panel, in every
  // layout: the control that was clicked is gone with the old panel.
  const focusPanel = useRef(false);
  const openNotes = () => {
    setNotesWanted(true);
    focusPanel.current = true;
    chat.openNotes();
  };
  const openAskFromNotes = () => {
    focusPanel.current = true;
    chat.setOpen(true);
  };
  /** Ask IRIS about a passage: the panel it opens takes focus. */
  const askAbout = (question: Parameters<PaperChat["askAbout"]>[0]) => {
    focusPanel.current = true;
    chat.askAbout(question);
  };
  /** Add a line to the reader's Notes, once their note has loaded. */
  const addToNote = (line: string) => {
    pendingNote.current = [...pendingNote.current, line];
    setNotesWanted(true);
    appendPendingNote();
  };

  const panelRef = useRef<HTMLElement>(null);
  const askButtonRef = useRef<HTMLButtonElement>(null);
  const notesButtonRef = useRef<HTMLButtonElement>(null);
  const refocusAsk = useRef(false);

  // Never beside the paper, where there is no sheet to tuck away.
  // Only Ask IRIS tucks away to a bar; Notes has nothing to answer back to.
  const chatMinimized = chat.minimized && chat.open && chat.tool === "ask" && !onReviewTab && tier !== "wide";
  // Ask IRIS over the paper, or instead of the page: the rest waits (IR-569).
  const chatModal =
    chat.open &&
    !chatMinimized &&
    !onReviewTab &&
    (tier === "single" || (onPaperTab && tier === "overlay"));
  // The reader's width, held to half the workspace, and beside the paper to
  // what leaves it 640px.
  const half = Math.floor(workspaceWidth / 2);
  const panelRoom = tier === "wide" && onPaperTab ? Math.min(half, workspaceWidth - 656) : half;
  const panelWidth =
    tier === "wide" || tier === "overlay" ? fitPanelWidth(chat.width, panelRoom) : undefined;

  // Opening the sidebar narrows the workspace; Ask IRIS steps aside rather than
  // taking over the page (IR-569): over the paper at any narrowing, and on the
  // other sections only where it would become the whole view. Widening leaves
  // it as it was.
  const lastTier = useRef<ReadingTier | null>(null);
  useEffect(() => {
    const before = lastTier.current;
    lastTier.current = tier;
    if (onReviewTab || !chat.open || before == null || tier == null) return;
    const narrowed = TIER_RANK[tier] < TIER_RANK[before];
    if (narrowed && (onPaperTab || tier === "single")) chat.setOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier]);

  // Entering Paper opens Ask IRIS, once per visit to the section (IR-569).
  // Following a citation within it is not an entry.
  const enteredPaper = useRef(false);
  useEffect(() => {
    if (!onPaperTab) {
      enteredPaper.current = false;
      chat.setMinimized(false);
      return;
    }
    if (arriving || enteredPaper.current) return;
    enteredPaper.current = true;
    if (askOffered) chat.setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onPaperTab, arriving]);

  const closeChat = () => {
    // Notes returns focus to its icon in every layout; Ask IRIS only where it was a dialog.
    if (chatModal || chat.tool === "notes") refocusAsk.current = true;
    chat.setOpen(false);
  };
  const backToPaper = () => {
    refocusAsk.current = true;
    // Notes has no minimized bar: back to the paper is closing it.
    if (chat.tool === "notes") chat.setOpen(false);
    else chat.setMinimized(true);
  };

  /** Back to the paper, offered only where the panel stands in for it: Paper at a single column. */
  const backToPaperAction = onPaperTab && (tier === "single" || tier === null) ? backToPaper : undefined;
  /** Open Ask IRIS from its button. */
  const openAsk = () => chat.setOpen(true);
  /** Bring a minimized Ask IRIS back up. */
  const restore = () => chat.setMinimized(false);
  /** A highlight opened from Notes: a panel that would cover the passage steps aside. */
  const stepAsideForHighlight = () => {
    if (chat.open && tier !== "wide") chat.setOpen(false);
  };

  // Over the paper, focus moves in and stays in, and Escape leaves; on
  // leaving, focus returns to the header's Ask IRIS once it is not inert.
  useEffect(() => {
    if (!chatModal) return;
    panelRef.current?.focus();
    // A dialog opened on top of the panel keeps its own Escape and focus.
    const inOtherDialog = (target: EventTarget | null) => {
      const owner = target instanceof Element ? target.closest('[role="dialog"],[role="alertdialog"]') : null;
      return owner != null && owner !== panelRef.current;
    };
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || inOtherDialog(e.target)) return;
      if (tier === "single" && onPaperTab) backToPaper();
      else closeChat();
    };
    // The sidebar is the app's, not inert here: focus reaching it comes back.
    const onFocusIn = (e: FocusEvent) => {
      const panel = panelRef.current;
      if (!panel || !(e.target instanceof Node) || panel.contains(e.target) || inOtherDialog(e.target)) return;
      panel.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
    };
    // `chat.tool`: swapping Ask IRIS for Notes replaces the panel, so focus follows it in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatModal, tier, onPaperTab, chat.tool]);
  useEffect(() => {
    if (focusPanel.current && chat.open && panelRef.current) {
      focusPanel.current = false;
      panelRef.current.focus();
    }
    if (!refocusAsk.current || chatModal) return;
    refocusAsk.current = false;
    const bar = panelRef.current?.querySelector<HTMLElement>('button[aria-label="Ask IRIS: back to the answer"]');
    (bar ?? (chat.tool === "notes" ? notesButtonRef.current : askButtonRef.current))?.focus();
  });

  useEffect(() => {
    if (openAtPage == null) return;
    // A citation followed while the chat covers the paper would land its
    // passage under it, so it tucks away to a bar (IR-354).
    if (chat.open && tier !== "wide") {
      // Notes would cover the passage just as the chat would, and has no bar
      // to tuck into: it closes, and the Notes icon brings it back.
      if (chat.tool === "notes") chat.setOpen(false);
      else chat.setMinimized(true);
    }
    // The arrival key is unique per navigation, including a second click on
    // the very citation already open -- without it in the dependency list,
    // clicking the same marker twice would not re-fire this effect. The
    // chat's state is read, not a trigger: opening the chat is not following
    // a citation, and neither is switching section.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openAtPage, arrivalKey]);

  // One Ask IRIS everywhere (IR-569): a column or drawer in the Paper
  // workspace, a column beside the page on the other sections. The Review section has none
  // (spec §4.6): the panel stays mounted there, only hidden.
  const panelClass = onReviewTab
    ? "hidden"
    : chatMinimized
      ? MINIMIZED_SHEET_CLASS
      : onPaperTab
        ? PAPER_WORKSPACE_PANEL_CLASS
        : DOCKED_PANEL_CLASS;

  return {
    note,
    notesWanted,
    openNotes,
    openAskFromNotes,
    askAbout,
    addToNote,
    panelRef,
    askButtonRef,
    notesButtonRef,
    chatMinimized,
    chatModal,
    panelRoom,
    panelWidth,
    panelClass,
    closeChat,
    backToPaper: backToPaperAction,
    openAsk,
    restore,
    stepAsideForHighlight,
  };
}
