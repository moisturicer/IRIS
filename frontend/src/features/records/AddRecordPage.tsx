import { useRef, useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TitleAbstractStep }  from "./steps/TitleAbstractStep";
import { RecordDetailsStep }  from "./steps/RecordDetailsStep";
import { UploadsStep, type StagedFile } from "./steps/UploadsStep";
import { recordFormSchema, type RecordFormValues } from "./recordFormSchema";
import { recordsApi }   from "@/api/records";
import { documentsApi } from "@/api/documents";

/**
 * Multi-step form for adding a new record.
 * Steps:
 *   1. Title & Abstract  — TitleAbstractStep
 *   2. Record Details    — RecordDetailsStep (year, type, authors, keywords)
 *   3. Uploads           — UploadsStep (one file per required slot)
 *
 * On submit:
 *   1. POST /records/            → creates record in draft
 *   2. POST /documents/submit/   → uploads each staged file
 *   3. POST /records/<id>/submit/→ transitions draft → adviser_review
 */
export default function AddRecordPage() {
  const navigate = useNavigate();
  const [step, setStep]       = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Staged files are managed inside UploadsStep; we lift them up via callback
  const stagedRef = useRef<Record<number, StagedFile>>({});

  const methods = useForm<RecordFormValues>({
    resolver: zodResolver(recordFormSchema),
    defaultValues: { title: "", abstract: "", authors: [], keywords: [], owners: [] },
    mode: "onTouched",
  });

  // Watch record_type so we can filter upload slots and conditionally validate adviser
  const selectedRecordType = methods.watch("record_type");

  const steps = ["Title & Abstract", "Record Details", "Uploads"];

  const handleSubmit = methods.handleSubmit(async (values) => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      // 1. Create the record (authors list is persisted by the serializer)
      const { data: record } = await recordsApi.create({
        title:             values.title,
        abstract:          values.abstract,
        year_accomplished: values.year,
        record_type:       values.record_type ? parseInt(values.record_type) : undefined,
        adviser:           values.adviser,
        authors:           values.authors,
      });

      // 2. Upload every staged file (required slots)
      const uploads = Object.values(stagedRef.current);
      await Promise.all(
        uploads.map((sf) => documentsApi.upload(record.id, sf.slotId, sf.file))
      );

      // 3. Submit the record into the approval pipeline
      await recordsApi.submit(record.id);

      navigate(`/records/${record.id}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Something went wrong. Please try again.";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <FormProvider {...methods}>
    <div>
      <PageHeader title="Add Record" description="Submit a new research record for review." />

      <div className="flex items-center gap-0 mb-6">
        {steps.map((label, i) => (
          <div key={label} className="flex items-center">
            <div
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[12px] font-semibold transition-colors ${
                step === i + 1
                  ? "bg-[#6B0F12] text-white"
                  : step > i + 1
                    ? "text-green-600"
                    : "text-gray-400"
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold ${
                  step === i + 1
                    ? "bg-white text-[#6B0F12]"
                    : step > i + 1
                      ? "bg-green-100"
                      : "bg-gray-100"
                }`}
              >
                {i + 1}
              </span>
              {label}
            </div>
            {i < steps.length - 1 && <div className="w-8 h-px bg-gray-200 mx-1" />}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {/* All steps stay mounted — CSS visibility preserves RHF values and UploadsStep local state */}

        {/* Step 1 — Title & Abstract */}
        <div style={{ display: step === 1 ? "block" : "none" }}>
          <TitleAbstractStep />
          <button
            type="button"
            onClick={async () => {
              const ok = await methods.trigger(["title", "abstract"]);
              if (ok) setStep(2);
            }}
            className="mt-6 bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]"
          >
            Next
          </button>
        </div>

        {/* Step 2 — Record Details */}
        <div style={{ display: step === 2 ? "block" : "none" }}>
          <RecordDetailsStep />
          <div className="flex gap-2 mt-6">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="border border-gray-200 px-6 py-2 rounded-lg text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
            >
              Back
            </button>
            <button
              type="button"
              onClick={async () => {
                const ok = await methods.trigger(["year", "record_type", "adviser", "authors"]);
                if (ok) setStep(3);
              }}
              className="bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]"
            >
              Next
            </button>
          </div>
        </div>

        {/* Step 3 — Uploads */}
        <div style={{ display: step === 3 ? "block" : "none" }}>
          <UploadsStep
            onStagedChange={(staged) => { stagedRef.current = staged; }}
            recordTypeId={selectedRecordType ? parseInt(selectedRecordType) : undefined}
          />
          {submitError && (
            <p className="mt-4 text-[13px] text-red-600">{submitError}</p>
          )}
          <div className="flex gap-2 mt-6">
            <button
              type="button"
              onClick={() => setStep(2)}
              className="border border-gray-200 px-6 py-2 rounded-lg text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
            >
              Back
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              className="bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting ? "Submitting…" : "Submit Record"}
            </button>
          </div>
        </div>
      </div>

    </div>
    </FormProvider>
  );
}
