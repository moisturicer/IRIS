import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { recordsApi } from "@/api/records";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { DecisionOutcome, RecordDetail, ReviewVerdict } from "@/types/records";

import { RELEASE_EMBARGO_MESSAGE, ReleaseDialog } from "./EmbargoCard";
import { useReviewActionRunner } from "./ReviewActionBar";
import { VERDICT_CAPABILITIES, type ReviewAction } from "./reviewActions";

/** One control the footer may draw: where it goes is decided below, never what it grants. */
interface Choice {
  key: string;
  label: string;
  icon?: string;
  /** The server's reason it is held, or null. */
  blocked: string | null;
  onSelect: () => void;
}

/**
 * The Review pane footer's actions (IR-1139), shaped like the prototype's merge
 * box: a "More review actions" menu, at most one secondary pill and one filled
 * primary, right-aligned beside "Your part".
 *
 * Nothing here grants anything: every control is a capability the server
 * offered, and a held one is disabled with the server's reason. Where *Finish
 * review* is granted, a verdict opens it with that verdict chosen, so drafts
 * still go with the verdict (ADR-032 §7, IR-875): RDCO's *Accept & publish*
 * and *Keep unlisted*, *Request changes* and *Reject* all do. Everyone else
 * finishes with one *Finish review…*. The other acts (Request documents, Add
 * a colleague, Withdraw revision request) are in the menu.
 *
 * While the reviewer has drafts, **Send N comments…** opens *Finish review* on
 * *Comment only*, so sending them never waits on choosing a verdict
 * (ADR-032 §7 as amended 2026-11-16, IR-1194).
 */
