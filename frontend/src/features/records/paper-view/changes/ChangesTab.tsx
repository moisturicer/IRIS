/**
 * The review pane's Changes tab (ADR-058 §3 as amended 2026-11-08, IR-873):
 * what changed between two Versions, section by section, with the earlier
 * threads under their section and each change one click from its place in
 * the paper.
 *
 * Everything shown is what the server sent. No state, message or warning
 * names how a Version's text was read.
 */
import { Fragment, useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Select } from "@/components/ui";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { errorDetail } from "@/lib/errorDetail";
import { cn } from "@/lib/utils";
import type {
  DocumentComparison, PlacedThread, RecordVersion, SectionComparison, VersionComparisonPayload,
} from "@/types/records";

import { SEVERITY_WORDS, type Thread } from "../threads/threadModel";
import { ChangeItem, type ChangesView, type ShowPlace } from "./ChangeItem";
import {
  countChanges, countsLabel, pageGroups, sectionHasChanges, sectionMarks, sectionTitle, threadsBySection,
} from "./changesModel";
import { useVersionComparison } from "./useVersionComparison";

export interface ChangesTabProps {
  recordId:      number;
  /** Oldest first; the tab is offered only with two or more. */
  versions:      RecordVersion[];
  /** The viewer's sent threads, to name and open the ones placed here. */
  threads:       Thread[];
  onShowInPaper: (place: ShowPlace) => void;
  onOpenThread:  (thread: Thread) => void;
}

const DOCUMENT_WORDS: Record<DocumentComparison["status"], (to: number) => string> = {
  unchanged: () => "Unchanged",
  replaced:  (to) => `Replaced in v${to}`,
  added:     (to) => `Added in v${to}`,
  removed:   (to) => `Not in v${to}`,
};

export function ChangesTab({ recordId, versions, threads, onShowInPaper, onOpenThread }: ChangesTabProps) {
  const ids = useId();
  const [pair, setPair] = useState<{ from: number; to: number } | null>(null);
  const [view, setView] = useState<ChangesView>("inline");
  const [showUnchanged, setShowUnchanged] = useState(false);
  const { load, retry } = useVersionComparison(recordId, pair);
  const data = load.status === "loaded" ? load.data : null;
  const from = pair?.from ?? data?.from ?? versions[versions.length - 2]?.number;
  const to = pair?.to ?? data?.to ?? versions[versions.length - 1]?.number;

  const choose = (side: "from" | "to", value: number) =>
    setPair({ from: side === "from" ? value : from, to: side === "to" ? value : to });

  return (
    <div className="space-y-4 text-small text-stone-700">
      <div className="flex flex-wrap items-end gap-3">
        {(["from", "to"] as const).map((side) => (
          <Select key={side} label={side === "from" ? "Compare" : "with"} size="sm"
            value={String(side === "from" ? from : to)}
            onChange={(e) => choose(side, Number(e.target.value))}>
            {versions.map((v) => <option key={v.number} value={v.number}>v{v.number} · {v.cause_label}</option>)}
          </Select>
        ))}
        <fieldset className="flex items-center gap-1">
          <legend className="sr-only">Show changes</legend>
          {(["inline", "side"] as const).map((name) => (
            <label key={name} className={cn("review-control inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3",
              view === name ? "border-stone-900 text-stone-900" : "border-stone-300 text-stone-600",
              "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand")}>
              <input type="radio" name={`${ids}-view`} value={name} checked={view === name}
                onChange={() => setView(name)} className="sr-only" />
              {name === "inline" ? "Inline" : "Side by side"}
            </label>
          ))}
        </fieldset>
      </div>

      {load.status === "loading" && <p role="status">Loading the comparison…</p>}
      {load.status === "failed" && (
        <div role="alert" className="space-y-2">
          <p>{load.message}</p>
          <button type="button" onClick={retry} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>
        </div>
      )}
      {data && <Comparison recordId={recordId} data={data} ids={ids} view={view} threads={threads} showUnchanged={showUnchanged}
        onShowUnchanged={() => setShowUnchanged((v) => !v)} onRetry={retry}
        onShowInPaper={onShowInPaper} onOpenThread={onOpenThread} />}
    </div>
  );
}

const SAVE_FAILED = "Couldn't save that. Please try again.";

