/**
 * Step 2 of the Submit Disclosure wizard — "Details".
 *
 * Merges the old TitleAbstractStep + RecordDetailsStep into the single step
 * docs/ui-ux/05-submission.md specifies ("2 · Details — Title, abstract,
 * authors, adviser (if Proposal), classification, IP flags"), and adds the
 * classification/PSCED/IP fields RecordWriteSerializer already accepts but no
 * step ever collected.
 *
 * Deliberately NOT here: an AI-extracted "confirm what IRIS found" panel. The
 * mockup shows one (drop a PDF, get title/abstract/authors/IP-signals with
 * confidence badges) but nothing backs it — no ADR, no SRS/SDD line, no Jira
 * card; Docling is unimplemented (ADR-006 defers it) and the LLM provider is
 * undecided (D-4). See iris-submit-disclosure-design memory for the search
 * that confirmed this. This step stays manual entry — real, not fabricated.
 *
 * Also collects the ADR-018 (Proposed) office-routing questions: an ethics
 * trigger with no upstream flag to derive from, and the actual office
 * request (ITSO/IERC/KTTO), pre-checked from the IP/ethics answers above but
 * independently overridable — the student decides, the system suggests.
 */
import { useEffect, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/Input";
import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import type { User } from "@/types/auth";
import type { RecordType, Classification, PSCEDClassification } from "@/types/records";
import type { RecordFormValues } from "../recordFormSchema";

export function PaperDetailsStep() {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = useFormContext<RecordFormValues>();

  const abstract        = watch("abstract") ?? "";
  const authors          = watch("authors") ?? [];
  const selectedTypeId   = watch("record_type");
  const [authorInput, setAuthorInput] = useState("");

  const [advisers,       setAdvisers]       = useState<User[]>([]);
  const [recordTypes,    setRecordTypes]    = useState<RecordType[]>([]);
  const [classifications,setClassifications]= useState<Classification[]>([]);
  const [psceds,         setPsceds]         = useState<PSCEDClassification[]>([]);
  const [loadingData,    setLoadingData]    = useState(true);
  const [loadError,      setLoadError]      = useState(false);

  const selectedTypeName = recordTypes.find((rt) => String(rt.id) === selectedTypeId)?.name;
  const isProposal       = selectedTypeName === "Proposal";
  const isProject        = selectedTypeName === "Project";
  const hasOfficeRouting = selectedTypeName === "Thesis / Research" || isProject;

  // Suggestion signals -> office requests. Mapped from each office's own
  // SRS-defined scope: ITSO does technical/patentability review, KTTO does
  // commercial evaluation, IERC does ethics review. community_extension maps
  // to no office -- none of the three's scope covers it.
  const isIp                = watch("is_ip");
  const forCommercialization = watch("for_commercialization");
  const requiresEthicsReview = watch("requires_ethics_review");

  // Each effect only re-fires when its own signal changes, so a student's
  // manual override of an office checkbox survives unrelated edits -- it's
  // only re-suggested if the specific flag it came from changes again.
  useEffect(() => {
    if (isProject) setValue("requested_itso", Boolean(isIp));
  }, [isIp, isProject, setValue]);

  useEffect(() => {
    setValue("requested_ktto", Boolean(forCommercialization));
  }, [forCommercialization, setValue]);

  useEffect(() => {
    setValue("requested_ierc", Boolean(requiresEthicsReview));
  }, [requiresEthicsReview, setValue]);

  useEffect(() => {
    setLoadError(false);
    Promise.all([
      accountsApi.listAdvisers(),
      recordsApi.recordTypes(),
      recordsApi.classifications(),
      recordsApi.pscedList(),
    ])
      .then(([advisersRes, typesRes, classRes, pscedRes]) => {
        setAdvisers(advisersRes.data.results ?? []);
        setRecordTypes(typesRes.data.results ?? []);
        setClassifications(classRes.data.results ?? []);
        setPsceds(pscedRes.data.results ?? []);
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

      {/* Title */}
      <div>
        <label htmlFor="title" className="block text-[13px] font-medium text-gray-700 mb-1">
          Title <span className="text-red-500">*</span>
        </label>
        <input
          id="title"
          {...register("title")}
          aria-invalid={Boolean(errors.title)}
          aria-describedby={errors.title ? "title-error" : undefined}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            ${errors.title ? "border-red-400 focus:border-red-500" : "border-gray-300 focus:border-brand"} focus:ring-1`}
          placeholder="Full title of the research"
        />
        {errors.title && (
          <p id="title-error" className="text-[12px] text-red-500 mt-1">{errors.title.message}</p>
        )}
      </div>

      {/* Abstract */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label htmlFor="abstract" className="text-[13px] font-medium text-gray-700">
            Abstract <span className="text-red-500">*</span>
          </label>
          <span className="text-[11px] text-gray-500">{abstract.length} / 5000</span>
        </div>
        <textarea
          id="abstract"
          {...register("abstract")}
          rows={6}
          maxLength={5000}
          aria-invalid={Boolean(errors.abstract)}
          aria-describedby={errors.abstract ? "abstract-error" : undefined}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors resize-none
            ${errors.abstract ? "border-red-400 focus:border-red-500" : "border-gray-300 focus:border-brand"} focus:ring-1`}
          placeholder="Brief summary of the research..."
        />
        {errors.abstract && (
          <p id="abstract-error" className="text-[12px] text-red-500 mt-1">{errors.abstract.message}</p>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-5">
        <Input
          label="Year Accomplished"
          type="number"
          {...register("year", { valueAsNumber: true })}
          error={errors.year?.message}
        />

        {/* Adviser — required only for Proposal */}
        <div>
          <label htmlFor="adviser" className="block text-[13px] font-medium text-gray-700 mb-1">
            Adviser{" "}
            {isProposal ? (
              <span className="text-red-500">*</span>
            ) : (
              <span className="text-gray-500 font-normal text-[12px]">(optional for this type)</span>
            )}
          </label>
          <select
            id="adviser"
            {...register("adviser", {
              // valueAsNumber turns an empty (unselected) option into NaN, not
              // undefined -- and z.number().optional() only rescues undefined,
              // so an optional field with nothing chosen failed validation with
              // "Expected number, received nan". Found live while walking this
              // step as Thesis/Research, where adviser is meant to be skippable.
              setValueAs: (v) => (v === "" ? undefined : Number(v)),
            })}
            disabled={loadingData}
            aria-invalid={Boolean(errors.adviser)}
            className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
              disabled:bg-gray-50 disabled:text-gray-500
              ${errors.adviser ? "border-red-400 focus:border-red-500" : "border-gray-300 focus:border-brand"} focus:ring-1`}
          >
            <option value="">
              {loadingData ? "Loading…" : advisers.length === 0 ? "No advisers available — contact RDCO" : "Select adviser"}
            </option>
            {advisers.map((a) => (
              <option key={a.id} value={a.id}>
                {a.last_name}, {a.first_name}{a.middle_initial ? ` ${a.middle_initial}.` : ""}
              </option>
            ))}
          </select>
          {errors.adviser && (
            <p className="text-[12px] text-red-500 mt-1">{errors.adviser.message}</p>
          )}
          {isProposal && !errors.adviser && (
            <p className="text-[11px] text-gray-500 mt-0.5">Required before this Proposal can be submitted.</p>
          )}
        </div>

        {/* Classification */}
        <div>
          <label htmlFor="classification" className="block text-[13px] font-medium text-gray-700 mb-1">
            Field of Research
          </label>
          <select
            id="classification"
            {...register("classification", { setValueAs: (v) => (v === "" ? undefined : Number(v)) })}
            disabled={loadingData}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-brand focus:ring-1 disabled:bg-gray-50 disabled:text-gray-500"
          >
            <option value="">{loadingData ? "Loading…" : "Select a field"}</option>
            {classifications.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        {/* PSCED */}
        <div>
          <label htmlFor="psced" className="block text-[13px] font-medium text-gray-700 mb-1">
            PSCED Classification
          </label>
          <select
            id="psced"
            {...register("psced", { setValueAs: (v) => (v === "" ? undefined : Number(v)) })}
            disabled={loadingData}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-brand focus:ring-1 disabled:bg-gray-50 disabled:text-gray-500"
          >
            <option value="">{loadingData ? "Loading…" : "Select a classification"}</option>
            {psceds.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Authors */}
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
            aria-label="Author name"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-brand focus:ring-1 focus:ring-brand"
          />
          <button
            type="button"
            onClick={addAuthor}
            className="px-3 py-2 bg-gray-100 rounded-lg text-[13px] text-gray-600 hover:bg-gray-200"
          >
            Add
          </button>
        </div>

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
                  aria-label={`Remove ${a}`}
                  className="text-gray-500 hover:text-gray-600"
                >
                  <i className="fa fa-times text-[10px]" aria-hidden />
                </button>
              </span>
            ))}
          </div>
        )}

        {errors.authors && (
          <p className="text-[12px] text-red-500 mt-1">
            {typeof errors.authors.message === "string" ? errors.authors.message : "At least one author is required."}
          </p>
        )}
      </div>

      {/* IP flags — submitter-settable. ip_type itself is staff-only (see recordFormSchema). */}
      <fieldset className="border border-gray-200 rounded-xl p-4">
        <legend className="px-1 text-[13px] font-medium text-gray-700">Intellectual Property</legend>
        <div className="flex flex-col gap-2.5 mt-1">
          <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
            <input type="checkbox" {...register("is_ip")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
            This work involves intellectual property worth protecting
          </label>
          <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
            <input type="checkbox" {...register("for_commercialization")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
            Flag for commercialization review
          </label>
          <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
            <input type="checkbox" {...register("community_extension")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
            This is a community extension project
          </label>
        </div>
        <p className="text-[11px] text-gray-500 mt-2.5">
          RDCO/KTTO set the specific IP classification (patent, copyright, etc.) after review.
        </p>
      </fieldset>

      {/* Ethics trigger — no upstream flag to derive this from; IERC's SRS
          scope is human/animal subjects and sensitive data specifically. */}
      <fieldset className="border border-gray-200 rounded-xl p-4">
        <legend className="px-1 text-[13px] font-medium text-gray-700">Ethics</legend>
        <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            {...register("requires_ethics_review")}
            className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand"
          />
          This research involves human participants, animal subjects, or sensitive personal data
        </label>
      </fieldset>

      {/* Office routing (ADR-018, Proposed) — Proposal has no parallel
          offices at all; ITSO only applies to Project (see submissionRoutes). */}
      {hasOfficeRouting && (
        <fieldset className="border border-gray-200 rounded-xl p-4">
          <legend className="px-1 text-[13px] font-medium text-gray-700">
            Which offices should review this?
          </legend>
          <p className="text-[11px] text-gray-500 mb-2.5">
            Suggested from your answers above — uncheck anything that doesn't apply. RDCO
            confirms this once your disclosure reaches intake.
          </p>
          <div className="flex flex-col gap-2.5">
            {isProject && (
              <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
                <input type="checkbox" {...register("requested_itso")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
                <span>
                  <span className="font-medium">ITSO</span> — technical review and patentability assessment
                </span>
              </label>
            )}
            <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
              <input type="checkbox" {...register("requested_ktto")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
              <span>
                <span className="font-medium">KTTO</span> — commercialization and industry-partnership review
              </span>
            </label>
            <label className="flex items-center gap-2.5 text-[13px] text-gray-700 cursor-pointer">
              <input type="checkbox" {...register("requested_ierc")} className="w-4 h-4 rounded border-gray-300 text-brand focus:ring-brand" />
              <span>
                <span className="font-medium">IERC</span> — ethics review (human/animal subjects, sensitive data)
              </span>
            </label>
          </div>
          <p className="text-[11px] text-gray-500 mt-2.5">
            Not sure? Leave everything unchecked — RDCO can still route it to the right office
            at intake.
          </p>
        </fieldset>
      )}
    </div>
  );
}
