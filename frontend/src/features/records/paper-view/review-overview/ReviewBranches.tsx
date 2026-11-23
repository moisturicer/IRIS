import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import { truncateBody } from "../commentThreads";
import type { ReviewTarget } from "../reviewTarget";
import type { BranchAsk, BranchNode, BranchTone } from "./branches";

const TONE: Record<BranchTone, { icon: string; text: string; wire: string }> = {
  asking:  { icon: "fa-rotate-left",    text: "text-brand",     wire: "stroke-brand" },
  refused: { icon: "fa-ban",            text: "text-brand",     wire: "stroke-brand" },
  done:    { icon: "fa-check",          text: "text-cleared",   wire: "stroke-cleared-line" },
  busy:    { icon: "fa-hourglass-half", text: "text-review",    wire: "stroke-review-line" },
  idle:    { icon: "fa-minus",          text: "text-stone-600", wire: "stroke-stone-300" },
};

/** Where an ask is read in full: the words in Conversation, the files in Documents. */
const targetOf = (party: string, ask: BranchAsk): ReviewTarget =>
  ask.kind === "revision" ? { tab: "conversation", party } : { tab: "documents", party: null };

/** The reviewer's words: a text node, never markup (ADR-022 §Security). A long one opens in place, as a review comment does. */
function Words({ text, label }: { text: string; label: string }) {
  const [whole, setWhole] = useState(false);
  const shown = whole ? { text, truncated: false } : truncateBody(text);
  return (
    <blockquote className="text-justified whitespace-pre-line break-words text-md text-stone-900">
      {shown.text}
      {shown.truncated && (
        <>
          …{" "}
          <button type="button" onClick={() => setWhole(true)} aria-label={`See more of ${label}'s request`}
            className={cn("rounded-control text-small font-semibold text-brand hover:underline", FOCUS_RING)}>
            See more
          </button>
        </>
      )}
    </blockquote>
  );
}

