/**
 * Edit details (IR-411; spec §4.6): a record's metadata, edited in a dialog
 * over Paper View. It replaces the Edit Record page and its three-step wizard.
 *
 * The fields are `MetadataForm`'s, the rules `metadataSchema`'s and the PATCH
 * body `metadataPayload`'s, all shared with Publish (IR-408), so the two
 * places a record's details are edited cannot drift apart.
 *
 * The page offers this only under the `edit_details` capability: the owner's
 * draft, or the owner's record awaiting a revision, where the change goes back
 * to the reviewers with the resubmission (invariant 4). The server re-checks.
 * Once submitted, the Adviser and the hints are fixed (IR-507): the form shows
 * them read-only and the PATCH leaves them out.
 */
import { useEffect, useMemo, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";
import type { Classification, PSCEDClassification, RecordDetail } from "@/types/records";

import { describeFailure, stateFromDraft, type ApiFailure } from "@/features/publish/draft";
import { FORM_FIELD, MetadataForm, focusFirstInvalid } from "@/features/records/metadata/MetadataForm";
import { metadataPayload, metadataSchema, type MetadataValues } from "@/features/records/metadata/metadataSchema";

interface Lists {
  advisers:        User[];
  classifications: Classification[];
  psceds:          PSCEDClassification[];
}

interface EditDetailsDialogProps {
  record:  RecordDetail;
  /** Who is signed in: shown in the adviser list, never choosable. */
  selfId:  number | null;
  onClose: () => void;
  /** The record as the server now holds it, so the page shows the change at once. */
  onSaved: (record: RecordDetail) => void;
}

export function EditDetailsDialog({ record, selfId, onClose, onSaved }: EditDetailsDialogProps) {
  const schema = useMemo(() => metadataSchema(selfId), [selfId]);
  const form = useForm<MetadataValues>({
    resolver: zodResolver(schema),
    defaultValues: stateFromDraft(record, { recordTypes: [], classifications: [], psceds: [] }).values,
    mode: "onTouched",
    shouldFocusError: false,
  });

  const [lists, setLists] = useState<Lists | null>(null);
  const [failed, setFailed] = useState({ advisers: false, classification: false, psced: false });
  const [moreOpen, setMoreOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  // Past draft, the Adviser and the hints are fixed (IR-507): shown, not sent.
  const submitted = record.pipeline_status !== "draft";

  // The lists name the record's classification and PSCED, which the detail
  // payload gives by name; the form needs their ids, so it is reset once
  // they arrive.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [advisers, classifications, psceds] = await Promise.allSettled([
        accountsApi.listAdvisers(),
        recordsApi.classifications(),
        recordsApi.pscedList(),
      ]);
      if (cancelled) return;
      const loaded: Lists = {
        advisers: advisers.status === "fulfilled" ? advisers.value.data.results ?? [] : [],
        classifications: classifications.status === "fulfilled" ? classifications.value.data.results ?? [] : [],
        psceds: psceds.status === "fulfilled" ? psceds.value.data.results ?? [] : [],
      };
      setFailed({
        advisers: advisers.status === "rejected",
        classification: classifications.status === "rejected",
        psced: psceds.status === "rejected",
      });
      form.reset(stateFromDraft(record, { recordTypes: [], ...loaded }).values);
      setLists(loaded);
    })();
    return () => {
      cancelled = true;
    };
    // The record is the one the dialog opened on; a re-render must not
    // discard what has been typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save(values: MetadataValues) {
    setSaving(true);
    setFailure(null);
    try {
      await recordsApi.update(record.id, metadataPayload(values, failed, { submitted }));
      const { data } = await recordsApi.detail(record.id);
      onSaved(data);
    } catch (err) {
      const refused = describeFailure(err, "We couldn't save these details. Try again.");
      for (const [field, message] of Object.entries(refused.fields)) {
        const name = FORM_FIELD[field];
        if (name) form.setError(name, { type: "server", message });
      }
      setFailure(refused);
    } finally {
      setSaving(false);
    }
  }

  const onSubmit = form.handleSubmit(save, (errors) => focusFirstInvalid(errors, () => setMoreOpen(true)));
  const revising = record.workflow_state === "awaiting_resubmission";

  return (
    <Modal
      open
      onClose={onClose}
      title="Edit details"
      displayTitle
      sheet
      size="max-w-2xl"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button type="button" onClick={onClose} className={cn(PILL_SECONDARY, FOCUS_RING)}>
            Cancel
          </button>
          {/* In the pinned footer, outside the form, so it submits by hand. */}
          <button
            type="button"
            onClick={() => void onSubmit()}
            disabled={saving || lists == null}
            className={cn(PILL_PRIMARY, FOCUS_RING)}
          >
            {saving ? "Saving…" : "Save details"}
          </button>
        </div>
      }
    >
      {lists == null ? (
        <Skeleton rows={6} label="Loading the details…" />
      ) : (
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-section-sm">
        {revising && (
          <p className="text-small text-stone-700">
            A revision was requested. Changes here are saved straight away, and the reviewers see them when you
            resubmit.
          </p>
        )}
        {failure && failure.message && Object.keys(failure.fields).length === 0 && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
            {failure.message}
          </p>
        )}
        <FormProvider {...form}>
          <MetadataForm
            advisers={lists.advisers}
            classifications={lists.classifications}
            psceds={lists.psceds}
            selfId={selfId}
            loadError={failed.advisers || failed.classification || failed.psced}
            moreOpen={moreOpen}
            onMoreOpenChange={setMoreOpen}
            submitted={submitted}
          />
        </FormProvider>
      </form>
      )}
    </Modal>
  );
}