/**
 * Each section's Viewed tick (IR-877): the server's answer, then the
 * viewer's own clicks, put back with a reason when the server refuses. The
 * mark follows the section's text, so the server alone says what is ticked
 * when a comparison loads.
 */
function useViewed(recordId: number, data: VersionComparisonPayload) {
  const [ticked, setTicked] = useState<Map<number, boolean>>(new Map());
  const [errors, setErrors] = useState<Map<number, string>>(new Map());
  // A box waits for its answer before it can be clicked again, so two quick
  // clicks never leave it out of step with the server.
  const [pending, setPending] = useState<Set<number>>(new Set());
  useEffect(() => {
    setTicked(new Map());
    setErrors(new Map());
    setPending(new Set());
  }, [data]);
  const sections = data.sections ?? [];

  const isViewed = (i: number) => ticked.get(i) ?? sections[i]?.viewed === true;
  const put = <T,>(map: Map<number, T>, i: number, value: T | undefined) => {
    const next = new Map(map);
    if (value === undefined) next.delete(i); else next.set(i, value);
    return next;
  };

  const toggle = async (i: number) => {
    const section = sections[i];
    const side = section.to ? "to" : "from";
    const key = section[side]?.key;
    if (!key || pending.has(i)) return;
    const wanted = !isViewed(i);
    const fail = (message: string) => {
      setTicked((m) => put(m, i, !wanted));
      setErrors((m) => put(m, i, message));
    };
    setPending((p) => new Set(p).add(i));
    setTicked((m) => put(m, i, wanted));
    setErrors((m) => put(m, i, undefined));
    try {
      const { data: answer } = await recordsApi.markSectionViewed(recordId, {
        from: data.from, to: data.to, side, key, viewed: wanted,
      });
      if (typeof answer?.viewed === "boolean") setTicked((m) => put(m, i, answer.viewed));
      else fail(SAVE_FAILED);
    } catch (err) {
      fail(errorDetail(err, SAVE_FAILED));
    } finally {
      setPending((p) => { const next = new Set(p); next.delete(i); return next; });
    }
  };
  return {
    isViewed, toggle,
    isPending: (i: number) => pending.has(i),
    error: (i: number) => errors.get(i) ?? null,
  };
}

interface ComparisonProps {
  recordId: number;
  data: VersionComparisonPayload;
  ids: string;
  view: ChangesView;
  threads: Thread[];
  showUnchanged: boolean;
  onShowUnchanged: () => void;
  onRetry: () => void;
  onShowInPaper: (place: ShowPlace) => void;
  onOpenThread: (thread: Thread) => void;
}

