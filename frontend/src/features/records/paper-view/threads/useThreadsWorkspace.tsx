import { useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { recordsApi } from "@/api/records";
import type { Capability } from "@/features/records/capabilities";
import { joinLabels } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { PageRegion, Party, RecordDetail, ReviewVerdict, ThreadDocument } from "@/types/records";

import { RouteDialog } from "../RouteDialog";
import { FinishReviewDialog } from "./FinishReviewDialog";
import {
  ReaderAnnotationsContext, type ReaderAnnotations, type ReaderLanding, type ReaderMark,
} from "./readerAnnotations";
import { useNewestResponseLetter } from "./ResponseLetter";
import type { CommentTarget, ReviewThreadsProps } from "./ReviewThreads";
import { SEVERITY_WORDS, countLabel, type Thread } from "./threadModel";
import { useReviewThreads } from "./useReviewThreads";

interface Options {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  onChanged: () => void;
  /** Show the Threads tab (and, in a drawer, the pane). */
  showThreads: () => void;
  /** Show the paper (in a drawer, close the pane). */
  showPaper?: () => void;
  /** Show the document a thread is about in the reader (IR-1204). */
  showDocument?: (document: ThreadDocument) => void;
  /** Announce an outcome. */
  announce?: (text: string) => void;
  /** The viewer's own review is not yet claimed and started: Comment is held (IR-1341). */
  notStarted?: boolean;
}

/** Why the reader's Comment is greyed out before the review starts (IR-1341). */
export const COMMENT_HELD = "Start your review to comment";

/**
 * Everything the Threads tab, the reader's pins and *Finish review* share in
 * one workspace (IR-875): the viewer's threads, the composer, which thread a
 * pin or Readiness points at, where the reader lands, and the Finish and
 * routing dialogs. Both review workspaces hold one.
 */
export function useThreadsWorkspace({ record, can, onChanged, showThreads, showPaper, showDocument, announce, notStarted = false }: Options) {
  const threads = useReviewThreads(record.id, record.readiness !== null);
  const letter = useNewestResponseLetter(record.id, record.readiness !== null);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const [composing, setComposing] = useState<CommentTarget | null>(null);
  // A party, or "owner" for the authors: Readiness's `show_threads` target.
  const [party, setParty] = useState<Party | "owner" | null>(null);
  const [focus, setFocus] = useState<{ id: number; key: number } | null>(null);
  const [landing, setLanding] = useState<ReaderAnnotations["landing"]>(null);
  // The verdict to open *Finish your review* on, or false while it is shut (IR-1139).
  const [finishing, setFinishing] = useState<ReviewVerdict | true | false>(false);
  const [routingSummary, setRoutingSummary] = useState<string | null>(null);
  const currentVersion = record.versions?.length ? record.versions[record.versions.length - 1].number : null;

  const openThread = (t: Thread) => {
    showThreads();
    setFocus({ id: t.root.id, key: Date.now() });
  };
  const showInPaper = (t: Thread) => {
    const at = whereShown(t, currentVersion);
    if (!at) return;
    showPaper?.();
    setLanding({ ...at, label: `${threadLabel(t, false)}, page ${at.page}`, key: Date.now() });
  };

  const annotations = useMemo<ReaderAnnotations>(() => {
    const mark = (t: Thread, pending: boolean): ReaderMark | null => {
      const a = whereShown(t, currentVersion);
      if (!a || !a.regions.length) return null;
      return { key: `t${t.root.id}`, pin: t.pin, version: a.version, regions: a.regions, label: threadLabel(t, pending), pending,
        open: focus?.id === t.root.id, onActivate: () => openThread(t) };
    };
    return {
      currentVersion,
      marks: [
        ...threads.sent.filter((t) => t.root.state === "open").map((t) => mark(t, false)),
        ...threads.drafts.map((t) => mark(t, true)),
      ].filter((m): m is ReaderMark => m !== null),
      // Starting a thread takes an open seat; a finished reviewer only replies (IR-1226).
      onComment: can.has("start_thread")
        ? (passage, version) => {
          setComposing({ kind: "passage", version, passage });
          showThreads();
        }
        : null,
      // A thread on the whole document shown, opened where a general one is (IR-1204).
      onCommentDocument: can.has("open_general_thread")
        ? (upload, label) => {
          setComposing({ kind: "document", upload, label });
          showThreads();
        }
        : null,
      landing,
      // Until the viewer's own review is claimed and started, Comment is shown greyed out (IR-1341).
      commentHeld: notStarted ? COMMENT_HELD : null,
    };
    // `openThread` and `showThreads` only set state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threads.sent, threads.drafts, can, currentVersion, landing, focus, notStarted]);

  const panel: ReviewThreadsProps = {
    recordId: record.id, can, threads,
    viewer: { userId, party: record.revision?.party ?? null },
    composing, onCompose: setComposing, onChanged, onShowInPaper: showInPaper, onShowDocument: showDocument,
    party, onClearParty: () => setParty(null), focus, letter,
  };

  const done = (outcome: string) => {
    setFinishing(false);
    setRoutingSummary(null);
    threads.reload();
    onChanged();
    announce?.(outcome);
  };

  const dialogs: ReactNode = createPortal(
    <>
      {finishing && (
        <FinishReviewDialog
          record={record} can={can} drafts={threads.drafts.map((t) => t.root)} sent={threads.sent}
          initialVerdict={finishing === true ? undefined : finishing}
          onClose={() => setFinishing(false)} onDone={done}
          onSendToRdco={(summary) => { setFinishing(false); setRoutingSummary(summary); }}
        />
      )}
      {routingSummary !== null && (
        <RouteDialog
          recordId={record.id} mode="accept" authorHints={record.decision?.author_hints ?? []}
          initialReason={routingSummary}
          send={(body) => recordsApi.finishReview(record.id, {
            verdict: "send_to_rdco", summary: body.reason, to: body.to, suggested_offices: body.suggested_offices,
          })}
          onClose={() => setRoutingSummary(null)}
          onRouted={(offices) => done(`Accepted and sent to ${joinLabels(offices)}.`)}
        />
      )}
    </>,
    document.body,
  );

  return {
    threads,
    panel,
    /** The Threads tab's count, e.g. "2 must fix · 5 suggestions". */
    count: countLabel(threads.sent),
    /** Readiness's `show_threads`: the party's open threads. */
    showParty: (target: string | null) => {
      setParty(target as Party | "owner" | null);
      showThreads();
    },
    /** Open *Finish your review*, on `verdict` when a footer button names one (IR-1139). */
    finish: (verdict?: ReviewVerdict) => setFinishing(verdict ?? true),
    /** Open one thread in the Threads tab (the Changes tab's thread links). */
    openThread,
    /** Conversation's *View in Threads* (IR-1194): one thread by id, else the tab. */
    openThreads: (id?: number) => {
      const thread = id === undefined ? undefined : threads.sent.find((t) => t.root.id === id);
      if (thread) openThread(thread);
      else showThreads();
    },
    /** Show the paper and land on this page's band (the Changes tab's *Show in paper*). */
    /** Show a passage of `version` (IR-1195): outlined, centred and focused, named `label`. */
    showPlace: (place: Omit<ReaderLanding, "key">) => {
      showPaper?.();
      setLanding({ ...place, regions: [...place.regions], key: Date.now() });
    },
    /** Wrap the reader so it draws the pins and offers Comment. */
    wrapReader: (reader: ReactNode) => (
      <ReaderAnnotationsContext.Provider value={annotations}>{reader}</ReaderAnnotationsContext.Provider>
    ),
    dialogs,
  };
}

/** A thread as the reader names it: "Thread 3, ITSO, Must fix", or "Draft D1, …". */
function threadLabel(t: Thread, pending: boolean): string {
  return [pending ? `Draft ${t.pin}` : `Thread ${t.pin}`, t.root.party_label,
    t.root.severity ? SEVERITY_WORDS[t.root.severity] : null]
    .filter(Boolean).join(", ");
}

/**
 * Where a thread's passage is shown: in the Version on screen when the
 * thread was found or followed there (IR-876), else on its own anchor.
 */
export function whereShown(t: Thread, currentVersion: number | null):
  { version: number; page: number; regions: PageRegion[] } | null {
  const a = t.root.anchor;
  if (!a) return null;
  const p = t.root.place;
  if (p && p.version === currentVersion && p.outcome !== "removed" && p.page != null) {
    return { version: p.version, page: p.page, regions: p.regions ?? [] };
  }
  return { version: a.version, page: a.page, regions: a.regions ?? [] };
}
