import { useEffect, useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal, Skeleton } from "@/components/ui";
import { CHECKBOX, LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import type { Party, RouteOptions, RouteRequest } from "@/types/records";

interface RouteDialogProps {
  recordId: number;
  /** *Accept & route* (the Adviser) or onward *Route* (an office seat holder). */
  mode: "accept" | "route";
  onClose: () => void;
  /** Routed: the offices it went to, for the bar to announce. */
  onRouted: (officeLabels: string[]) => void;
}

/** What the reviewer chose for one office: ticked, and whom (if anyone) to nominate. */
interface Choice {
  ticked: boolean;
  nominees: number[];
}

/**
 * Route a record to one or more offices (ADR-032 §3–§4, IR-261).
 *
 * The offices, their members and the author's hints come from the server
 * (`route-options`), which also decides who may route at all. Nothing is
 * pre-ticked, even where the author flagged an office: the hint is shown, and
 * the decision stays the router's (ADR-032 §3). An office that already holds
 * the record can only gain a nominee, so its picker has no "leave in pool".
 *
 * Adding a colleague from your own office is a different act (ADR-032 §4) and
 * is not here.
 */
export function RouteDialog({ recordId, mode, onClose, onRouted }: RouteDialogProps) {
  const ids = useId();
  const [options, setOptions] = useState<RouteOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState<string | null>(null);
  const [choices, setChoices] = useState<Partial<Record<Party, Choice>>>({});
  const [suggested, setSuggested] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    recordsApi
      .routeOptions(recordId)
      .then(({ data }) => {
        if (!cancelled) setOptions(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadFailed(errorDetail(err, "The offices could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  const accepting = mode === "accept";
  const title = accepting ? "Accept & send to RDCO" : "Request office review";
  const choiceFor = (party: Party): Choice => choices[party] ?? { ticked: false, nominees: [] };
  const setChoice = (party: Party, change: Partial<Choice>) =>
    setChoices((prev) => ({ ...prev, [party]: { ...choiceFor(party), ...change } }));

  const ticked = (options?.targets ?? []).filter((t) => choiceFor(t.party).ticked);
  // An office already reviewing it gains only a nominee: one must be named.
  const missingNominee = ticked.some((t) => t.already_holds && !choiceFor(t.party).nominees.length);
  const ready = ticked.length > 0 && reason.trim() !== "" && !missingNominee;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    const body: RouteRequest = {
      reason: reason.trim(),
      ...(accepting ? { suggested_offices: suggested } : {}),
      to: ticked.map((t) => {
        const nominees = choiceFor(t.party).nominees;
        return nominees.length ? { party: t.party, nominees } : { party: t.party };
      }),
    };
    try {
      await (accepting ? recordsApi.acceptAndRoute(recordId, body) : recordsApi.route(recordId, body));
      onRouted(ticked.map((t) => t.label));
    } catch (err) {
      // The typed reason and choices stay, so the router fixes and resends.
      setError(errorDetail(err, "The record could not be routed. Please try again."));
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title={title}
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!ready} loading={sending}>
            {accepting ? "Accept & send to RDCO" : "Request review"}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          {accepting
            ? "You accept this work and send it to RDCO. RDCO may decide immediately or ask specialist offices to review. The record stays in review."
            : `${options?.from_label ?? "Your office"} keeps reviewing this record. The offices you choose review it as well.`}
        </p>

        {loadFailed ? (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {loadFailed}
          </p>
        ) : options == null ? (
          <Skeleton rows={3} label="Loading the offices…" />
        ) : (
          <fieldset>
            <legend className={LABEL}>Offices</legend>
            <ul className="space-y-3">
              {options.targets.map((target) => {
                const choice = choiceFor(target.party);
                const checkId = `${ids}-${target.party}`;
                const pickId = `${checkId}-nominee`;
                const hintId = `${checkId}-hint`;
                // Already reviewing: routing there only adds someone, so a
                // reviewer must be chosen -- and the dialog says so.
                const needsNominee = choice.ticked && target.already_holds && !choice.nominees.length;
                return (
                  <li key={target.party} className="rounded-lg border border-stone-200 px-3 py-2.5">
                    <div className="flex items-start gap-2.5">
                      <input
                        id={checkId}
                        type="checkbox"
                        className={`${CHECKBOX} mt-0.5`}
                        checked={choice.ticked}
                        onChange={(e) => setChoice(target.party, { ticked: e.target.checked })}
                        aria-describedby={target.author_hint ? hintId : undefined}
                      />
                      <div className="min-w-0">
                        <label htmlFor={checkId} className="text-[14px] font-medium text-stone-900">
                          {target.label}
                          {/* A real space, not only a margin: the checkbox's accessible
                              name must read "ITSO already reviewing", not run together. */}
                          {target.already_holds && " "}
                          {target.already_holds && (
                            <span className="ml-1 text-[13px] font-normal text-stone-600">
                              already reviewing
                            </span>
                          )}
                        </label>
                        {target.author_hint && (
                          <p id={hintId} className="mt-0.5 text-[13px] text-stone-600">
                            <i className="fas fa-flag mr-1.5 text-[11px]" aria-hidden />
                            {target.author_hint}
                          </p>
                        )}
                      </div>
                    </div>

                    {choice.ticked && (
                      <div className="mt-2.5 pl-6">
                        <p className={LABEL}>Officers at {target.label}</p>
                        <p className="text-small text-stone-600 mb-2">
                          {target.already_holds ? "Choose officers to add." : `Leave everyone unchecked for ${target.label}'s pool, or choose specific officers.`}
                        </p>
                        <fieldset id={pickId} aria-label={`Officers at ${target.label}`}
                          aria-describedby={needsNominee ? `${pickId}-why` : undefined} className="space-y-2">
                          {target.members.map((m) => (
                            <label key={m.id} className="flex items-center gap-2 text-small">
                              <input type="checkbox" className={CHECKBOX} checked={choice.nominees.includes(m.id)}
                                onChange={(e) => setChoice(target.party, { nominees: e.target.checked
                                  ? [...choice.nominees, m.id] : choice.nominees.filter((id) => id !== m.id) })} />
                              {m.name}
                            </label>
                          ))}
                        </fieldset>
                        {needsNominee && (
                          <p id={`${pickId}-why`} className="mt-1 text-[13px] text-brand">
                            {target.label} already has this record. Choose someone to add.
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </fieldset>
        )}

        {accepting && <fieldset className="space-y-2">
          <legend className={LABEL}>Suggested specialist offices (optional)</legend>
          <p className="text-small text-stone-600">These are suggestions for RDCO; they do not request a review.</p>
          {["itso", "ierc", "ktto"].map((p) => <label key={p} className="flex items-center gap-2 text-small">
            <input type="checkbox" className={CHECKBOX} checked={suggested.includes(p)} onChange={(e) => setSuggested(e.target.checked ? [...suggested, p] : suggested.filter((v) => v !== p))} />{p.toUpperCase()}
          </label>)}
        </fieldset>}
        {!accepting && !!options?.suggested_offices?.length && <p className="text-small text-stone-700">
          The Adviser suggested: {options.suggested_offices.map((p) => p.toUpperCase()).join(", ")}. Only the offices you select are requested.
        </p>}
        <div>
          <label htmlFor={`${ids}-reason`} className={LABEL}>
            Reason
          </label>
          <textarea
            id={`${ids}-reason`}
            required
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-describedby={`${ids}-reason-help`}
            className={fieldClasses(false)}
          />
          <p id={`${ids}-reason-help`} className="mt-1 text-[13px] text-stone-600">
            The offices see this with the record.
          </p>
        </div>

        {error && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