export function ReviewFooterActions({ record, can, actions, finishing, onFinish, lead, onChanged, drafts = 0 }: {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  /** The review acts the footer may offer, in `REVIEW_ACTIONS`' order. */
  actions: readonly ReviewAction[];
  /** `finish_review` is granted and the review is open. */
  finishing: boolean;
  onFinish: (verdict?: ReviewVerdict) => void;
  /** Open review or Claim: the primary, when the host offers it. */
  lead?: ReactNode;
  onChanged: () => void;
  /** How many of the viewer's draft threads wait to be sent. */
  drafts?: number;
}) {
  const ids = useId();
  const runner = useReviewActionRunner(record, onChanged);
  const [releasing, setReleasing] = useState(false);

  const decision = record.decision;
  const held = (o: DecisionOutcome) => decision?.blocked ?? decision?.blocked_outcomes?.[o] ?? null;
  const asChoice = (a: ReviewAction): Choice => ({
    key: a.label, label: a.label, icon: a.icon,
    blocked: a.blockedReason?.(record) ?? null,
    onSelect: () => runner.start(a),
  });
  const granted = actions.filter((a) => can.has(a.capability));
  // Terminal acts last, as the bar orders them (spec §4.7).
  const ordered = [...granted.filter((a) => a.kind !== "terminal"), ...granted.filter((a) => a.kind === "terminal")];

  let primary: Choice | null = null;
  let secondary: Choice | null = null;
  let send: Choice | null = null;
  const menu: Choice[] = [];
  if (finishing) {
    if (drafts > 0) {
      send = { key: "send", label: `Send ${drafts} ${drafts === 1 ? "comment" : "comments"}…`, icon: "fa-paper-plane",
        blocked: null, onSelect: () => onFinish("comment_only") };
    }
    const publishes = can.has("accept_publish");
    const unlists = can.has("keep_unlisted");
    if (publishes || unlists) {
      const publish: Choice | null = publishes
        ? { key: "publish", label: "Accept & publish…", icon: "fa-circle-check", blocked: held("publish"), onSelect: () => onFinish("publish") }
        : null;
      const unlisted: Choice | null = unlists
        ? { key: "keep_unlisted", label: "Keep unlisted…", icon: "fa-eye-slash", blocked: held("keep_unlisted"), onSelect: () => onFinish("keep_unlisted") }
        : null;
      primary = publish ?? unlisted;
      secondary = publish ? unlisted : null;
      if (can.has("request_revision")) {
        menu.push({ key: "request_revision", label: "Request changes…", icon: "fa-arrow-rotate-left",
          blocked: record.revision?.blocked ?? null, onSelect: () => onFinish("request_revision") });
      }
      if (can.has("reject")) {
        menu.push({ key: "reject", label: "Reject…", icon: "fa-xmark", blocked: held("reject"), onSelect: () => onFinish("reject") });
      }
    } else {
      primary = { key: "finish", label: "Finish review…", blocked: null, onSelect: () => onFinish() };
    }
    menu.push(...ordered.filter((a) => !VERDICT_CAPABILITIES.includes(a.capability)).map(asChoice));
  } else {
    const choices = ordered.map(asChoice);
    if (!lead) primary = choices.shift() ?? null;
    menu.push(...choices);
  }

  // The embargo is the one hold the footer can lift: RDCO or the Adviser
  // releases it here instead of finding the card on Overview.
  const embargoHeld = Boolean(decision?.blocked_outcomes?.publish) && can.has("release_embargo");
  const reasonId = `${ids}-held`;
  const heldReason = primary?.blocked ?? secondary?.blocked ?? null;

  if (!lead && !primary && !secondary && !send && menu.length === 0) return runner.portal;

  const pill = (c: Choice, filled: boolean) => (
    <button key={c.key} type="button" disabled={c.blocked != null} onClick={c.onSelect}
      aria-describedby={c.blocked ? reasonId : undefined}
      className={cn(filled ? PILL_PRIMARY : PILL_SECONDARY, FOCUS_RING)}>
      {c.label}
    </button>
  );

  return (
    <>
      <div role="toolbar" aria-label="Review actions" className="ml-auto flex flex-wrap items-center justify-end gap-2">
        {menu.length > 0 && <MoreMenu choices={menu} />}
        {send && pill(send, false)}
        {secondary && pill(secondary, false)}
        {lead}
        {primary && pill(primary, !lead)}
      </div>
      {heldReason && (
        <p id={reasonId} className="basis-full text-2xs text-stone-600">
          {heldReason}
          {embargoHeld && (
            <>
              {" "}
              <button type="button" onClick={() => setReleasing(true)}
                className={cn("font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
                Release embargo…
              </button>
            </>
          )}
        </p>
      )}
      <p role="status" aria-live="polite" className={cn("basis-full text-small text-stone-900", !runner.outcome && "sr-only")}>
        {runner.outcome}
      </p>
      {runner.portal}
      {createPortal(
        <ReleaseDialog
          open={releasing}
          title="Release this embargo?"
          message={RELEASE_EMBARGO_MESSAGE}
          act={() => recordsApi.releaseEmbargo(record.id)}
          onCancel={() => setReleasing(false)}
          onReleased={() => { setReleasing(false); onChanged(); }}
          onRefused={onChanged}
        />,
        document.body,
      )}
    </>
  );
}

/** The footer's "More review actions" menu, opening upward from the bottom of the pane. */
function MoreMenu({ choices }: { choices: readonly Choice[] }) {
  const [open, setOpen] = useState(false);
  // Fixed to the viewport: the footer scrolls (`overflow-y: auto`), which would clip a menu opening upward from inside it.
  const [anchor, setAnchor] = useState<{ right: number; bottom: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')?.focus();
    const outside = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("click", outside);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("click", outside);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Tab") { setOpen(false); return; }
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      button.current?.focus();
      return;
    }
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    e.preventDefault();
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    items[(at + step + items.length) % items.length]?.focus();
  };

  return (
    <div className="relative">
      <button ref={button} type="button" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
        aria-label="More review actions" title="More review actions" onClick={() => {
          const r = button.current?.getBoundingClientRect();
          if (r) setAnchor({ right: window.innerWidth - r.right, bottom: window.innerHeight - r.top + 4 });
          setOpen((o) => !o);
        }}
        className={cn("review-control text-stone-600 hover:text-brand", FOCUS_RING)}>
        <i className="fas fa-ellipsis" aria-hidden />
      </button>
      {open && anchor && createPortal(
        <div ref={menu} id={id} role="menu" aria-label="More review actions" onKeyDown={onKeyDown}
          style={{ position: "fixed", right: anchor.right, bottom: anchor.bottom }}
          className="z-50 min-w-56 rounded-control border border-stone-300 bg-overlay p-1 shadow-sm">
          {choices.map((c) => (
            <button key={c.key} type="button" role="menuitem" tabIndex={-1}
              aria-disabled={c.blocked != null || undefined}
              onClick={() => { if (c.blocked != null) return; setOpen(false); c.onSelect(); }}
              className={cn("review-control flex w-full items-start gap-2 text-left text-stone-900 hover:bg-stone-100",
                c.blocked != null && "cursor-not-allowed text-stone-500 hover:bg-transparent", FOCUS_RING)}>
              {c.icon && <i className={cn("fas mt-0.5 w-4 text-2xs text-stone-500", c.icon)} aria-hidden />}
              <span>
                <span className="block">{c.label}</span>
                {c.blocked && <span className="block text-2xs text-stone-600">{c.blocked}</span>}
              </span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
