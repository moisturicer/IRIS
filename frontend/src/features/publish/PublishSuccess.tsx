/**
 * Publish's confirmation (spec §4.4 "Success").
 *
 * **Who it names comes from the server.** The dialog re-reads the record after
 * submitting and names its `current_holders`, so it never says "sent to your
 * adviser" unless the server says the Adviser holds it (§0). It invents no
 * timeline either: nothing promises how long a review takes.
 *
 * **Intake is never named.** ADR-032 retires it and invariant 1 forbids naming
 * it as a current step, but until IR-260 cuts over the server still reports it
 * for a Thesis or Project. Such a holder reads as a plain "Submitted for
 * review", which names nobody rather than the wrong party (lead, 2026-10-06).
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { TrackerHolder } from "@/types/records";

interface PublishSuccessProps {
  recordId:    number;
  /** Null when the record could not be re-read; then nobody is named. */
  holders:     TrackerHolder[] | null;
  adviserName: string | null;
  isProposal:  boolean;
  onPublishAnother: () => void;
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** The holders worth naming: every party but the retired Intake. */
function namedHolders(holders: TrackerHolder[] | null): TrackerHolder[] {
  return (holders ?? []).filter((h) => h.party !== "intake");
}

/** The holders as people where the record names the person, otherwise as the server words them. */
export function holderNames(holders: TrackerHolder[], adviserName: string | null): string[] {
  return namedHolders(holders).map((h) => (h.party === "adviser" && adviserName ? adviserName : h.label));
}

export function successHeadline(holders: TrackerHolder[] | null, adviserName: string | null): string {
  const names = holders ? holderNames(holders, adviserName) : [];
  return names.length > 0 ? `Sent to ${joinNames(names)} for review` : "Submitted for review";
}

export function PublishSuccess({ recordId, holders, adviserName, isProposal, onPublishAnother }: PublishSuccessProps) {
  const headline = successHeadline(holders, adviserName);
  // Submit, which held focus, is gone; the next thing to do is open the paper.
  const openRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => openRef.current?.focus(), []);
  const named = namedHolders(holders);
  const withAdviser = named.some((h) => h.party === "adviser");

  let next: string | null = null;
  if (withAdviser) {
    next = isProposal
      ? "Your adviser reads it and decides: accept it, ask for revisions, or archive it."
      : "Your adviser reads it first. They can accept it, ask for revisions, or bring in a specialist office.";
  } else if (named.length > 0) {
    next = `${joinNames(named.map((h) => h.label))} reviews it next.`;
  }

  return (
    <div className="flex flex-col items-center py-section text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-stone-900 text-white">
        <i className="fas fa-check text-lg" aria-hidden />
      </span>
      <h3 className="mt-4 font-display text-title text-stone-900">{headline}</h3>
      <div className="mt-2 max-w-md text-body text-stone-700">
        {next && <p>{next}</p>}
        <p className={next ? "mt-1" : undefined}>
          You'll get a notification when someone acts on it, or if anything more is needed from you.
        </p>
      </div>
      <div className="mt-section-lg flex flex-wrap justify-center gap-3">
        <Link ref={openRef} to={`/records/${recordId}`} className={cn(PILL_PRIMARY, FOCUS_RING)}>
          Open paper
        </Link>
        <button type="button" onClick={onPublishAnother} className={cn(PILL_SECONDARY, FOCUS_RING)}>
          Publish another
        </button>
      </div>
    </div>
  );
}
