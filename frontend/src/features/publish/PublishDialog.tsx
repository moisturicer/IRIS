/**
 * Publish: starting a submission is a short dialog (IR-408; spec §4.4).
 *
 * It replaces the Submit Disclosure page and its wizard. There are three steps,
 * the fewest that keep the upload, the confirmation and the consent separate.
 * It asks nothing about an embargo: every paper starts embargoed, and only its
 * Adviser or RDCO date or release one (ADR-052 as amended for IR-882).
 *
 *   1. **Your manuscript** — the type, and the PDF. Choosing the file creates
 *      the draft at once, titled from the file name, so nothing typed later
 *      can be lost, and the server starts reading the PDF straight away.
 *   2. **Details** — `MetadataForm`, saved as the author works and again on
 *      Continue, each save checked against the draft's revision (`useAutosave`).
 *      The manuscript's own title and abstract are filled in once it has been
 *      read, with Undo, and its labelled authors, keywords and publication year
 *      offered (IR-833, `usePrefill` and `autofill`); none of it blocks Details.
 *   3. **Review & submit** — every value, consent, Submit.
 *
 * **Opened by the URL**: `/?publish=new` starts one, `/?publish=<draftId>`
 * resumes one at its first incomplete step. Creating the draft rewrites the
 * URL to its id, so a reload resumes rather than starting over. Closing clears
 * the parameter and keeps the draft.
 *
 * It decides no workflow. The type list is the server's, the author picks no
 * office (the hints are hints; see `metadataPayload`), and the confirmation
 * names whoever the server says holds the record now.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { recordsApi, type ManuscriptMatch } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { rolesFor } from "@/lib/access";
import { errorDetail } from "@/lib/errorDetail";
import { tabbableWithin } from "@/lib/focusTrap";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { AdviserOption, User } from "@/types/auth";
import type { Classification, MetadataSources, PSCEDClassification, RecordFormData, RecordType, TrackerHolder } from "@/types/records";

import { FORM_FIELD, MetadataForm, focusFirstInvalid } from "@/features/records/metadata/MetadataForm";
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
import { acceptedManuscript, ManuscriptStep, type ManuscriptUpload } from "./ManuscriptStep";
import { AUTOFILL_FIELDS, offerFor, planAutofill, sameValue, type AutofillField, type FieldOffer, type FormValue } from "./autofill";
import { isStaleEdit, useAutosave, type SaveStatus } from "./autosave";
import { AutofilledNote, PrefillChip } from "./PrefillChip";
import { usePrefill, type Prefill } from "./prefill";
import { PublishSuccess, successHeadline } from "./PublishSuccess";
import { ReviewStep } from "./ReviewStep";
import { IrisLoader } from "@/components/brand/IrisBrand";
import { PublishDetailsPreview } from "./PublishDetailsPreview";

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
  | { kind: "loadError"; message: string }
  | { kind: "notFound" }
  | { kind: "notDraft"; recordId: number }
  | { kind: "form" }
  | { kind: "success"; recordId: number; holders: TrackerHolder[] | null; adviserName: string | null };

interface Lists {
  recordTypes:     RecordType[];
  advisers:        AdviserOption[];
  classifications: Classification[];
  psceds:          PSCEDClassification[];
}

const NEUTRAL_PREFILL = "We couldn't read details from this file — fill them in below.";
const NOTHING_FOUND = "We read your PDF but found no details to fill in.";
const STALE_DRAFT = "This draft was changed somewhere else, so your latest changes weren't saved. Reload it to see the newer version.";

/** The field names the prefill's notes and announcements use. */
const FIELD_NAMES: Record<AutofillField, string> = {
  title: "title", abstract: "abstract", authors: "authors", keywords: "keywords", publication_year: "publication year",
};

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
    defaultValues: { ...emptyMetadata(personName(user)), owner_emails: user.email },
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
  const [listError, setListError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const [step, setStep] = useState<PublishStep>(1);
  const [typeId, setTypeId] = useState<number | null>(null);
  const [isContinuation, setIsContinuation] = useState(false);
  // The type the server holds, so Continue saves only a change.
  const savedTypeId = useRef<number | null>(null);
  // A ref as well as state: a retry reads it from a closure made before the
  // draft existed, and must not create a second one.
  const draftIdRef = useRef<number | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);

  const [upload, setUpload] = useState<ManuscriptUpload>({ status: "idle" });
  const fileRef = useRef<File | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Which uploaded file the prefill is about; a replacement bumps it as it
  // begins, which forgets the old file's reading and any reply still coming.
  const [uploadGeneration, setUploadGeneration] = useState(0);
  // The author's decision about each field the PDF can fill (`autofill`),
  // saved with the draft. `systemValues` is what the dialog itself last put
  // in a field, so any other change to it is the author's.
  const [decisions, setDecisions] = useState<MetadataSources>({});
  const systemValues = useRef<Partial<Record<AutofillField, unknown>>>({});
  // The draft revision last seen, which every Details save names (IR-833).
  const detailsRevision = useRef<number | null>(null);
  const [retryingRead, setRetryingRead] = useState(false);

  // Details saves itself while it is shown, unless a save met a newer draft.
  const watched = form.watch();
  const complete = completeBody(watched, decisions, listsFailed);
  const invalid = new Set((schema.safeParse(watched).error?.issues ?? []).map((issue) => String(issue.path[0])));
  const autosaveBody = Object.fromEntries(
    Object.entries(complete).filter(([key]) => !UNSAVED_UNTIL_CONTINUE.has(key) && !invalid.has(FORM_FIELD[key] ?? key)),
  );
  const autosave = useAutosave({
    enabled: phase.kind === "form" && step === 2 && draftId != null,
    payload: autosaveBody,
    complete,
    save: async (body) => {
      const id = draftIdRef.current;
      if (id != null) await patchDetails(id, body);
    },
  });

  const [moreOpen, setMoreOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stepFailure, setStepFailure] = useState<ApiFailure | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitFailure, setSubmitFailure] = useState<ApiFailure | null>(null);
  const [exactMatches, setExactMatches] = useState<ManuscriptMatch[]>([]);
  const [likelyMatches, setLikelyMatches] = useState<ManuscriptMatch[]>([]);
  const [matchesAcknowledged, setMatchesAcknowledged] = useState(false);
  const [matchFailure, setMatchFailure] = useState("");
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
        setPhase({ kind: "loadError", message: errorDetail(types.reason, "We couldn't open Publish just now.") });
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
      const listFailure = [advisers, classifications, psceds].find((result) => result.status === "rejected");
      setListError(listFailure ? errorDetail(listFailure.reason, "We couldn't load the adviser and classification lists. Close this and try again.") : null);

      // A reload after a save conflict reopens the draft this flow created.
      const target = draftIdRef.current != null ? String(draftIdRef.current) : startTarget;
      if (target === "new") {
        setPhase({ kind: "form" });
        return;
      }

      const id = Number(target);
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
        setIsContinuation(Boolean(record.lineage?.derived_from));
        form.reset(state.values);
        // Saved decisions come back as they were. A value the dialog or the
        // PDF supplied is still the system's until it changes.
        const onDraft = record.metadata_sources ?? {};
        setDecisions(onDraft);
        systemValues.current = Object.fromEntries(
          AUTOFILL_FIELDS.filter((field) => ["placeholder", "automatic", "accepted"].includes(onDraft[field]?.state ?? ""))
            .map((field) => [field, state.values[field]]),
        );
        detailsRevision.current = record.details_revision ?? null;
        autosave.reset(completeBody(state.values, onDraft, {
          classification: classifications.status === "rejected",
          psced: psceds.status === "rejected",
        }));
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
        setPhase(status === 404 ? { kind: "notFound" } : { kind: "loadError", message: errorDetail(err, "We couldn't open Publish just now.") });
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

    // A replacement attempt is not the accepted source. IR-831 keeps the
    // preceding valid Manuscript on the server when a replacement is refused,
    // so retain that accepted identity until this upload succeeds.
    const acceptedBeforeAttempt = acceptedManuscript(upload);
    const controller = new AbortController();
    abortRef.current = controller;
    setUpload({ status: "uploading", fileName: file.name, progress: 0 });
    // The old file's reading stops counting the moment a replacement begins.
    if (acceptedBeforeAttempt) setUploadGeneration((n) => n + 1);
    setExactMatches([]);
    setLikelyMatches([]);
    setMatchesAcknowledged(false);

    try {
      let id = draftIdRef.current;
      if (id == null) {
        const title = provisionalTitle(file.name);
        // The title made from the file name is a placeholder, saved as one, so
        // the PDF's own title may replace it, now or after a reopening.
        const placeholder = !form.getValues("title");
        const metadata_sources: MetadataSources = placeholder ? { title: { state: "placeholder" } } : {};
        const { data } = await recordsApi.create({ title, record_type: typeId, metadata_sources });
        // Closed while the draft was being created: keep the draft, but do not
        // write its id into the URL, which would reopen the dialog.
        if (controller.signal.aborted) return;
        id = data.id;
        draftIdRef.current = id;
        setDraftId(id);
        savedTypeId.current = typeId;
        detailsRevision.current = data.details_revision ?? null;
        autosave.reset({ title, metadata_sources });
        onDraftCreated(id);
        if (placeholder) {
          systemValues.current.title = title;
          form.setValue("title", title);
          setDecisions((prev) => ({ ...prev, title: { state: "placeholder" } }));
        }
      }
      await recordsApi.uploadManuscript(id, file, {
        signal: controller.signal,
        onProgress: (progress) =>
          setUpload((u) => (u.status === "uploading" ? { ...u, progress } : u)),
      });
      setUpload({ status: "done", fileName: file.name, size: file.size });
      setUploadGeneration((n) => n + 1);
      void refreshMatches(id).catch(() => setMatchFailure("Matches could not be checked. Try again before submitting."));
    } catch (err) {
      if (controller.signal.aborted) return;
      const failure = describeFailure(err, "The upload failed.");
      const data = (err as { response?: { data?: { code?: string; matches?: ManuscriptMatch[] } } })?.response?.data;
      if (data?.code === "exact_duplicate") setExactMatches(data.matches ?? []);
      setUpload({
        status: "failed",
        fileName: file.name,
        error: failure.fields.abstract_file ?? failure.fields.title ?? failure.message,
        accepted: acceptedBeforeAttempt,
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
        await patchDetails(id, { record_type: typeId });
        savedTypeId.current = typeId;
      } catch (err) {
        setStepFailure(isStaleEdit(err)
          ? { message: STALE_DRAFT, fields: {}, network: false }
          : describeFailure(err, "We couldn't save the type. Try again."));
        return;
      } finally {
        setSaving(false);
      }
    }
    goTo(2);
  }

  /* ── Step 2: saved as the author works, then validated and saved ─────── */
  /** One Details save, conditional on the revision this dialog last saw. */
  async function patchDetails(id: number, body: Partial<RecordFormData>) {
    const expected = detailsRevision.current;
    const { data } = await recordsApi.update(id, expected == null ? body : { ...body, expected_details_revision: expected });
    if (data?.details_revision != null) detailsRevision.current = data.details_revision;
  }

  async function saveDetails(values: MetadataValues) {
    const id = draftIdRef.current;
    if (id == null) return;
    setSaving(true);
    setStepFailure(null);
    try {
      // In the autosave queue, so no autosave names the same revision.
      const body = completeBody(values, decisions, listsFailed);
      await autosave.exclusive(() => patchDetails(id, body));
      autosave.markSaved(body);
      await refreshMatches(id).catch(() => setMatchFailure("Matches could not be checked. Try again before submitting."));
      goTo(3);
    } catch (err) {
      if (isStaleEdit(err)) {
        autosave.conflict();
        return;
      }
      const failure = describeFailure(err, "We couldn't save these details. Try again.");
      applyFieldErrors(failure);
      setStepFailure(failure);
    } finally {
      setSaving(false);
    }
  }

  function reloadDraft() {
    setAttempt((n) => n + 1);
  }

  /** Put the server's field errors on the form, so Details shows them in place. */
  function applyFieldErrors(failure: ApiFailure) {
    for (const [field, message] of Object.entries(failure.fields)) {
      const name = FORM_FIELD[field];
      if (name) form.setError(name, { type: "server", message });
    }
  }

  const continueFromDetails = form.handleSubmit(saveDetails, (errors) => focusFirstInvalid(errors, () => setMoreOpen(true)));

  async function refreshMatches(id: number) {
    const { data } = await recordsApi.duplicateMatches(id);
    setExactMatches(data.exact);
    setLikelyMatches(data.likely);
    setMatchesAcknowledged(data.acknowledged);
    setMatchFailure("");
  }

  useEffect(() => {
    if (phase.kind !== "form" || step !== 3 || draftId == null) return;
    let active = true;
    recordsApi.duplicateMatches(draftId).then(({ data }) => {
      if (!active) return;
      setExactMatches(data.exact);
      setLikelyMatches(data.likely);
      setMatchesAcknowledged(data.acknowledged);
    }).catch(() => { if (active) setMatchFailure("Matches could not be checked. Try again before submitting."); });
    return () => { active = false; };
  }, [draftId, phase.kind, step, uploadGeneration]);

  async function acknowledgeMatches() {
    const id = draftIdRef.current;
    if (id == null) return;
    try {
      const { data } = await recordsApi.acknowledgeDuplicates(id, likelyMatches.map((match) => match.id));
      setLikelyMatches(data.matches);
      setMatchesAcknowledged(data.acknowledged);
      setMatchFailure("");
    } catch {
      setMatchesAcknowledged(false);
      await refreshMatches(id).catch(() => undefined);
      setMatchFailure("The matches changed. Review the current list and acknowledge it again.");
    }
  }

  const acceptedUpload = acceptedManuscript(upload);
  const prefill = usePrefill({
    recordId: draftId,
    active: phase.kind === "form" && step === 2 && acceptedUpload != null,
    generation: uploadGeneration,
  });
  const reading: Prefill = prefill;

  /** Put a value in a field as the dialog, not the author. */
  function systemSet(field: AutofillField, value: FormValue) {
    systemValues.current[field] = value;
    form.setValue(field, value as never, { shouldDirty: true, shouldValidate: true });
  }

  // Fill in what the PDF supplies, where the author has not had their say.
  // Re-running is harmless: a filled field is `automatic` for this revision.
  useEffect(() => {
    if (reading.status !== "ready") return;
    const fills = planAutofill(reading.fields, reading.revision, decisions, form.getValues());
    if (fills.length === 0) return;
    for (const fill of fills) systemSet(fill.field, fill.value);
    setDecisions((prev) => ({ ...prev, ...Object.fromEntries(fills.map((fill) => [fill.field, fill.decision])) }));
    // `systemSet` and `form` are stable for this flow's life.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reading.status, reading.fields, reading.revision, decisions]);

  // Any change to a field that the dialog did not make is the author's, and
  // from then on no reading may replace it.
  useEffect(() => {
    const subscription = form.watch((all, { name }) => {
      if (!name || !(AUTOFILL_FIELDS as readonly string[]).includes(name)) return;
      const field = name as AutofillField;
      if (field in systemValues.current && sameValue(all[field], systemValues.current[field])) return;
      delete systemValues.current[field];
      // Editing a value the PDF supplied keeps which file it came from, so
      // that file's value is not offered back.
      setDecisions((prev) => {
        const before = prev[field];
        if (before?.state === "authored") return prev;
        const from = before?.state === "automatic" || before?.state === "accepted" ? before.source_revision : undefined;
        return { ...prev, [field]: from ? { state: "authored", source_revision: from } : { state: "authored" } };
      });
    });
    return () => subscription.unsubscribe();
  }, [form]);

  /** Fill a field from the PDF at the author's word, and put them in it. */
  function acceptSuggestion(field: AutofillField, value: FormValue) {
    systemSet(field, value);
    setDecisions((prev) => ({ ...prev, [field]: { state: "accepted", source_revision: reading.revision } }));
    form.setFocus(field);
  }

  function dismissSuggestion(field: AutofillField) {
    setDecisions((prev) => ({ ...prev, [field]: { state: "dismissed", source_revision: reading.revision } }));
    form.setFocus(field);
  }

  /** Put back what the field held before the PDF filled it in. */
  function undoAutofill(field: AutofillField) {
    systemSet(field, (decisions[field]?.previous ?? "") as FormValue);
    setDecisions((prev) => ({ ...prev, [field]: { state: "dismissed", source_revision: reading.revision } }));
    form.setFocus(field);
  }

  async function retryReading() {
    const id = draftIdRef.current;
    if (id == null) return;
    setRetryingRead(true);
    try {
      await recordsApi.retryExtraction(id, reading.revision);
    } catch {
      // A 409 means the manuscript changed, a 400 that it is no longer failed:
      // either way, asking again shows where it stands now.
    } finally {
      setRetryingRead(false);
      reading.checkAgain();
    }
  }

  /* ── Step 3: submit, then re-read who holds it ───────────────────────── */
  async function submit() {
    const id = draftIdRef.current;
    if (id == null) return;
    setSubmitting(true);
    setSubmitFailure(null);
    try {
      await recordsApi.submit(id);
    } catch (err) {
      const data = (err as { response?: { data?: { code?: string; matches?: ManuscriptMatch[] } } })?.response?.data;
      if (data?.code === "exact_duplicate") setExactMatches(data.matches ?? []);
      if (data?.code === "acknowledgement_required") {
        setLikelyMatches(data.matches ?? []);
        setMatchesAcknowledged(false);
      }
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
      holders = data.current_holders;
      // A holder is a party, not a person. When the party is the Adviser, the
      // person is the re-read record's own `adviser`, not the form's.
      const person = lists.advisers.find((a) => a.id === data.adviser);
      holderAdviser = person ? personName(person) : null;
    } catch {
      // Submitted all the same; the confirmation just names nobody.
    }
    setSubmitting(false);
    const headline = successHeadline(holders, holderAdviser);
    setAnnouncement(headline.startsWith("Sent") ? `Submitted. ${headline}.` : `${headline}.`);
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
  const values = watched;
  const offers = Object.fromEntries(
    AUTOFILL_FIELDS.map((field) => [
      field,
      reading.status === "ready" ? offerFor(field, reading.fields, reading.revision, decisions[field], values[field]) : null,
    ]),
  ) as Record<AutofillField, FieldOffer>;
  const prefillNotes = prefillFieldNotes(reading, (field) => {
    const offer = offers[field];
    if (offer == null) return null;
    const name = FIELD_NAMES[field];
    if (offer.kind === "filled") return <AutofilledNote field={name} page={offer.page} entry={offer.entry} onUndo={() => undoAutofill(field)} />;
    if (offer.kind === "stale") return <AutofilledNote field={name} page={null} stale />;
    return (
      <PrefillChip
        field={name}
        suggestion={Array.isArray(offer.value) ? offer.value.join(", ") : String(offer.value)}
        replaces={offer.replaces}
        page={offer.entry.page}
        tooLong={offer.entry.exceeds_limit}
        entry={offer.entry}
        onUse={() => acceptSuggestion(field, offer.value)}
        onDismiss={() => dismissSuggestion(field)}
      />
    );
  });
  const adviser = lists.advisers.find((a) => a.id === values.adviser);
  const adviserName = adviser ? personName(adviser) : null;
  const typeName = lists.recordTypes.find((t) => t.id === typeId)?.name ?? "";

  const summary = {
    keywords: values.keywords,
    ownerEmails: values.owner_emails,
    typeName,
    fileName: acceptedUpload?.fileName ?? null,
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
          {draftId == null ? " " : step === 2 ? SAVE_STATUS[autosave.status] : "Saved as a draft. You can close this and finish later."}
          {step === 2 && autosave.status === "failed" && (
            <button type="button" onClick={() => void autosave.saveNow()} className={cn("ml-2 rounded-full font-medium text-stone-800 underline underline-offset-2", FOCUS_RING)}>
              Try again
            </button>
          )}
        </p>
        <div className="ml-auto flex gap-2">
          {step > 1 && (
            <button
              type="button"
              onClick={() => goTo((step - 1) as PublishStep)}
              disabled={saving || submitting || upload.status === "uploading"}
              className={cn(PILL_SECONDARY, FOCUS_RING)}
            >
              Back
            </button>
          )}
          {step === 1 && (
            <button
              type="button"
              onClick={() => void continueFromManuscript()}
              disabled={acceptedUpload == null || typeId == null || saving}
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
              disabled={submitting}
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
      size={phase.kind === "form" && step === 2 ? "max-w-[1180px]" : "max-w-[720px]"}
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
          <IrisLoader className="h-5 w-5 text-brand" /> Getting things ready…
        </p>
      )}

      {phase.kind === "loadError" && (
        <Notice
          message={phase.message}
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
              recordTypes={isContinuation ? lists.recordTypes.filter((type) => !isProposal(type.name)) : lists.recordTypes}
              typeId={typeId}
              onTypeChange={setTypeId}
              upload={upload}
              onFile={handleFile}
              onRetry={() => void startUpload()}
              exactMatches={exactMatches}
            />
          )}

          {step === 2 && draftId != null && (
            <PublishDetailsPreview recordId={draftId} sourceKey={uploadGeneration}>
              <FormProvider {...form}>
                {autosave.status === "conflict" && (
                  <div role="alert" className={cn(LOAD_ERROR, "mb-section flex-wrap")}>
                    <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
                    <span className="flex-1">{STALE_DRAFT}</span>
                    <button type="button" onClick={reloadDraft} className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-4")}>
                      Reload draft
                    </button>
                  </div>
                )}
                {/* One announcement for the prefill, where the visible lines sit
                    under several fields and would be read more than once. */}
                <span role="status" className="sr-only">
                  {prefillAnnouncement(reading, offers)}
                </span>
                <PrefillLine reading={reading} retrying={retryingRead} onRetry={() => void retryReading()} />
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
                    loadErrorMessage={listError}
                    moreOpen={moreOpen}
                    onMoreOpenChange={setMoreOpen}
                    fieldNotes={prefillNotes}
                  />
                </form>
              </FormProvider>
            </PublishDetailsPreview>
          )}

          {step === 3 && (
            <ReviewStep
              summary={summary}
              failure={submitFailure}
              exactMatches={exactMatches}
              likelyMatches={likelyMatches}
              matchesAcknowledged={matchesAcknowledged}
              matchFailure={matchFailure}
              onAcknowledge={() => void acknowledgeMatches()}
              onCheckAgain={() => {
                if (draftId != null) void refreshMatches(draftId).catch(() => setMatchFailure("Matches could not be checked. Try again before submitting."));
              }}
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

/** Continue saves these, autosave does not: an owner list typed half-way is not one. */
const UNSAVED_UNTIL_CONTINUE = new Set(["owner_emails"]);

/** Everything Details saves: its values, and the author's decision about each prefilled field. */
function completeBody(
  values: MetadataValues,
  decisions: MetadataSources,
  unloaded: { classification?: boolean; psced?: boolean },
): Partial<RecordFormData> {
  return { ...metadataPayload(values, unloaded), metadata_sources: decisions };
}

/** Said in the footer while Details is shown. Not announced: a conflict has its own alert. */
const SAVE_STATUS: Record<SaveStatus, string> = {
  idle: "Saved as a draft. You can close this and finish later.",
  saving: "Saving…",
  saved: "All changes saved.",
  unsaved: "Some changes aren't saved yet. Continue saves them.",
  failed: "Your latest changes couldn't be saved.",
  conflict: "Your latest changes weren't saved.",
};

/** What reading the PDF is doing, as the line under each field says it. */
function readingText(reading: Prefill): string {
  if (reading.phase === "queued") return "Waiting to read your PDF…";
  if (reading.phase === "retrying") return "Reading your PDF didn't work the first time. Trying again…";
  return "Reading your PDF…";
}

/**
 * What sits under each prefillable field: a still line while the PDF is read
 * (the fields stay editable), then each field's note or chip, if it has one.
 */
function prefillFieldNotes(
  reading: Prefill,
  noteFor: (field: AutofillField) => ReactNode,
): Partial<Record<AutofillField, ReactNode>> {
  if (reading.status === "pending") {
    // A still icon: this can sit on screen for minutes, and a spinner that
    // long is motion the reduced-motion rule (spec §7) forbids.
    const line = (
      <p className="mt-1 flex items-center gap-1.5 text-small text-stone-600" aria-hidden>
        <i className="fas fa-file-lines text-label" aria-hidden />
        {readingText(reading)}
      </p>
    );
    return { title: line, abstract: line };
  }
  if (reading.status !== "ready") return {};
  return Object.fromEntries(AUTOFILL_FIELDS.map((f) => [f, noteFor(f)]).filter(([, note]) => note != null));
}

/** The line above Details when reading has stopped, or found nothing. */
function PrefillLine({ reading, retrying, onRetry }: { reading: Prefill; retrying: boolean; onRetry: () => void }) {
  const action = (label: string, onClick: () => void, disabled = false) => (
    <button type="button" onClick={onClick} disabled={disabled} className={cn(PILL_SECONDARY, FOCUS_RING, "ml-2 min-h-9 px-4")}>
      {label}
    </button>
  );
  if (reading.status === "stalled") {
    return (
      <p className="mb-section-sm flex flex-wrap items-center gap-y-2 text-small text-stone-600">
        Still processing your PDF. Keep filling in details, and check again for suggestions.
        {action("Check again", reading.checkAgain)}
      </p>
    );
  }
  if (reading.status === "failed" || reading.status === "unsupported") {
    return (
      <p className="mb-section-sm flex flex-wrap items-center gap-y-2 text-small text-stone-600">
        {NEUTRAL_PREFILL}
        {reading.status === "failed" && reading.retryable && action("Retry extraction", onRetry, retrying)}
      </p>
    );
  }
  if (reading.status === "ready" && AUTOFILL_FIELDS.every((field) => reading.fields[field] == null)) {
    return <p className="mb-section-sm text-small text-stone-600">{NOTHING_FOUND}</p>;
  }
  return null;
}

/** What the prefill's live region says; the notes themselves carry the detail. */
function prefillAnnouncement(reading: Prefill, offers: Record<AutofillField, FieldOffer>): string {
  // The neutral line is not repeated here: it is ordinary text above the form,
  // read in order, and a failure to prefill needs no interruption.
  if (reading.status === "pending") return readingText(reading);
  if (reading.status === "stalled") return "Still processing your PDF.";
  const names = (kind: string) => AUTOFILL_FIELDS.filter((f) => offers[f]?.kind === kind).map((f) => FIELD_NAMES[f]);
  const list = (items: string[]) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}` : items[0]);
  const filled = names("filled");
  const offered = names("offer");
  return [
    filled.length > 0 && `Filled in the ${list(filled)} from your PDF. You can undo this under each field.`,
    offered.length > 0 && `Suggestions for the ${list(offered)} are shown under each field.`,
  ].filter(Boolean).join(" ");
}

/** Where the author is: done steps say so in words, the current one is marked. */
function StepIndicator({ current }: { current: Exclude<PublishStep, 0> }) {
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
    <div role="alert" className="flex flex-col items-start gap-section py-section">
      <p className="text-body text-stone-800">{message}</p>
      {action}
    </div>
  );
}
