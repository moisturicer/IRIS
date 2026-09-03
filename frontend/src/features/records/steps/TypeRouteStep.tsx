/**
 * Step 1 of the Submit Disclosure wizard — "What are you submitting?"
 *
 * Type moves here from the old step 2 (IR-88 / docs/ui-ux/05-submission.md):
 * type determines who does intake and final sign-off, so a submitter needs to
 * see that before writing an abstract, not discover it on submit.
 *
 * Only the fixed bookends are shown here — real `<input type="radio">`
 * elements (native arrow-key roving, not reimplemented) plus
 * `lib/submissionRoutes.ts`'s bookend map. Two things this step deliberately
 * does NOT show, per the grilled redesign (ADR-016, Proposed):
 *
 *  - A full route pill-chain with fixed offices (e.g. "IERC + KTTO" for every
 *    Thesis/Research). Which offices review a disclosure is no longer type-
 *    determined — it's requested in step 2 based on what the work actually
 *    involves, and confirmed by RDCO at intake. A fixed chain here would
 *    misrepresent something genuinely conditional, the same mistake the
 *    pre-redesign version made for every submission of a given type.
 *  - The document-requirements checklist ("You will need: ..."). The real
 *    UploadSlot data is large (13 required items for Thesis/Research) and
 *    unconditional regardless of what the disclosure needs — showing it
 *    upfront was found to work against NFR-U2, not for it (see IR-118). Only
 *    the manuscript is required at submission now; everything else is
 *    attached later, from the record's own Documents page, once it's routed
 *    to the offices that actually need it.
 */
import { useEffect, useState } from "react";
import { useFormContext } from "react-hook-form";
import { recordsApi } from "@/api/records";
import type { RecordType } from "@/types/records";
import { routeForTypeName } from "@/lib/submissionRoutes";
import type { RecordFormValues } from "../recordFormSchema";
import { cn } from "@/lib/utils";

export function TypeRouteStep() {
  const { register, watch, formState: { errors } } = useFormContext<RecordFormValues>();
  const selectedId = watch("record_type");

  const [recordTypes, setRecordTypes] = useState<RecordType[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    recordsApi
      .recordTypes()
      .then(({ data }) => setRecordTypes(data.results ?? []))
      .catch(() => setLoadError(true))
      .finally(() => setLoadingTypes(false));
  }, []);

  return (
    <div className="lg:flex lg:gap-6 lg:items-start">
      <div className="min-w-0 lg:flex-1">
        <p className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-3">
          Step 1 of 3 · Type determines who reviews first
        </p>

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700 mb-4">
            Failed to load record types. Please refresh the page and try again.
          </div>
        )}

        {loadingTypes ? (
          <div className="space-y-3" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-24 rounded-xl bg-stone-100 animate-pulse" />
            ))}
          </div>
        ) : (
          <fieldset>
            <legend className="sr-only">What are you submitting?</legend>
            <div role="radiogroup" aria-label="Record type" className="space-y-3">
              {recordTypes.map((rt) => {
                const checked = String(rt.id) === selectedId;
                const r = routeForTypeName(rt.name);
                return (
                  <label
                    key={rt.id}
                    className={cn(
                      "block relative rounded-xl border-2 p-4 pl-12 cursor-pointer transition-colors",
                      checked
                        ? "border-brand bg-brand-50/40"
                        : "border-stone-200 hover:border-stone-300",
                    )}
                  >
                    <input
                      type="radio"
                      value={String(rt.id)}
                      {...register("record_type")}
                      className="absolute left-4 top-5 w-4 h-4 accent-brand"
                    />
                    <span className="block text-[14px] font-bold text-stone-900">{rt.name}</span>
                    {r && (
                      <>
                        <span className="block text-[12px] text-stone-500 mt-0.5">{r.description}</span>
                        <span className="flex flex-wrap items-center gap-1.5 mt-2.5">
                          {r.bookends.map((label, i) => (
                            <span key={label} className="flex items-center gap-1.5">
                              {i > 0 && (
                                <i
                                  className={cn(
                                    "text-[9px] text-stone-300",
                                    r.hasConditionalOffices && i === 1 ? "fas fa-ellipsis" : "fas fa-arrow-right",
                                  )}
                                  aria-hidden
                                />
                              )}
                              <span className="px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wide bg-stone-900 text-white">
                                {label}
                              </span>
                            </span>
                          ))}
                        </span>
                        {r.hasConditionalOffices && (
                          <span className="block text-[11px] text-stone-400 mt-1.5">
                            Which offices review it in between depends on what you tell us next.
                          </span>
                        )}
                      </>
                    )}
                  </label>
                );
              })}
            </div>
          </fieldset>
        )}
        {errors.record_type && (
          <p className="text-[12px] text-red-500 mt-2">{errors.record_type.message}</p>
        )}
      </div>

      <aside className="mt-5 lg:mt-0 lg:w-72 lg:shrink-0 space-y-4">
        <div className="bg-white border border-stone-200 rounded-xl p-4">
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-2">
            What you'll need
          </h3>
          <p className="text-[12px] text-stone-600 leading-relaxed">
            Just your manuscript (PDF, max 50 MB) to submit. Anything a specific office needs —
            an ethics clearance form, a similarity report — is requested once your disclosure is
            routed there, from this record's Documents page.
          </p>
        </div>

        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-[12px] font-bold text-amber-800">Data Privacy consent</p>
          <p className="text-[11px] text-amber-700 mt-1 leading-relaxed">
            Required at step 3. Full text is readable in place, not a click-through.
          </p>
        </div>
      </aside>
    </div>
  );
}
