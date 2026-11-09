import { useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { recordsApi } from "@/api/records";
import type { Capability } from "@/features/records/capabilities";
import { joinLabels } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { PageRegion, Party, RecordDetail } from "@/types/records";

import { RouteDialog } from "../RouteDialog";
import { FinishReviewDialog } from "./FinishReviewDialog";
import { ReaderAnnotationsContext, type ReaderAnnotations, type ReaderMark } from "./readerAnnotations";
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
  /** Announce an outcome. */
  announce?: (text: string) => void;
}

/**
 * Everything the Threads tab, the reader's pins and *Finish review* share in
 * one workspace (IR-875): the viewer's threads, the composer, which thread a
 * pin or Readiness points at, where the reader lands, and the Finish and
 * routing dialogs. Both review workspaces hold one.
 */
export function useThreadsWorkspace({ record, can, onChanged, showThreads, showPaper, announce }: Options) {
  const threads = useReviewThreads(record.id, record.readiness !== null);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const [composing, setComposing] = useState<CommentTarget | null>(null);
  // A party, or "owner" for the authors: Readiness's `show_threads` target.
  const [party, setParty] = useState<Party | "owner" | null>(null);
  const [focus, setFocus] = useState<{ id: number; key: number } | null>(null);
  const [landing, setLanding] = useState<ReaderAnnotations["landing"]>(null);
  const [finishing, setFinishing] = useState(false);
  const [routingSummary, setRoutingSummary] = useState<string | null>(null);
  const currentVersion = record.versions?.length ? record.versions[record.versions.length - 1].number : null;

  const openThread = (t: Thread) => {
    showThreads();
    setFocus({ id: t.root.id, key: Date.now() });
  };
  const showInPaper = (t: Thread) => {
    const a = t.root.anchor;
    if (!a) return;
    const first = (a.regions ?? []).find((r) => r.page === a.page);
    showPaper?.();
    setLanding({ page: a.page, top: first?.top ?? 0, bottom: first?.bottom ?? 0, key: Date.now() });
  };

  const annotations = useMemo<ReaderAnnotations>(() => {
    const mark = (t: Thread, pending: boolean): ReaderMark | null => {
      const a = t.root.anchor;
      if (!a || !(a.regions ?? []).length) return null;
      const label = [pending ? `Draft ${t.pin}` : `Thread ${t.pin}`, t.root.party_label,
        t.root.severity ? SEVERITY_WORDS[t.root.severity] : null]
        .filter(Boolean).join(", ");
      return { key: `t${t.root.id}`, pin: t.pin, version: a.version, regions: a.regions ?? [], label, pending,
        onActivate: () => openThread(t) };
    };
    return {
      currentVersion,
      marks: [
        ...threads.sent.filter((t) => t.root.state === "open").map((t) => mark(t, false)),
        ...threads.drafts.map((t) => mark(t, true)),
      ].filter((m): m is ReaderMark => m !== null),
      onComment: can.has("comment_review")
        ? (passage, version) => {
          setComposing({ kind: "passage", version, passage });
          showThreads();
        }
        : null,
      landing,
    };
    // `openThread` and `showThreads` only set state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threads.sent, threads.drafts, can, currentVersion, landing]);

  const panel: ReviewThreadsProps = {
    recordId: record.id, can, threads,
    viewer: { userId, party: record.revision?.party ?? null },
    composing, onCompose: setComposing, onChanged, onShowInPaper: showInPaper,
    party, onClearParty: () => setParty(null), focus,
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
    finish: () => setFinishing(true),
    /** Open one thread in the Threads tab (the Changes tab's thread links). */
    openThread,
    /** Show the paper and land on this page's band (the Changes tab's *Show in paper*). */
    showPlace: (page: number, regions: readonly PageRegion[]) => {
      const first = regions.find((r) => r.page === page);
      showPaper?.();
      setLanding({ page, top: first?.top ?? 0, bottom: first?.bottom ?? 0, key: Date.now() });
    },
    /** Wrap the reader so it draws the pins and offers Comment. */
    wrapReader: (reader: ReactNode) => (
      <ReaderAnnotationsContext.Provider value={annotations}>{reader}</ReaderAnnotationsContext.Provider>
    ),
    dialogs,
  };
}
