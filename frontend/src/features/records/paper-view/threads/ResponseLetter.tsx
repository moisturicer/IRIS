import { useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { cn } from "@/lib/utils";
import type { ResponseLetter, ResponseLetterEntry } from "@/types/records";

import { SEVERITY_WORDS } from "./threadModel";

/** How the letter states one answer (ADR-032 §7: "Addressed in …" / "Declined: …"). */
export function answerWords(entry: Pick<ResponseLetterEntry, "answer" | "note">): string {
  if (entry.answer === "addressed") return `Addressed: ${entry.note}`;
  if (entry.answer === "declined") return `Declined: ${entry.note}`;
  return "No answer given";
}

/** The letter's threads, one item each, as the submit dialog and Threads both show them. */
export function LetterEntries({ entries }: { entries: ResponseLetterEntry[] }) {
  return (
    <ol className="space-y-2">
      {entries.map((e) => (
        <li key={e.thread} className="rounded border border-stone-200 bg-white px-2.5 py-2 text-small text-stone-800 space-y-0.5">
          <p className="text-2xs text-stone-600">
            {e.party_label}
            {e.severity ? ` · ${SEVERITY_WORDS[e.severity]}` : ""}
            {e.page != null && e.version != null ? ` · p.${e.page}, v${e.version}` : ""}
          </p>
          <p className="whitespace-pre-wrap break-words">{e.comment}</p>
          <p className={cn("whitespace-pre-wrap", e.answer ? "font-semibold" : "italic text-stone-600")}>{answerWords(e)}</p>
        </li>
      ))}
    </ol>
  );
}

/**
 * The response the newest lettered Version was submitted with, at the top of
 * Threads, so a reviewer looking again reads it first (ADR-032 §7, IR-876).
 * The server orders the viewer's own party first.
 */
export function ResponseLetterPanel({ letter }: { letter: ResponseLetter }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-lg border border-stone-300 bg-stone-50 p-3 space-y-2">
      <h4 id={headingId} className="text-small font-semibold text-stone-900">
        Response to reviewers<span className="sr-only">,</span> <span className="font-normal text-stone-600">v{letter.version}</span>
      </h4>
      <LetterEntries entries={letter.entries} />
    </section>
  );
}

/** The newest response letter on a record, or null; read once the review is readable. */
export function useNewestResponseLetter(recordId: number, enabled: boolean): ResponseLetter | null {
  const [letter, setLetter] = useState<ResponseLetter | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    Promise.resolve()
      .then(() => recordsApi.responseLetters(recordId))
      .then(({ data }) => {
        if (cancelled) return;
        // A shape we don't know shows no letter rather than throwing (F1).
        const newest = Array.isArray(data) ? data[0] : undefined;
        setLetter(newest && Array.isArray(newest.entries) && typeof newest.version === "number" ? newest : null);
      })
      .catch(() => {
        if (!cancelled) setLetter(null);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, enabled]);
  return letter;
}
