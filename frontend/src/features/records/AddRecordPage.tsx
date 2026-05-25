import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { DpaConsentGate, DpaConsentModal } from "@/components/compliance";
import { UploadsStep } from "./steps/UploadsStep";

/**
 * Multi-step IP disclosure wizard (FR-M1-02, FR-M6-02).
 */
export default function AddRecordPage() {
  const [step, setStep]           = useState(1);
  const [dpaAccepted, setDpaAccepted] = useState(false);
  const [dpaModalOpen, setDpaModalOpen] = useState(false);

  const steps = ["Title & Abstract", "Record Details", "Uploads"];

  const handleSubmit = () => {
    if (!dpaAccepted) return;
    // TODO: POST /records/ then upload staged files; log DPA consent to audit (FR-M6-02)
  };

  return (
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
        {step === 1 && (
          <div>
            <p className="text-[13px] text-gray-500">TODO: implement TitleAbstractStep</p>
            <p className="text-[12px] text-gray-400 mt-2">
              Fields: title, year_accomplished, year_completed, abstract (TipTap), abstract_file,
              record_type, classification, psced, adviser
            </p>
            <button
              type="button"
              onClick={() => setStep(2)}
              className="mt-4 bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]"
            >
              Next
            </button>
          </div>
        )}

        {step === 2 && (
          <div>
            <p className="text-[13px] text-gray-500">TODO: implement RecordDetailsStep</p>
            <p className="text-[12px] text-gray-400 mt-2">
              Sections: Authors, Publication, Conferences, Budgets, Collaborations
            </p>
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="border border-gray-200 px-6 py-2 rounded-lg text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            <UploadsStep />

            <DpaConsentGate
              accepted={dpaAccepted}
              onAcceptedChange={setDpaAccepted}
              onViewTerms={() => setDpaModalOpen(true)}
            />

            <div className="flex gap-2 mt-4">
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
                disabled={!dpaAccepted}
                title={dpaAccepted ? undefined : "Accept the Data Privacy Act terms to submit"}
                className="bg-[#6B0F12] text-white px-6 py-2 rounded-lg text-[13px] font-semibold
                  hover:bg-[#7d1215] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[#6B0F12]"
              >
                Submit Record
              </button>
            </div>
          </div>
        )}
      </div>

      <DpaConsentModal open={dpaModalOpen} onClose={() => setDpaModalOpen(false)} />
    </div>
  );
}
