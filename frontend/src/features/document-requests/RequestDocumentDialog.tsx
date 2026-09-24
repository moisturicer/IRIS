import { useEffect, useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import type { DocumentRequestItemInput, DocumentRequestSlot, Party } from "@/types/records";

import { errorDetail } from "./errorDetail";

interface RequestDocumentDialogProps {
  recordId: number;
  /** The parties the reviewer may ask as -- `can_request_document`. Non-empty. */
  parties: Party[];
  /** Display names for those parties, as the server words them. */
  partyLabels: Partial<Record<Party, string>>;
  onClose: () => void;
  onCreated: () => void;
}

/**
 * Ask the owner for specific documents without a resubmission (IR-262,
 * ADR-022).
 *
 * The picklist is the record type's upload slots, from the server; "Other" is
 * free text for anything the list lacks. Nothing about the record's status or
 * clearances changes, and the dialog says so, because a reviewer used to
 * "Request Revision" for this would otherwise expect it to.
 */
export function RequestDocumentDialog({
  recordId,
  parties,
  partyLabels,
  onClose,
  onCreated,
}: RequestDocumentDialogProps) {
  const ids = useId();
  const titleId = `${ids}-title`;
  const [slots, setSlots] = useState<DocumentRequestSlot[] | null>(null);
  const [slotsFailed, setSlotsFailed] = useState(false);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [other, setOther] = useState("");
  const [message, setMessage] = useState("");
  const [party, setParty] = useState<Party>(parties[0]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    recordsApi
      .documentRequestSlots(recordId)
      .then(({ data }) => {
        if (!cancelled) setSlots(data);
      })
      .catch(() => {
        if (!cancelled) setSlotsFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, sending]);

  const toggle = (id: number) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    // Picklist order, not click order, so the owner reads them as listed.
    const items: DocumentRequestItemInput[] = (slots ?? [])
      .filter((s) => chosen.has(s.id))
      .map((s) => ({ slot: s.id }));
    if (other.trim()) items.push({ label: other.trim() });
    if (items.length === 0) {
      setError("Choose at least one document, or name one under Other.");
      return;
    }
    if (!message.trim()) {
      setError("Tell the owner why you need these documents.");
      return;
    }
    setSending(true);
    try {
      await recordsApi.createDocumentRequest(recordId, {
        message: message.trim(),
        items,
        ...(parties.length > 1 ? { party } : {}),
      });
      onCreated();
    } catch (err) {
      setError(errorDetail(err, "Something went wrong. Please try again."));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto"
      >
        <form onSubmit={submit} noValidate className="p-6 space-y-4">
          <div>
            <h2 id={titleId} className="text-[15px] font-bold text-stone-900">
              Request documents
            </h2>
            <p className="text-[12px] text-stone-600 mt-1 leading-relaxed">
              The owner is asked to upload these. The record stays in review and no clearance
              changes — use this instead of Request Revision when only a file is missing.
            </p>
          </div>

          {parties.length > 1 && (
            <div>
              <label
                htmlFor={`${ids}-party`}
                className="block text-[12px] font-semibold text-stone-700 mb-1"
              >
                Asking as
              </label>
              <select
                id={`${ids}-party`}
                value={party}
                onChange={(e) => setParty(e.target.value as Party)}
                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-brand"
              >
                {parties.map((p) => (
                  <option key={p} value={p}>
                    {partyLabels[p] ?? p}
                  </option>
                ))}
              </select>
            </div>
          )}

          <fieldset>
            <legend className="text-[12px] font-semibold text-stone-700 mb-1.5">Documents</legend>
            {slotsFailed ? (
              <p className="text-[12px] text-stone-600">
                Could not load this record type's documents. Name what you need under Other.
              </p>
            ) : slots === null ? (
              <div aria-hidden className="space-y-2">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-4 rounded bg-stone-100 animate-pulse" />
                ))}
              </div>
            ) : slots.length === 0 ? (
              <p className="text-[12px] text-stone-600">
                This record type lists no documents. Name what you need under Other.
              </p>
            ) : (
              <ul className="max-h-48 overflow-y-auto space-y-1 pr-1">
                {slots.map((s) => (
                  <li key={s.id}>
                    <label className="flex items-center gap-2 text-[13px] text-stone-800 py-0.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={chosen.has(s.id)}
                        onChange={() => toggle(s.id)}
                        className="accent-brand"
                      />
                      {s.name}
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <label
              htmlFor={`${ids}-other`}
              className="block text-[12px] font-semibold text-stone-700 mt-3 mb-1"
            >
              Other document <span className="font-normal text-stone-500">(optional)</span>
            </label>
            <input
              id={`${ids}-other`}
              type="text"
              value={other}
              maxLength={200}
              onChange={(e) => setOther(e.target.value)}
              placeholder="e.g. Rescanned consent form"
              className="w-full border border-stone-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-brand"
            />
          </fieldset>

          <div>
            <label
              htmlFor={`${ids}-message`}
              className="block text-[12px] font-semibold text-stone-700 mb-1"
            >
              Message to the owner <span className="font-normal text-red-600">(required)</span>
            </label>
            <textarea
              id={`${ids}-message`}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Why you need these, and anything they should check first."
              className="w-full border border-stone-200 rounded-lg p-3 text-[13px] resize-y focus:outline-none focus:border-brand"
            />
          </div>

          {error && (
            <p role="alert" className="text-[12px] text-red-700">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={sending}
              className="px-4 py-2 rounded-lg border border-stone-200 text-[13px] font-semibold text-stone-600 hover:bg-stone-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={sending}
              className="px-4 py-2 rounded-lg bg-brand text-white text-[13px] font-bold hover:bg-brand-light disabled:opacity-60"
            >
              {sending ? "Sending…" : "Send request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
