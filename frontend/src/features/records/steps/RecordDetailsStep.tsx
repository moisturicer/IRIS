/**
 * Step 2 of the record creation/edit wizard.
 * Collects: year, record type, adviser, authors.
 *
 * Record types are fetched from /records/record-types/ so the list
 * stays in sync with the database without hardcoding.
 *
 * NOTE: "research_type" (Applied/Basic/Action/Mixed) has no backing model field
 * and is intentionally omitted until a ResearchType model is added.
 */
import { useEffect, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/Input";
import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import type { User } from "@/types/auth";
import type { RecordType } from "@/types/records";
import type { RecordFormValues } from "../recordFormSchema";
import { FieldError } from "./FieldError";
import { LABEL, LOAD_ERROR, fieldClasses } from "./fieldClasses";

export function RecordDetailsStep() {
  const {
    register,
    formState: { errors },
    watch,
    setValue,
    getValues,
  } = useFormContext<RecordFormValues>();

  const authors          = watch("authors") ?? [];
  const selectedTypeId   = watch("record_type");
  const [authorInput, setAuthorInput] = useState("");

  const [advisers,     setAdvisers]     = useState<User[]>([]);
  const [recordTypes,  setRecordTypes]  = useState<RecordType[]>([]);
  const [loadingData,  setLoadingData]  = useState(true);
  const [loadError,    setLoadError]    = useState(false);

  // Derived: is the selected record type "Proposal"?
  const selectedTypeName = recordTypes.find((rt) => String(rt.id) === selectedTypeId)?.name;
  const isProposal       = selectedTypeName === "Proposal";

  useEffect(() => {
    setLoadError(false);
    Promise.all([
      accountsApi.listAdvisers(),
      recordsApi.recordTypes(),
    ])
      .then(([advisersRes, typesRes]) => {
        setAdvisers(advisersRes.data.results ?? []);
        setRecordTypes(typesRes.data.results ?? []);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoadingData(false));
  }, []);

  // The select mounts before its options arrive, so the browser cannot select
  // the saved type then and falls back to the placeholder, although the form
  // still holds the value. Put it back once the options exist.
  useEffect(() => {
    if (!loadingData) setValue("record_type", getValues("record_type"));
  }, [loadingData, getValues, setValue]);

  const addAuthor = () => {
    const trimmed = authorInput.trim();
    if (trimmed && !authors.includes(trimmed)) {
      setValue("authors", [...authors, trimmed], { shouldValidate: true });
    }
    setAuthorInput("");
  };

  const removeAuthor = (idx: number) => {
    setValue("authors", authors.filter((_, i) => i !== idx), { shouldValidate: true });
  };

  return (
    <div className="flex flex-col gap-5">
      {loadError && (
        <div className={LOAD_ERROR}>
          <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
          Failed to load form data. Please refresh the page and try again.
        </div>
      )}

      {/* Year */}
      <Input
        label="Year Accomplished"
        type="number"
        {...register("year", { valueAsNumber: true })}
        error={errors.year?.message}
      />

      {/* Record type — fetched from API */}
      <div>
        <label className={LABEL}>
          Record Type <span className="text-brand">*</span>
        </label>
        <select
          {...register("record_type")}
          disabled={loadingData}
          className={fieldClasses(Boolean(errors.record_type))}
        >
          <option value="">{loadingData ? "Loading…" : "Select record type"}</option>
          {recordTypes.map((rt) => (
            <option key={rt.id} value={String(rt.id)}>{rt.name}</option>
          ))}
        </select>
        {errors.record_type && <FieldError>{errors.record_type.message}</FieldError>}
      </div>

      {/* Adviser — only required for Proposal; shown as optional for other types */}
      <div>
        <label className={LABEL}>
          Adviser{" "}
          {isProposal ? (
            <span className="text-brand">*</span>
          ) : (
            <span className="text-stone-500 font-normal text-[12px]">
              {selectedTypeName ? "(optional for this record type)" : "(select record type first)"}
            </span>
          )}
        </label>
        <select
          {...register("adviser", { valueAsNumber: true })}
          disabled={loadingData}
          className={fieldClasses(Boolean(errors.adviser))}
        >
          <option value="">{loadingData ? "Loading…" : "Select adviser"}</option>
          {advisers.map((a) => (
            <option key={a.id} value={a.id}>
              {a.last_name}, {a.first_name}{a.middle_initial ? ` ${a.middle_initial}.` : ""}
            </option>
          ))}
        </select>
        {errors.adviser && <FieldError>{errors.adviser.message}</FieldError>}
        {isProposal && (
          <p className="text-[11px] text-stone-500 mt-0.5">
            Proposal records must have an assigned adviser before submission.
          </p>
        )}
      </div>

      {/* Authors — required, min 1 */}
      <div>
        <label className={LABEL}>
          Authors <span className="text-brand">*</span>
        </label>
        <div className="flex gap-2 mb-2">
          <input
            value={authorInput}
            onChange={(e) => setAuthorInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addAuthor())}
            placeholder="Type author name and press Enter or Add"
            className="flex-1 border border-stone-300 rounded-lg px-3 py-2 text-[13px] text-stone-900 outline-none
              placeholder:text-stone-500 focus:border-brand focus:ring-1 focus:ring-brand"
          />
          <button
            type="button"
            onClick={addAuthor}
            className="px-3 py-2 bg-stone-100 rounded-lg text-[13px] text-stone-700 hover:bg-stone-200"
          >
            Add
          </button>
        </div>

        {/* Author chips */}
        {authors.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-1">
            {authors.map((a, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-stone-100 rounded-full text-[12px] text-stone-700"
              >
                {a}
                <button
                  type="button"
                  onClick={() => removeAuthor(i)}
                  className="text-stone-500 hover:text-stone-900"
                  aria-label={`Remove author ${a}`}
                >
                  <i className="fa fa-times text-[10px]" aria-hidden />
                </button>
              </span>
            ))}
          </div>
        )}

        {errors.authors && (
          <FieldError>
            {typeof errors.authors.message === "string"
              ? errors.authors.message
              : "At least one author is required."}
          </FieldError>
        )}
      </div>
    </div>
  );
}
