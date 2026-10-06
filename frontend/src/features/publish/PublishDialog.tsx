/**
 * Publish: starting a submission is a short dialog (IR-408; spec §4.4).
 *
 * It replaces the Submit Disclosure page and its wizard. There are three steps,
 * the fewest that keep the upload, the confirmation and the consent separate:
 *
 *   1. **Your manuscript** — the type, and the PDF. Choosing the file creates
 *      the draft at once, titled from the file name, so nothing typed later
 *      can be lost, and the server starts reading the PDF straight away.
 *   2. **Details** — `MetadataForm`, patched onto the draft on Continue.
 *   3. **Review & submit** — every value, consent, Submit.
 *
 * **Opened by the URL**: `/?publish=new` starts one, `/?publish=<draftId>`
 * resumes one at its first incomplete step. Creating the draft rewrites the
 * URL to its id, so a reload resumes rather than starting over. Closing clears
 * the parameter and keeps the draft.
 *
 * It decides no workflow. The type list is the server's, the author picks no
 * office (the hints carry `requested_*` only because the legacy pipeline routes
 * on them until IR-260; see `metadataPayload`), and the confirmation names
 * whoever the server says holds the record now.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { FormProvider, useForm, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { rolesFor } from "@/lib/access";
import { tabbableWithin } from "@/lib/focusTrap";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { User } from "@/types/auth";
import type { Classification, PSCEDClassification, RecordType, TrackerHolder } from "@/types/records";

import {
  METADATA_FIELD_IDS,
  METADATA_FIELD_ORDER,
  MORE_DETAILS_FIELDS,
  MetadataForm,
} from "@/features/records/metadata/MetadataForm";
import {
  emptyMetadata,
  metadataPayload,
  metadataSchema,
  type MetadataValues,
} from "@/features/records/metadata/metadataSchema";
import { personName } from "@/features/records/metadata/personName";

import {
  describeFailure,
  firstIncompleteStep,
  isProposal,
  provisionalTitle,
  stateFromDraft,
  type ApiFailure,
  type PublishStep,
} from "./draft";
import { ManuscriptStep, type ManuscriptUpload } from "./ManuscriptStep";
import { PublishSuccess, successHeadline } from "./PublishSuccess";
import { ReviewStep } from "./ReviewStep";

export const PUBLISH_PARAM = "publish";

const STEPS: Array<{ step: PublishStep; title: string }> = [
  { step: 1, title: "Your manuscript" },
  { step: 2, title: "Details" },
  { step: 3, title: "Review & submit" },
];

/** The server's field names, as the form labels them. */
const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  abstract: "Abstract",
  adviser: "Adviser",
  authors: "Authors",
  year_accomplished: "Year",
  classification: "Field of research",
  psced: "PSCED classification",
  record_type: "Type",
  abstract_file: "Manuscript",
};

/** Server field → form field, where they differ in name. */
const FORM_FIELD: Record<string, keyof MetadataValues> = {
  title: "title",
  abstract: "abstract",
  adviser: "adviser",
  authors: "authors",
  year_accomplished: "year",
  classification: "classification",
  psced: "psced",
};

/**
 * Mounted on the home route. Renders nothing unless the URL asks for Publish
 * and the signed-in user may author a record; the server's `IsAuthor` is the
 * real boundary, this only keeps the dialog from opening onto a refusal.
 */
export function PublishDialog() {
  const [params, setParams] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  // Bumped by "Publish another", so the flow starts from nothing.
  const [instance, setInstance] = useState(0);

  const target = params.get(PUBLISH_PARAM);
  const role = user?.role_name ?? null;
  const isAuthor = role != null && rolesFor("submit").includes(role);

  const setTarget = useCallback(
    (value: string | null) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value == null) next.delete(PUBLISH_PARAM);
          else next.set(PUBLISH_PARAM, value);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  if (target == null || !isAuthor || !user) return null;

  return (
    <PublishFlow
      key={instance}
      initialTarget={target}
      user={user}
      onDraftCreated={(id) => setTarget(String(id))}
      onClose={() => setTarget(null)}
      onRestart={() => {
        setTarget("new");
        setInstance((n) => n + 1);
      }}
    />
  );
}

