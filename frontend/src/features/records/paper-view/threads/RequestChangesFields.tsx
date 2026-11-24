import { useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Input } from "@/components/ui";
import { errorDetail } from "@/lib/errorDetail";
import type { DocumentRequestItemInput, DocumentRequestSlot } from "@/types/records";

/** What *Request changes* asks for, as the finish-review body carries it. */
export interface ChangesAsked {
  /** The paper itself needs changes, answered by a new version. */
  newVersion: boolean;
  /** Documents asked for in the same act, picklist order, then Other. */
  documents: DocumentRequestItemInput[];
}

/** Nothing to ask for: neither a new version nor a document. */
export const asksNothing = (asked: ChangesAsked) => !asked.newVersion && asked.documents.length === 0;

/**
 * *Request changes*' own fields in *Finish review* (ADR-022 Amendment 8,
 * IR-1322): whether the paper itself needs a new version (ticked by default),
 * and the documents the reviewer needs, from the record type's picklist or
 * named under Other. One act, so the owner sees one item from this party.
 * Shown only to a reviewer the server names a party for
 * (`can_request_document`); anyone else asks for a revision alone.
 */
export function RequestChangesFields({ recordId, offerDocuments, onChange }: {
  recordId: number;
  offerDocuments: boolean;
  onChange: (asked: ChangesAsked) => void;
}) {
  const ids = useId();
  const [newVersion, setNewVersion] = useState(true);
  const [slots, setSlots] = useState<DocumentRequestSlot[] | null>(null);
  const [slotsFailed, setSlotsFailed] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [other, setOther] = useState("");

  useEffect(() => {
    if (!offerDocuments) return;
    let cancelled = false;
    recordsApi.documentRequestSlots(recordId)
      .then(({ data }) => { if (!cancelled) setSlots(data); })
      .catch((error: unknown) => {
        if (!cancelled) setSlotsFailed(errorDetail(error, "Could not load this record type's documents. Name what you need under Other."));
      });
    return () => { cancelled = true; };
  }, [recordId, offerDocuments]);

  useEffect(() => {
    const documents: DocumentRequestItemInput[] = (slots ?? [])
      .filter((s) => chosen.has(s.id)).map((s) => ({ slot: s.id }));
    if (other.trim()) documents.push({ label: other.trim() });
    onChange({ newVersion, documents });
  }, [newVersion, slots, chosen, other, onChange]);

  const toggle = (id: number) => setChosen((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <div className="space-y-3 rounded-control border border-stone-200 bg-stone-50 px-3 py-3">
      <label className="flex cursor-pointer items-start gap-2.5 text-small text-stone-800">
        <input type="checkbox" checked={newVersion} onChange={(e) => setNewVersion(e.target.checked)}
          aria-describedby={`${ids}-version-desc`} className="mt-[3px] size-4 shrink-0 accent-brand" />
        <span>
          <span className="font-semibold text-stone-900">The paper itself needs changes</span>
          <span id={`${ids}-version-desc`} className="block text-stone-600">
            The authors revise it and submit a new version, which you review again.
          </span>
        </span>
      </label>

      {offerDocuments && (
        <fieldset>
          <legend className="text-small font-semibold text-stone-900">Documents you need</legend>
          <p className="mb-1.5 text-2xs text-stone-600">
            Optional. The authors send them together{newVersion ? " with the new version" : ""}.
          </p>
          {slotsFailed ? (
            <p className="text-small text-stone-600">{slotsFailed}</p>
          ) : slots === null ? (
            <div aria-hidden className="space-y-2">
              {[0, 1].map((i) => <div key={i} className="h-4 rounded-control bg-stone-200 motion-safe:animate-pulse" />)}
            </div>
          ) : slots.length > 0 && (
            <ul className="max-h-40 space-y-1 overflow-y-auto pr-1">
              {slots.map((s) => (
                <li key={s.id}>
                  <label className="flex cursor-pointer items-center gap-2 py-0.5 text-small text-stone-800">
                    <input type="checkbox" checked={chosen.has(s.id)} onChange={() => toggle(s.id)} className="size-4 accent-brand" />
                    {s.name}
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2">
            <Input id={`${ids}-other`} label="Other document" optional type="text" value={other} maxLength={200}
              onChange={(e) => setOther(e.target.value)} placeholder="e.g. Rescanned consent form" />
          </div>
        </fieldset>
      )}
    </div>
  );
}