function Node({ node, onOpenReview }: { node: BranchNode; onOpenReview: (target: ReviewTarget) => void }) {
  const tone = TONE[node.tone];
  const asking = node.asks.length > 0;
  return (
    <div
      data-branch={node.party}
      data-tone={node.tone}
      className={cn(
        "relative min-w-0 rounded-card",
        asking ? "border-[1.5px] border-brand bg-surface px-5 py-4"
          : node.tone === "idle" ? "border border-stone-200 bg-stone-50 px-4 py-3"
            : "border border-stone-300 bg-surface px-4 py-3",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-0.5">
        <h3 className={asking ? "font-display text-title font-semibold text-stone-900" : cn("text-body font-semibold", node.tone === "idle" ? "text-stone-600" : "text-stone-900")}>
          {node.label}
        </h3>
        {(node.kept ?? node.status) && (
          <p
            className={cn("inline-flex items-center gap-1.5 text-small font-medium", tone.text)}
            title={node.kept ? "Cleared before the current submission and carried over. This office will not review again." : undefined}
          >
            <i className={cn("fas text-2xs", node.kept ? "fa-shield-halved" : tone.icon)} aria-hidden />
            {node.kept ?? node.status}
          </p>
        )}
      </div>
      {node.asks.map((ask) => (
        <div key={ask.key} className="mt-2 first-of-type:mt-1">
          <p className="text-small text-stone-600">{ask.act}</p>
          {ask.words && <Words text={ask.words} label={node.label} />}
          <button
            type="button"
            onClick={() => onOpenReview(targetOf(node.party, ask))}
            aria-label={ask.kind === "revision" ? `Read in Review: ${node.label}'s request` : `Read in Review: what ${node.label} asked for`}
            className={cn("group/go mt-1 inline-flex min-h-11 reading-split:min-h-8 items-center gap-1.5 rounded-control text-small font-semibold text-brand hover:underline underline-offset-[3px]", COLOUR_TRANSITION, FOCUS_RING)}
          >
            Read in Review
            <i className="fas fa-arrow-right text-3xs transition-transform duration-150 group-hover/go:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}

interface Wire { d: string; tone: BranchTone }

/** A line from `a` down to `b`: straight where one stands over the other, else a soft S. */
function link(a: DOMRect, b: DOMRect, origin: DOMRect, stacked: boolean): string {
  const box = (r: DOMRect) => ({ l: r.left - origin.left, r: r.right - origin.left, t: r.top - origin.top, b: r.bottom - origin.top, x: (r.left + r.right) / 2 - origin.left });
  const A = box(a), B = box(b);
  if (stacked) {
    // One column: a rail down the left, with a branch into each office.
    const x = 10;
    return `M${x} ${A.b}V${B.l > x + 4 ? (B.t + B.b) / 2 : B.t}${B.l > x + 4 ? `H${B.l}` : ""}`;
  }
  const inside = (o: typeof A, x: number) => x > o.l + 16 && x < o.r - 16;
  const x1 = A.r - A.l > B.r - B.l && inside(A, B.x) ? B.x : A.x;
  const x2 = B.r - B.l > A.r - A.l && inside(B, A.x) ? A.x : B.x;
  const y = (A.b + B.t) / 2;
  return `M${x1} ${A.b}C${x1} ${y} ${x2} ${y} ${x2} ${B.t}`;
}

/**
 * The branches, with the owner's answer placed under whoever asked last in
 * the flow. The lines are drawn from where the boxes landed, and are
 * decoration: each box says its own state.
 */
export function ReviewBranches({ rows, answer, onOpenReview }: {
  rows: BranchNode[][];
  /** The owner's files, or null when nothing waits on them (or they are not the owner). */
  answer: ReactNode;
  onOpenReview: (target: ReviewTarget) => void;
}) {
  const tree = useRef<HTMLDivElement>(null);
  const [wires, setWires] = useState<Wire[]>([]);
  // Under the last row that asks; with nobody asking any more, at the end.
  const lastAsking = rows.reduce((at, row, i) => (row.some((n) => n.asks.length > 0) ? i : at), -1);
  const answerAfter = answer ? (lastAsking >= 0 ? lastAsking : rows.length - 1) : -1;

  useLayoutEffect(() => {
    const el = tree.current;
    if (!el) return;
    const draw = () => {
      const origin = el.getBoundingClientRect();
      const rect = (n: string) => el.querySelector<HTMLElement>(`[data-branch="${n}"]`)?.getBoundingClientRect();
      const next: Wire[] = [];
      const add = (a: string, b: string, tone: BranchTone, stacked: boolean) => {
        const A = rect(a), B = rect(b);
        if (A && B && A.width > 0) next.push({ d: link(A, B, origin, stacked), tone });
      };
      const offices = rows.find((r) => r.length > 1) ?? [];
      const stacked = offices.length > 1 && rect(offices[0].party)?.top !== rect(offices[1].party)?.top;
      rows.forEach((row, i) => {
        const below = rows[i + 1];
        if (i === answerAfter) {
          row.filter((n) => n.asks.length > 0).forEach((n) => add(n.party, "answer", "asking", stacked));
          below?.forEach((n) => add("answer", n.party, "idle", stacked));
        } else if (below) {
          row.forEach((a) => below.forEach((b) => {
            const tone = row.length === 1 ? b.tone : a.tone === "done" ? "done" : "idle";
            add(a.party, b.party, tone, stacked);
          }));
        }
      });
      setWires((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
    };
    draw();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(draw);
    observer.observe(el);
    return () => observer.disconnect();
  });

  const slot = answer ? <div key="answer" data-branch="answer" className="w-full">{answer}</div> : null;
  return (
    <div ref={tree} className="relative flex flex-col gap-6 overview-roomy:items-center overview-roomy:gap-10">
      <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full fill-none" strokeWidth={2}>
        {wires.map((w, i) => <path key={i} d={w.d} className={TONE[w.tone].wire} />)}
      </svg>
      {/* One flat, keyed list: the answer moves when who asks changes, and never
          remounts, so an upload in it is never lost. */}
      {rows.flatMap((row, i) => [
        row.length === 1 ? (
          <div key={row[0].party} className="min-w-0 overview-roomy:min-w-[15rem] overview-roomy:max-w-xl">
            <Node node={row[0]} onOpenReview={onOpenReview} />
          </div>
        ) : (
          <ul
            key="offices"
            aria-label="Offices"
            className="grid w-full items-start gap-3 pl-6 overview-roomy:gap-4 overview-roomy:pl-0 overview-roomy:[grid-template-columns:var(--branch-cols)]"
            style={{ "--branch-cols": row.map((n) => (n.asks.length > 0 ? "minmax(0,1.7fr)" : "minmax(0,1fr)")).join(" ") } as CSSProperties}
          >
            {row.map((node) => <li key={node.party} className="min-w-0"><Node node={node} onOpenReview={onOpenReview} /></li>)}
          </ul>
        ),
        ...(i === answerAfter ? [slot] : []),
      ])}
      {rows.length === 0 && slot}
    </div>
  );
}
