/**
 * Edit record page -- same wizard as AddRecordPage but pre-populated with existing data.
 * Only the record owner (or staff) can access this page.
 * Record must be in "draft" or "declined" status to be editable.
 *
 * TODO: guard against editing records in other pipeline stages (show read-only view).
 * TODO: auto-save draft to localStorage to prevent loss on accidental navigation.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { recordsApi }   from "@/api/records";
import { PageHeader }   from "@/components/layout/PageHeader";
import { Button }       from "@/components/ui/Button";
import { useUIStore }   from "@/store/ui.store";
import { TitleAbstractStep } from "./steps/TitleAbstractStep";
import { RecordDetailsStep } from "./steps/RecordDetailsStep";
import { UploadsStep }       from "./steps/UploadsStep";
import { DpaConsentGate, DpaConsentModal } from "@/components/compliance";
import { recordFormSchema, type RecordFormValues } from "./recordFormSchema";
import type { RecordFormData } from "@/types/records";

const STEPS = ["Title & Abstract", "Details", "Documents"];

export default function EditRecordPage() {
  const { id }   = useParams<{ id: string }>();
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);

  const [step, setStep]             = useState(0);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [dpaAccepted, setDpaAccepted] = useState(false);
  const [dpaModalOpen, setDpaModalOpen] = useState(false);

  const methods = useForm<RecordFormValues>({
    resolver: zodResolver(recordFormSchema),
    defaultValues: {
      title: "", abstract: "", year: new Date().getFullYear(),
      record_type: "",
      authors: [], keywords: [], owners: [],
    },
  });

  // Load existing record data
  useEffect(() => {
    if (!id) return;
    recordsApi.detail(Number(id)).then(({ data }) => {
      methods.reset({
        title:         data.title,
        abstract:      data.abstract ?? "",
        year:          data.year_accomplished ?? data.year_completed ?? new Date().getFullYear(),
        record_type:   data.record_type?.toString() ?? "",
        authors:       data.authors?.map((a) => a.name) ?? [],
        keywords:      data.keywords ?? [],
        owners:        data.owners?.map((o) => o.user) ?? [],
      });
    }).finally(() => setLoading(false));
  }, [id]);

  const handleSave = methods.handleSubmit(async (values) => {
    setSaving(true);
    try {
      const payload: Partial<RecordFormData> = {
        title:                 values.title,
        abstract:              values.abstract,
        year_accomplished:     values.year,
        year_completed:        values.year,
        record_type:           values.record_type ? Number(values.record_type) : undefined,

      };
      await recordsApi.update(Number(id), payload);
      addToast({ type: "success", message: "Record updated." });
      navigate(`/records/${id}`);
    } catch {
      addToast({ type: "error", message: "Save failed. Please try again." });
    } finally {
      setSaving(false);
    }
  });

  if (loading) return <div className="p-8 text-center text-gray-400 text-[13px]">Loading record...</div>;

  return (
    <FormProvider {...methods}>
      <div className="max-w-3xl">
        <PageHeader title="Edit Record" description="Update the details of this research record." />

        {/* Step indicator */}
        <div className="flex gap-0 mb-8">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                className={`flex items-center gap-2 text-[13px] font-medium
                  ${i === step ? "text-[#6B0F12]" : i < step ? "text-green-600 cursor-pointer" : "text-gray-400"}`}
              >
                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold
                  ${i === step ? "bg-[#6B0F12] text-white" : i < step ? "bg-green-600 text-white" : "bg-gray-200 text-gray-500"}`}
                >
                  {i < step ? <i className="fa fa-check text-[10px]" /> : i + 1}
                </span>
                {label}
              </button>
              {i < STEPS.length - 1 && (
                <span className="mx-3 text-gray-300 text-[11px]"><i className="fa fa-chevron-right" /></span>
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          {step === 0 && <TitleAbstractStep />}
          {step === 1 && <RecordDetailsStep />}
          {step === 2 && (
            <>
              <UploadsStep recordId={Number(id)} />
              <DpaConsentGate
                accepted={dpaAccepted}
                onAcceptedChange={setDpaAccepted}
                onViewTerms={() => setDpaModalOpen(true)}
              />
            </>
          )}
        </div>

        {/* Navigation */}
        <div className="flex justify-between mt-6">
          <Button
            variant="secondary"
            onClick={() => (step === 0 ? navigate(`/records/${id}`) : setStep(step - 1))}
          >
            {step === 0 ? "Cancel" : "Back"}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button
              onClick={async () => {
                const fields: Record<number, (keyof RecordFormValues)[]> = {
                  0: ["title", "abstract"],
                  1: ["record_type", "year"],
                };
                const ok = await methods.trigger(fields[step] as (keyof RecordFormValues)[]);
                if (ok) setStep(step + 1);
              }}
            >
              Next
            </Button>
          ) : (
            <Button
              loading={saving}
              disabled={!dpaAccepted}
              onClick={handleSave}
              title={dpaAccepted ? undefined : "Accept the Data Privacy Act terms to save"}
            >
              Save Changes
            </Button>
          )}
        </div>

        <DpaConsentModal open={dpaModalOpen} onClose={() => setDpaModalOpen(false)} />
      </div>
    </FormProvider>
  );
}