type Phase =
  | { kind: "loading" }
  | { kind: "loadError" }
  | { kind: "notFound" }
  | { kind: "notDraft"; recordId: number }
  | { kind: "form" }
  | { kind: "success"; recordId: number; holders: TrackerHolder[] | null; adviserName: string | null };

interface Lists {
  recordTypes:     RecordType[];
  advisers:        User[];
  classifications: Classification[];
  psceds:          PSCEDClassification[];
}

const NO_LISTS: Lists = { recordTypes: [], advisers: [], classifications: [], psceds: [] };

interface PublishFlowProps {
  initialTarget:  string;
  user:           User;
  onDraftCreated: (id: number) => void;
  onClose:        () => void;
  onRestart:      () => void;
}

function PublishFlow({ initialTarget, user, onDraftCreated, onClose, onRestart }: PublishFlowProps) {
  // Read once. Creating the draft rewrites the URL from "new" to its id, and
  // that must not reload the flow under an upload in progress.
  const [startTarget] = useState(initialTarget);
  const selfId = user.id;
  const schema = useMemo(() => metadataSchema(selfId), [selfId]);
  const form = useForm<MetadataValues>({
    resolver: zodResolver(schema),
    defaultValues: emptyMetadata(personName(user)),
    mode: "onTouched",
    // Focus is moved by hand: the adviser is a custom control, and a field
    // inside a closed More details must be opened before it can take focus.
    shouldFocusError: false,
  });

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [lists, setLists] = useState<Lists>(NO_LISTS);
  // Which reference lists failed. Details still opens; a failed list's field is
  // left out of the save so a resumed draft's value is not erased.
  const [listsFailed, setListsFailed] = useState({ advisers: false, classification: false, psced: false });
  const [attempt, setAttempt] = useState(0);

  const [step, setStep] = useState<PublishStep>(1);
  const [typeId, setTypeId] = useState<number | null>(null);
  // The type the server holds, so Continue saves only a change.
  const savedTypeId = useRef<number | null>(null);
  // A ref as well as state: a retry reads it from a closure made before the
  // draft existed, and must not create a second one.
  const draftIdRef = useRef<number | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);

  const [upload, setUpload] = useState<ManuscriptUpload>({ status: "idle" });
  const fileRef = useRef<File | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [moreOpen, setMoreOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stepFailure, setStepFailure] = useState<ApiFailure | null>(null);
  const [dpaAccepted, setDpaAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitFailure, setSubmitFailure] = useState<ApiFailure | null>(null);
  const [confirmingClose, setConfirmingClose] = useState(false);
  // Escape or Close put the question on screen; focus goes with it, once.
  const keepUploadingRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (confirmingClose) keepUploadingRef.current?.focus();
  }, [confirmingClose]);
  const [announcement, setAnnouncement] = useState("");

  /* ── Load the lists, then the draft if one was named ─────────────────── */
  useEffect(() => {
    let cancelled = false;
    setPhase({ kind: "loading" });

    (async () => {
      const [types, advisers, classifications, psceds] = await Promise.allSettled([
        recordsApi.recordTypes(),
        accountsApi.listAdvisers(),
        recordsApi.classifications(),
        recordsApi.pscedList(),
      ]);
      if (cancelled) return;
      // Without the types nothing can start; the other three only degrade step 2.
      if (types.status === "rejected") {
        setPhase({ kind: "loadError" });
        return;
      }
      const loaded: Lists = {
        recordTypes: types.value.data.results ?? [],
        advisers: advisers.status === "fulfilled" ? advisers.value.data.results ?? [] : [],
        classifications: classifications.status === "fulfilled" ? classifications.value.data.results ?? [] : [],
        psceds: psceds.status === "fulfilled" ? psceds.value.data.results ?? [] : [],
      };
      setLists(loaded);
      setListsFailed({
        advisers: advisers.status === "rejected",
        classification: classifications.status === "rejected",
        psced: psceds.status === "rejected",
      });

      if (startTarget === "new") {
        setPhase({ kind: "form" });
        return;
      }

      const id = Number(startTarget);
      if (!Number.isInteger(id) || id <= 0) {
        setPhase({ kind: "notFound" });
        return;
      }
      try {
        const { data: record } = await recordsApi.detail(id);
        if (cancelled) return;
        if (record.pipeline_status !== "draft") {
          setPhase({ kind: "notDraft", recordId: id });
          return;
        }
        const state = stateFromDraft(record, loaded);
        form.reset(state.values);
        draftIdRef.current = id;
        setDraftId(id);
        setTypeId(state.typeId);
        savedTypeId.current = state.typeId;
        const hasManuscript = Boolean(record.abstract_file);
        setUpload(hasManuscript ? { status: "done", fileName: null, size: null } : { status: "idle" });
        setStep(firstIncompleteStep({ typeId: state.typeId, hasManuscript, values: state.values }, selfId));
        setPhase({ kind: "form" });
      } catch (err) {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        setPhase(status === 404 ? { kind: "notFound" } : { kind: "loadError" });
      }
    })();

    return () => {
      cancelled = true;
    };
    // `form`, `selfId` and `startTarget` are fixed for this flow's life;
    // `attempt` is Try again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  // Each step renders its own actions, so the button that was pressed is gone
  // after a step change and focus would fall to <body>. Move it to the new
  // step's first control instead. Not for the step the form first opens on
  // (a resumed draft sets it while loading): the dialog's open focus has that.
  const stepRef = useRef<HTMLDivElement>(null);
  const shownStep = useRef<PublishStep | null>(null);
  useEffect(() => {
    if (phase.kind !== "form") return;
    const changed = shownStep.current !== null && shownStep.current !== step;
    shownStep.current = step;
    const root = stepRef.current;
    if (changed && root) (tabbableWithin(root)[0] ?? root).focus();
  }, [step, phase.kind]);

  // Stop an upload still running when the dialog goes away.
  useEffect(() => () => abortRef.current?.abort(), []);

  function goTo(next: PublishStep) {
    setStep(next);
    setStepFailure(null);
    setAnnouncement(`Step ${next} of 3: ${STEPS[next - 1].title}`);
  }

  /* ── Step 1: create the draft once, then upload onto it ─────────────── */
  async function startUpload() {
    const file = fileRef.current;
    if (!file || typeId == null) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setUpload({ status: "uploading", fileName: file.name, progress: 0 });

    try {
      let id = draftIdRef.current;
      if (id == null) {
        const title = provisionalTitle(file.name);
        const { data } = await recordsApi.create({ title, record_type: typeId });
        // Closed while the draft was being created: keep the draft, but do not
        // write its id into the URL, which would reopen the dialog.
        if (controller.signal.aborted) return;
        id = data.id;
        draftIdRef.current = id;
        setDraftId(id);
        savedTypeId.current = typeId;
        onDraftCreated(id);
        if (!form.getValues("title")) form.setValue("title", title);
      }
      await recordsApi.uploadManuscript(id, file, {
        signal: controller.signal,
        onProgress: (progress) =>
          setUpload((u) => (u.status === "uploading" ? { ...u, progress } : u)),
      });
      setUpload({ status: "done", fileName: file.name, size: file.size });
    } catch (err) {
      if (controller.signal.aborted) return;
      const failure = describeFailure(err, "The upload failed.");
      setUpload({
        status: "failed",
        fileName: file.name,
        error: failure.fields.abstract_file ?? failure.fields.title ?? failure.message,
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  function handleFile(file: File) {
    fileRef.current = file;
    void startUpload();
  }

  async function continueFromManuscript() {
    const id = draftIdRef.current;
    if (id == null || typeId == null) return;
    if (typeId !== savedTypeId.current) {
      setSaving(true);
      try {
        await recordsApi.update(id, { record_type: typeId });
        savedTypeId.current = typeId;
      } catch (err) {
        setStepFailure(describeFailure(err, "We couldn't save the type. Try again."));
        return;
      } finally {
        setSaving(false);
      }
    }
    goTo(2);
  }

  /* ── Step 2: validate, then patch the draft ──────────────────────────── */
  function focusFirstError(errors: FieldErrors<MetadataValues>) {
    const field = METADATA_FIELD_ORDER.find((name) => errors[name]);
    if (!field) return;
    if (MORE_DETAILS_FIELDS.includes(field)) setMoreOpen(true);
    // After the render that opens More details or shows the error.
    requestAnimationFrame(() => document.getElementById(METADATA_FIELD_IDS[field])?.focus());
  }

  async function saveDetails(values: MetadataValues) {
    const id = draftIdRef.current;
    if (id == null) return;
    setSaving(true);
    setStepFailure(null);
    try {
      await recordsApi.update(id, metadataPayload(values, listsFailed));
      goTo(3);
    } catch (err) {
      const failure = describeFailure(err, "We couldn't save these details. Try again.");
      applyFieldErrors(failure);
      setStepFailure(failure);
    } finally {
      setSaving(false);
    }
  }

  /** Put the server's field errors on the form, so Details shows them in place. */
  function applyFieldErrors(failure: ApiFailure) {
    for (const [field, message] of Object.entries(failure.fields)) {
      const name = FORM_FIELD[field];
      if (name) form.setError(name, { type: "server", message });
    }
  }

  const continueFromDetails = form.handleSubmit(saveDetails, focusFirstError);

  /* ── Step 3: submit, then re-read who holds it ───────────────────────── */
  async function submit() {
    const id = draftIdRef.current;
    if (id == null || !dpaAccepted) return;
    setSubmitting(true);
    setSubmitFailure(null);
    try {
      await recordsApi.submit(id, dpaAccepted);
    } catch (err) {
      const failure = describeFailure(err, "IRIS couldn't submit this. Check the details and try again.");
      applyFieldErrors(failure);
      setSubmitFailure(failure);
      setSubmitting(false);
      return;
    }

    let holders: TrackerHolder[] | null = null;
    let holderAdviser: string | null = null;
    try {
      const { data } = await recordsApi.detail(id);
      holders = data.current_holders ?? [];
      // A holder is a party, not a person. When the party is the Adviser, the
      // person is the re-read record's own `adviser`, not the form's.
      const person = lists.advisers.find((a) => a.id === data.adviser);
      holderAdviser = person ? personName(person) : null;
    } catch {
      // Submitted all the same; the confirmation just names nobody.
    }
    setSubmitting(false);
    setAnnouncement(`Submitted. ${successHeadline(holders, holderAdviser)}.`);
    setPhase({ kind: "success", recordId: id, holders, adviserName: holderAdviser });
  }

  /* ── Closing ─────────────────────────────────────────────────────────── */
  function requestClose() {
    if (upload.status === "uploading") setConfirmingClose(true);
    else onClose();
  }

  function stopAndClose() {
    abortRef.current?.abort();
    onClose();
  }

  /* ── What the steps show ─────────────────────────────────────────────── */
  const values = form.watch();
  const adviser = lists.advisers.find((a) => a.id === values.adviser);
  const adviserName = adviser ? personName(adviser) : null;
  const typeName = lists.recordTypes.find((t) => t.id === typeId)?.name ?? "";

  const summary = {
    typeName,
    fileName: upload.status === "done" ? upload.fileName : null,
    title: values.title ?? "",
    abstract: values.abstract ?? "",
    adviserName: adviserName ?? "",
    authors: values.authors ?? [],
    year: values.year,
    classification: lists.classifications.find((c) => c.id === values.classification)?.name ?? null,
    psced: lists.psceds.find((p) => p.id === values.psced)?.name ?? null,
    hints: [
      values.is_ip && "Possible intellectual property",
      values.requires_ethics_review && "Human participants, animal subjects or sensitive data",
      values.for_commercialization && "Commercial potential",
    ].filter((hint): hint is string => Boolean(hint)),
  };

  let footer: ReactNode = null;
  if (phase.kind === "form" && !confirmingClose) {
    footer = (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-small text-stone-600">
          {draftId != null ? "Saved as a draft. You can close this and finish later." : " "}
        </p>
        <div className="ml-auto flex gap-2">
          {step > 1 && (
            <button
              type="button"
              onClick={() => goTo((step - 1) as PublishStep)}
              disabled={saving || submitting}
              className={cn(PILL_SECONDARY, FOCUS_RING)}
            >
              Back
            </button>
          )}
          {step === 1 && (
            <button
              type="button"
              onClick={() => void continueFromManuscript()}
              disabled={upload.status !== "done" || typeId == null || saving}
              className={cn(PILL_PRIMARY, FOCUS_RING)}
            >
              Continue
            </button>
          )}
          {step === 2 && (
            <button
              type="button"
              onClick={() => void continueFromDetails()}
              disabled={saving}
              className={cn(PILL_PRIMARY, FOCUS_RING)}
            >
              Continue
            </button>
          )}
          {step === 3 && (
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!dpaAccepted || submitting}
              className={cn(PILL_PRIMARY, FOCUS_RING)}
            >
              {submitting && <i className="fas fa-spinner fa-spin" aria-hidden />}
              Submit for review
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <Modal
      open
      onClose={requestClose}
      title="Publish your research"
      displayTitle
      sheet
      size="max-w-[720px]"
      footer={footer}
    >
      <span role="status" className="sr-only">
        {announcement}
      </span>

      {confirmingClose && (
        <div
          role="alertdialog"
          aria-labelledby="publish-close-title"
          aria-describedby="publish-close-body"
          className="mb-section rounded-xl border border-stone-300 bg-stone-50 p-card-compact"
        >
          <p id="publish-close-title" className="text-body font-medium text-stone-900">Stop the upload and close?</p>
          <p id="publish-close-body" className="mt-1 text-small text-stone-600">
            Your draft is kept, but the file has not finished uploading. You can add it when you come back.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              ref={keepUploadingRef}
              onClick={() => setConfirmingClose(false)}
              className={cn(PILL_PRIMARY, FOCUS_RING)}
            >
              Keep uploading
            </button>
            <button type="button" onClick={stopAndClose} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Stop and close
            </button>
          </div>
        </div>
      )}

      {phase.kind === "loading" && (
        <p className="flex items-center gap-2 py-section text-body text-stone-600" role="status">
          <i className="fas fa-spinner fa-spin" aria-hidden /> Getting things ready…
        </p>
      )}

      {phase.kind === "loadError" && (
        <Notice
          message="We couldn't open Publish just now."
          action={
            <button type="button" onClick={() => setAttempt((n) => n + 1)} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Try again
            </button>
          }
        />
      )}

      {phase.kind === "notFound" && (
        <Notice
          message="We couldn't find that draft. It may have been deleted, or it isn't yours."
          action={
            <button type="button" onClick={onRestart} className={cn(PILL_PRIMARY, FOCUS_RING)}>
              Start a new submission
            </button>
          }
        />
      )}

      {phase.kind === "notDraft" && (
        <Notice
          message="This record has already been submitted, so it can't be changed here."
          action={
            <Link to={`/records/${phase.recordId}`} className={cn(PILL_PRIMARY, FOCUS_RING)}>
              Open paper
            </Link>
          }
        />
      )}

      {phase.kind === "success" && (
        <PublishSuccess
          recordId={phase.recordId}
          holders={phase.holders}
          adviserName={phase.adviserName}
          isProposal={isProposal(typeName)}
          onPublishAnother={onRestart}
        />
      )}

      {phase.kind === "form" && (
        <>
          <StepIndicator current={step} />

          {stepFailure && step !== 3 && (
            <div role="alert" className={cn(LOAD_ERROR, "mb-section flex-wrap")}>
              <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
              <span className="flex-1">{stepFailure.message}</span>
              {stepFailure.network && (
                <button
                  type="button"
                  onClick={() => void (step === 1 ? continueFromManuscript() : continueFromDetails())}
                  className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-4")}
                >
                  Try again
                </button>
              )}
            </div>
          )}

          <div ref={stepRef} tabIndex={-1} className="outline-none">
          {step === 1 && (
            <ManuscriptStep
              recordTypes={lists.recordTypes}
              typeId={typeId}
              onTypeChange={setTypeId}
              upload={upload}
              onFile={handleFile}
              onRetry={() => void startUpload()}
            />
          )}

          {step === 2 && (
            <FormProvider {...form}>
              <form
                noValidate
                onSubmit={(e) => {
                  e.preventDefault();
                  void continueFromDetails();
                }}
              >
                <MetadataForm
                  advisers={lists.advisers}
                  classifications={lists.classifications}
                  psceds={lists.psceds}
                  selfId={selfId}
                  loadError={listsFailed.advisers || listsFailed.classification || listsFailed.psced}
                  moreOpen={moreOpen}
                  onMoreOpenChange={setMoreOpen}
                />
              </form>
            </FormProvider>
          )}

          {step === 3 && (
            <ReviewStep
              summary={summary}
              dpaAccepted={dpaAccepted}
              onDpaChange={setDpaAccepted}
              failure={submitFailure}
              onRetry={() => void submit()}
              onFixDetails={() => goTo(2)}
              fieldLabels={FIELD_LABELS}
              onEditManuscript={() => goTo(1)}
              onEditDetails={() => goTo(2)}
              onEditHints={() => {
                setMoreOpen(true);
                goTo(2);
              }}
            />
          )}
          </div>
        </>
      )}
    </Modal>
  );
}

/** Where the author is: done steps say so in words, the current one is marked. */
function StepIndicator({ current }: { current: PublishStep }) {
  return (
    <div className="mb-section">
      <p className="text-small text-stone-600 sm:hidden" aria-hidden>
        Step {current} of 3 · {STEPS[current - 1].title}
      </p>
      <ol aria-label="Publish steps" className="mt-2 grid grid-cols-3 gap-2 sm:mt-0">
        {STEPS.map(({ step, title }) => {
          const done = step < current;
          const isCurrent = step === current;
          return (
            <li key={step} aria-current={isCurrent ? "step" : undefined}>
              <span
                className={cn(
                  "block h-1 rounded-full",
                  isCurrent ? "bg-brand" : done ? "bg-stone-900" : "bg-stone-200",
                )}
                aria-hidden
              />
              <span
                aria-hidden
                className={cn(
                  "mt-2 hidden items-center gap-1.5 text-small sm:flex",
                  isCurrent ? "font-semibold text-stone-900" : done ? "text-stone-800" : "text-stone-600",
                )}
              >
                {done && <i className="fas fa-check text-label" aria-hidden />}
                {title}
              </span>
              <span className="sr-only">
                {`Step ${step}: ${title}`}
                {done ? ", completed" : ""}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Notice({ message, action }: { message: string; action: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-section py-section">
      <p className="text-body text-stone-800">{message}</p>
      {action}
    </div>
  );
}
