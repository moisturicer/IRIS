import { useEffect, useRef, useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { DpaConsentInline } from "@/components/compliance";
import { TypeRouteStep }     from "./steps/TypeRouteStep";
import { PaperDetailsStep }  from "./steps/PaperDetailsStep";
import { UploadsStep } from "./steps/UploadsStep";
import { recordFormSchema, type RecordFormValues } from "./recordFormSchema";
import { recordsApi }   from "@/api/records";
import { useUIStore }   from "@/store/ui.store";
import { routeForTypeName } from "@/lib/submissionRoutes";
import type { RecordType } from "@/types/records";
import { cn } from "@/lib/utils";

const STEPS = [
  { title: "What are you submitting?", short: "Type & Route" },
  { title: "Details", short: "Paper & Details" },
  { title: "Documents & consent", short: "Documents & Consent" },
];

/**
 * Submit Disclosure — the new-record wizard.
 *
 * Redesigned against IR-88 / docs/ui-ux/05-submission.md: type moves to step 1
 * so the route and required documents are visible before the user commits to
 * writing an abstract (docs/ui-ux/05-submission.md §3-4). Draft and submit are
 * two distinct, explicit actions (§"draft/submit boundary") rather than one
 * button that silently does both.
 *
 * Deliberately does NOT include an AI-driven "confirm what IRIS found" panel
 * some reference mockups show (drop a PDF, get title/abstract/IP-signals with
 * confidence scores) — nothing backs it (no ADR, no SRS/SDD line, no Jira
 * card; Docling is unimplemented, the LLM provider is undecided). See
 * iris-submit-disclosure-design memory.
 */
export default function AddRecordPage() {
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);

  const [step, setStep] = useState(1);
  const [recordTypes, setRecordTypes] = useState<RecordType[]>([]);

  // Once a draft exists server-side, every later save patches it instead of
  // creating a duplicate.
  const [draftId, setDraftId] = useState<number | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);

  const [dpaAccepted, setDpaAccepted] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // The manuscript is managed inside UploadsStep; lifted via callback rather
  // than form state, since it's a File object, not a form value. There is no
  // per-slot staging anymore -- see UploadsStep's hideSlots doc comment.
  const manuscriptRef = useRef<File | null>(null);

  const methods = useForm<RecordFormValues>({
    resolver: zodResolver(recordFormSchema),
    defaultValues: {
      title: "", abstract: "", authors: [], keywords: [], owners: [],
      is_ip: false, for_commercialization: false, community_extension: false,
      requires_ethics_review: false, requested_itso: false, requested_ierc: false, requested_ktto: false,
    },
    mode: "onTouched",
  });

  useEffect(() => {
    recordsApi.recordTypes().then(({ data }) => setRecordTypes(data.results ?? []));
  }, []);

  const selectedRecordType = methods.watch("record_type");
  const selectedTypeName = recordTypes.find((rt) => String(rt.id) === selectedRecordType)?.name;
  const isProposal = selectedTypeName === "Proposal";
  const route = routeForTypeName(selectedTypeName);
  const manuscriptStaged = manuscriptRef.current !== null;

  /** Build the payload the API accepts from current form values. */
  const buildPayload = (values: RecordFormValues) => ({
    title:                 values.title,
    abstract:              values.abstract,
    year_accomplished:     values.year,
    record_type:           values.record_type ? parseInt(values.record_type) : undefined,
    adviser:               values.adviser,
    classification:        values.classification,
    psced:                 values.psced,
    is_ip:                 values.is_ip,
    for_commercialization: values.for_commercialization,
    community_extension:   values.community_extension,
    requires_ethics_review: values.requires_ethics_review,
    requested_itso:         values.requested_itso,
    requested_ierc:         values.requested_ierc,
    requested_ktto:         values.requested_ktto,
    authors:               values.authors,
  });

  /** Create the draft once, then patch the same record on every later save. */
  const persistDraft = async (values: RecordFormValues) => {
    if (draftId) {
      const { data } = await recordsApi.update(draftId, buildPayload(values));
      return data.id;
    }
    const { data } = await recordsApi.create(buildPayload(values));
    setDraftId(data.id);
    return data.id;
  };

  const handleSaveDraft = async () => {
    const ok = await methods.trigger(["title"]);
    if (!ok) {
      setStep(2); // title lives on step 2 now
      return;
    }
    setSavingDraft(true);
    setSubmitError(null);
    try {
      await persistDraft(methods.getValues());
      addToast({ type: "success", message: "Saved as draft." });
    } catch {
      addToast({ type: "error", message: "Could not save draft. Please try again." });
    } finally {
      setSavingDraft(false);
    }
  };

  const goToStep2 = async () => {
    const ok = await methods.trigger(["record_type"]);
    if (ok) setStep(2);
  };

  const goToStep3 = async () => {
    const ok = await methods.trigger(["title", "abstract", "year", "authors", "adviser"]);
    if (!ok) return;
    if (isProposal && !methods.getValues("adviser")) {
      methods.setError("adviser", { message: "An adviser must be assigned before a Proposal can be submitted." });
      return;
    }
    setStep(3);
  };

  /** The actual work, run only after the user confirms in the modal. */
  const performSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const id = await persistDraft(methods.getValues());

      if (manuscriptRef.current) {
        await recordsApi.uploadManuscript(id, manuscriptRef.current);
      }

      await recordsApi.submit(id);
      setConfirmOpen(false);
      navigate(`/records/${id}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Something went wrong. Please try again.";
      setSubmitError(msg);
      setConfirmOpen(false);
    } finally {
      setSubmitting(false);
    }
  };

  // Gated on the manuscript and consent only -- not on every "Required"
  // UploadSlot. The backend's own submit() never checked slot completeness
  // either, and with 13 required slots seeded for Thesis/Research alone
  // (see IR-118), hard-gating on all of them would make NFR-U2's 10-minute
  // target unachievable with real files. Staff can still see what's missing
  // once the record reaches review.
  const requestSubmit = () => {
    if (!dpaAccepted || !manuscriptStaged) return;
    setConfirmOpen(true);
  };

  return (
    <FormProvider {...methods}>
      <div>
        <PageHeader
          title="Submit Research Disclosure"
          description="Institutional Research & IP Disclosure Intake Workflow (CIT-U IRIS)"
          actions={
            <>
              <Button variant="outline" size="sm" onClick={() => navigate("/workspace")}>
                Cancel
              </Button>
              <Button variant="secondary" size="sm" loading={savingDraft} onClick={handleSaveDraft}>
                Save as draft
              </Button>
            </>
          }
        />

        <p className="text-[12px] text-stone-400 mb-6 -mt-3">
          <Link to="/workspace" className="hover:text-brand">My Workspace</Link>
          <span className="mx-1.5">/</span>
          <span className="text-stone-600 font-medium">New Disclosure</span>
        </p>

        {/* Step indicator — <ol> with aria-current="step" per docs/ui-ux/05-submission.md a11y spec */}
        <ol className="flex items-center gap-0 mb-6" aria-label="Submission steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex items-center">
              <div
                aria-current={step === i + 1 ? "step" : undefined}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-[12px] font-semibold transition-colors",
                  step === i + 1 ? "bg-brand text-white" : step > i + 1 ? "text-emerald-600" : "text-stone-400",
                )}
              >
                <span
                  className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold",
                    step === i + 1 ? "bg-white text-brand" : step > i + 1 ? "bg-emerald-100" : "bg-stone-100",
                  )}
                >
                  {step > i + 1 ? <i className="fa fa-check text-[9px]" aria-hidden /> : i + 1}
                </span>
                {s.title}
              </div>
              {i < STEPS.length - 1 && <div className="w-8 h-px bg-stone-200 mx-1" />}
            </li>
          ))}
        </ol>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          {/* All steps stay mounted -- CSS visibility preserves RHF values and UploadsStep local state */}

          <div style={{ display: step === 1 ? "block" : "none" }}>
            <TypeRouteStep />
            <div className="mt-6">
              <Button onClick={goToStep2}>Continue to Details →</Button>
            </div>
          </div>

          <div style={{ display: step === 2 ? "block" : "none" }}>
            <PaperDetailsStep />
            <div className="flex gap-2 mt-6">
              <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
              <Button onClick={goToStep3}>Continue to Documents →</Button>
            </div>
          </div>

          <div style={{ display: step === 3 ? "block" : "none" }}>
            <UploadsStep
              hideSlots
              onManuscriptChange={(file) => { manuscriptRef.current = file; }}
              recordTypeId={selectedRecordType ? parseInt(selectedRecordType) : undefined}
            />

            <div className="mt-5">
              <DpaConsentInline accepted={dpaAccepted} onAcceptedChange={setDpaAccepted} />
            </div>

            {submitError && (
              <p className="mt-4 text-[13px] text-red-600" role="alert">{submitError}</p>
            )}

            <div className="flex gap-2 mt-6">
              <Button variant="outline" onClick={() => setStep(2)}>Back</Button>
              <Button
                onClick={requestSubmit}
                disabled={!dpaAccepted || !manuscriptStaged}
                title={
                  !manuscriptStaged
                    ? "Attach your manuscript to continue"
                    : !dpaAccepted
                      ? "Accept the Data Privacy Act terms to continue"
                      : undefined
                }
              >
                Submit for Review →
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Modal open={confirmOpen} onClose={() => (submitting ? undefined : setConfirmOpen(false))} title="Submit this disclosure?">
        <div className="p-5">
          <p className="text-[13px] text-gray-700 leading-relaxed">
            Submitting sends this to {route?.firstStage ?? "the first reviewer"}. You will not
            be able to edit it while it is under review.
          </p>
          {submitError && <p className="text-[13px] text-red-600 mt-3" role="alert">{submitError}</p>}
          <div className="flex justify-end gap-2 mt-5">
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={submitting}>
              Keep editing
            </Button>
            <Button onClick={performSubmit} loading={submitting}>
              Yes, submit for review
            </Button>
          </div>
        </div>
      </Modal>
    </FormProvider>
  );
}