function Comparison({ recordId, data, ids, view, threads, showUnchanged, onShowUnchanged, onRetry, onShowInPaper, onOpenThread }: ComparisonProps) {
  const { from, to } = data;
  const viewed = useViewed(recordId, data);
  if (data.state !== "ready") {
    return (
      <div className="space-y-4">
        <div role={data.state === "preparing" ? "status" : undefined}
          className="rounded-lg border border-stone-200 bg-white p-3">
          <p className="text-stone-900">{data.message}</p>
          {data.state === "unavailable" && (
            <button type="button" onClick={onRetry} className={cn(PILL_SECONDARY, FOCUS_RING, "mt-2")}>Try again</button>
          )}
        </div>
        <Documents documents={data.documents} to={to} />
      </div>
    );
  }

  const byPage = data.mode === "pages";
  const sections = data.sections ?? [];
  const placed = threadsBySection(data.threads ?? []);
  const thread = (t: PlacedThread) => threads.find((x) => x.root.id === t.thread);
  const nameOf = (side: "from" | "to", key: string) =>
    sections.find((s) => s[side]?.key === key)?.[side]?.heading ?? null;
  const changed = sections.map((s, i) => ({ s, i })).filter(({ s }) => sectionHasChanges(s));
  const shown = showUnchanged ? sections.map((s, i) => ({ s, i })) : changed;
  const unchangedCount = sections.length - changed.length;
  const counts = data.counts;
  const extra = counts && [
    counts.sections_renamed ? `${counts.sections_renamed} section${counts.sections_renamed === 1 ? "" : "s"} renamed` : null,
    counts.sections_moved ? `${counts.sections_moved} section${counts.sections_moved === 1 ? "" : "s"} moved` : null,
  ].filter(Boolean);
  const focusTarget = (id: string) => {
    const el = document.getElementById(id);
    el?.scrollIntoView({ block: "start" });
    el?.focus({ preventScroll: true });
  };

  return (
    <div className="space-y-4">
      <p className="text-stone-900">
        <span className="font-semibold">v{from} → v{to}:</span> {counts ? countsLabel(counts) : "No changes"}
        {extra && extra.length > 0 && <span className="text-stone-600"> · {extra.join(" · ")}</span>}
      </p>

      {(data.notices ?? []).map((n) => (
        <p key={`${n.code}-${n.side}`} role="note"
          className="rounded-lg border border-stone-300 bg-stone-100 p-3 text-stone-800">
          <i className="fas fa-circle-info mr-2 text-stone-600" aria-hidden />{n.message}
        </p>
      ))}

      {byPage ? (
        <PageList data={data} ids={ids} view={view} placed={placed.get(null) ?? []} thread={thread}
          nameOf={nameOf} focusTarget={focusTarget} onShowInPaper={onShowInPaper} onOpenThread={onOpenThread} />
      ) : (
        <>
          {changed.length > 0 && (
            <nav aria-label="Changed sections">
              <ul className="space-y-0.5">
                {changed.map(({ s, i }) => (
                  <li key={i}>
                    <button type="button" onClick={() => focusTarget(`${ids}-s${i}`)}
                      className={cn("review-control flex w-full items-baseline justify-between gap-3 text-left hover:bg-stone-100", FOCUS_RING)}>
                      <span className="truncate text-stone-900">{sectionTitle(s)}</span>
                      <span className="shrink-0 text-2xs text-stone-600">
                        {s.changes.length ? countsLabel(s.counts) : sectionMarks(s, from, to).join(" · ")}
                        {viewed.isViewed(i) && " · Viewed"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
          {unchangedCount > 0 && (
            <button type="button" aria-expanded={showUnchanged} onClick={onShowUnchanged}
              className={cn("review-control text-stone-700 underline-offset-2 hover:underline", FOCUS_RING)}>
              {showUnchanged ? "Hide" : "Show"} {unchangedCount} unchanged section{unchangedCount === 1 ? "" : "s"}
            </button>
          )}
          {changed.length === 0 && !showUnchanged && (
            <p>Nothing in the text changed between v{from} and v{to}.</p>
          )}
          {shown.map(({ s, i }) => (
            <Section key={i} section={s} id={`${ids}-s${i}`} from={from} to={to} view={view}
              viewed={viewed.isViewed(i)} viewedPending={viewed.isPending(i)} viewedError={viewed.error(i)}
              onToggleViewed={() => void viewed.toggle(i)}
              placed={placed.get(i) ?? []} thread={thread} nameOf={nameOf}
              onShowInPaper={onShowInPaper} onOpenThread={onOpenThread} />
          ))}
        </>
      )}

      <Documents documents={data.documents} to={to} />
    </div>
  );
}

interface SectionProps {
  section: SectionComparison;
  id: string;
  from: number;
  to: number;
  view: ChangesView;
  viewed: boolean;
  viewedPending: boolean;
  viewedError: string | null;
  onToggleViewed: () => void;
  placed: PlacedThread[];
  thread: (t: PlacedThread) => Thread | undefined;
  nameOf: (side: "from" | "to", key: string) => string | null;
  onShowInPaper: (place: ShowPlace) => void;
  onOpenThread: (thread: Thread) => void;
}

function Section({
  section, id, from, to, view, viewed, viewedPending, viewedError, onToggleViewed, placed, thread, nameOf, onShowInPaper, onOpenThread,
}: SectionProps) {
  const marks = sectionMarks(section, from, to);
  const title = sectionTitle(section);
  return (
    <section aria-labelledby={id} className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <h3 id={id} tabIndex={-1} className={cn("font-display text-base font-semibold text-stone-900", FOCUS_RING)}>
          {title}
        </h3>
        {/* Private and decides nothing; it only folds the changes away (IR-877). */}
        <label className="review-control inline-flex shrink-0 cursor-pointer items-center gap-1.5 text-2xs text-stone-700">
          <input type="checkbox" checked={viewed} onChange={onToggleViewed} disabled={viewedPending}
            aria-label={`Viewed: ${title}`}
            className="accent-brand" />
          Viewed
        </label>
      </div>
      {viewedError && <p role="alert" className="text-2xs text-brand">{viewedError}</p>}
      {marks.length > 0 && (
        <p className="flex flex-wrap gap-1.5">{marks.map((m) => <span key={m} className="review-tag">{m}</span>)}</p>
      )}
      <Threads placed={placed} thread={thread} onOpenThread={onOpenThread} />
      {section.changes.length > 0 && !viewed && (
        <ul className="space-y-2">
          {section.changes.map((c, n) => (
            <li key={n}><ChangeItem change={c} from={from} to={to} view={view} sectionName={nameOf} onShow={onShowInPaper} /></li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PageList({ data, ids, view, placed, thread, nameOf, focusTarget, onShowInPaper, onOpenThread }: {
  data: VersionComparisonPayload; ids: string; view: ChangesView; placed: PlacedThread[];
  thread: (t: PlacedThread) => Thread | undefined;
  nameOf: (side: "from" | "to", key: string) => string | null;
  focusTarget: (id: string) => void;
  onShowInPaper: (place: ShowPlace) => void; onOpenThread: (thread: Thread) => void;
}) {
  const groups = pageGroups(data.changes ?? []);
  const { from, to } = data;
  if (groups.length === 0) return <p>Nothing in the text changed between v{from} and v{to}.</p>;
  return (
    <>
      <nav aria-label="Changed pages">
        <ul className="space-y-0.5">
          {groups.map((g, i) => (
            <li key={i}>
              <button type="button" onClick={() => focusTarget(`${ids}-p${i}`)}
                className={cn("review-control flex w-full items-baseline justify-between gap-3 text-left hover:bg-stone-100", FOCUS_RING)}>
                <span className="text-stone-900">{g.page != null ? `Page ${g.page}` : "Page unknown"}</span>
                <span className="text-2xs text-stone-600">{countsLabel(countChanges(g.changes))}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <Threads placed={placed} thread={thread} onOpenThread={onOpenThread} />
      {groups.map((g, i) => (
        <section key={i} aria-labelledby={`${ids}-p${i}`} className="space-y-2">
          <h3 id={`${ids}-p${i}`} tabIndex={-1} className={cn("font-display text-base font-semibold text-stone-900", FOCUS_RING)}>
            {g.page != null ? `Page ${g.page}` : "Page unknown"}
          </h3>
          <ul className="space-y-2">
            {g.changes.map((c, n) => (
              <li key={n}><ChangeItem change={c} from={from} to={to} view={view} sectionName={nameOf} onShow={onShowInPaper} /></li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function Threads({ placed, thread, onOpenThread }: {
  placed: PlacedThread[]; thread: (t: PlacedThread) => Thread | undefined; onOpenThread: (t: Thread) => void;
}) {
  const found = placed.map((p) => ({ p, t: thread(p) })).filter((x): x is { p: PlacedThread; t: Thread } => Boolean(x.t));
  if (found.length === 0) return null;
  return (
    <ul aria-label="Threads in this section" className="flex flex-wrap gap-1.5">
      {found.map(({ p, t }) => {
        const words = [t.root.party_label, t.root.severity ? SEVERITY_WORDS[t.root.severity] : null,
          t.root.state === "open" ? "open" : "resolved"].filter(Boolean).join(", ");
        return (
          <li key={p.thread}>
            <button type="button" onClick={() => onOpenThread(t)}
              className={cn("review-tag gap-1 hover:border-brand/40 hover:text-brand", FOCUS_RING)}>
              <i className="fas fa-comment text-2xs" aria-hidden />
              Thread {t.pin}{" "}<span className="text-stone-600">· {words}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Documents({ documents, to }: { documents: DocumentComparison[]; to: number }) {
  if (documents.length === 0) return null;
  return (
    <section aria-label="Documents" className="space-y-1">
      <h3 className="font-display text-base font-semibold text-stone-900">Documents</h3>
      <dl className="review-kv">
        {documents.map((d) => (
          <Fragment key={d.slot}>
            <dt>{d.slot}</dt>
            <dd>{DOCUMENT_WORDS[d.status](to)}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  );
}
