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

export function RecordDetailsStep() {
  const {
    register,
    formState: { errors },
    watch,
    setValue,
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
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
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
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Record Type <span className="text-red-500">*</span>
        </label>
        <select
          {...register("record_type")}
          disabled={loadingData}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            disabled:bg-gray-50 disabled:text-gray-400
            ${errors.record_type
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
        >
          <option value="">{loadingData ? "Loading…" : "Select record type"}</option>
          {recordTypes.map((rt) => (
            <option key={rt.id} value={String(rt.id)}>{rt.name}</option>
          ))}
        </select>
        {errors.record_type && (
          <p className="text-[12px] text-red-500 mt-1">{errors.record_type.message}</p>
        )}
      </div>

      {/* Adviser — only required for Proposal; shown as optional for other types */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Adviser{" "}
          {isProposal ? (
            <span className="text-red-500">*</span>
          ) : (
            <span className="text-gray-400 font-normal text-[12px]">
              {selectedTypeName ? "(optional for this record type)" : "(select record type first)"}
            </span>
          )}
        </label>
        <select
          {...register("adviser", { valueAsNumber: true })}
          disabled={loadingData}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            disabled:bg-gray-50 disabled:text-gray-400
            ${errors.adviser
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
        >
          <option value="">{loadingData ? "Loading…" : "Select adviser"}</option>
          {advisers.map((a) => (
            <option key={a.id} value={a.id}>
              {a.last_name}, {a.first_name}{a.middle_initial ? ` ${a.middle_initial}.` : ""}
            </option>
          ))}
        </select>
        {errors.adviser && (
          <p className="text-[12px] text-red-500 mt-1">{errors.adviser.message}</p>
        )}
        {isProposal && (
          <p className="text-[11px] text-gray-400 mt-0.5">
            Proposal records must have an assigned adviser before submission.
          </p>
        )}
      </div>

      {/* Authors — required, min 1 */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Authors <span className="text-red-500">*</span>
        </label>
        <div className="flex gap-2 mb-2">
          <input
            value={authorInput}
            onChange={(e) => setAuthorInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addAuthor())}
            placeholder="Type author name and press Enter or Add"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
          />
          <button
            type="button"
            onClick={addAuthor}
            className="px-3 py-2 bg-gray-100 rounded-lg text-[13px] text-gray-600 hover:bg-gray-200"
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
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-100 rounded-full text-[12px] text-gray-700"
              >
                {a}
                <button
                  type="button"
                  onClick={() => removeAuthor(i)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <i className="fa fa-times text-[10px]" />
                </button>
              </span>
            ))}
          </div>
        )}

        {errors.authors && (
          <p className="text-[12px] text-red-500 mt-1">
            {typeof errors.authors.message === "string"
              ? errors.authors.message
              : "At least one author is required."}
          </p>
        )}
      </div>
    </div>
  );
}
