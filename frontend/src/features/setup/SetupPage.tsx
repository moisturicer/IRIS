/**
 * RDCO's Setup page, Requirements & Templates (ADR-063 decisions 1-12, IR-971).
 *
 * One tab per record type: its description, then its requirements in order.
 * The Manuscript is a fixed first row: its description and Template can be
 * edited, but it can't be removed or made Optional. RDCO adds, edits, reorders
 * and removes the rest. A requirement's label is Required or Optional and never
 * blocks submitting. Removing one a paper has used hides it and keeps its
 * files; an unused one is deleted. A Template is a PDF, Word, spreadsheet or
 * image file up to 50 MB, and always downloads.
 *
 * Every change is saved at once and audited by the server. The Notice joins
 * this page later (ADR-063 decision 9); `/notices` still holds it.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  setupApi, TEMPLATE_ACCEPT, type RequirementFields, type SetupRecordType, type SetupRequirement,
} from "@/api/setup";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { PlainTextWithLinks } from "@/components/shared/PlainTextWithLinks";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { fieldClasses, LABEL, WARNING_NOTICE } from "@/components/ui/fieldClasses";
import { Spinner } from "@/components/ui/Spinner";
import { useApiRead } from "@/hooks/useApiRead";
import { errorDetail } from "@/lib/errorDetail";
import { downloadBlob } from "@/lib/utils";

const MAX_TEMPLATE_BYTES = 50 * 1024 * 1024;
const MAX_DESCRIPTION = 2000;

/** Only a list of record types is usable; anything else is a failed read (CODING_STANDARDS F1). */
function isRecordTypeList(data: unknown): data is SetupRecordType[] {
  return Array.isArray(data) && data.every(
    (rt) => rt && typeof rt.id === "number" && typeof rt.name === "string" && Array.isArray(rt.requirements),
  );
}

/** What the page says after a change: an outcome, or why it didn't happen. */
type Outcome = { kind: "done" | "failed"; text: string } | null;

export default function SetupPage() {
  const read = useApiRead((signal) => setupApi.recordTypes({ signal }).then((r) => r.data), []);
  const [types, setTypes] = useState<SetupRecordType[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const tabsId = useId();

  useEffect(() => {
    const data = read.data;
    if (read.status !== "ready" || !isRecordTypeList(data)) return;
    setTypes(data);
    setSelected((current) => current ?? data[0]?.id ?? null);
  }, [read.status, read.data]);

  /** Re-read after a change, keeping the page on screen meanwhile. */
  const refresh = async () => {
    try {
      const { data } = await setupApi.recordTypes();
      if (isRecordTypeList(data)) setTypes(data);
    } catch {
      setOutcome({ kind: "failed", text: "Your change was saved, but the list didn't reload. Refresh the page." });
    }
  };

  const act = async (work: () => Promise<unknown>, done: string, fallback: string): Promise<boolean> => {
    setOutcome(null);
    try {
      await work();
      await refresh();
      setOutcome({ kind: "done", text: done });
      return true;
    } catch (err) {
      setOutcome({ kind: "failed", text: errorDetail(err, fallback) });
      return false;
    }
  };

  const current = types?.find((rt) => rt.id === selected) ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Setup"
        description="What each record type asks for, the forms people download, and how each type is described. Changes show at once wherever requirements show."
      />

      {read.status === "interrupted" && !types ? (
        <InterruptedState what="setup" onRetry={read.retry} framed />
      ) : !types ? (
        read.status === "ready" ? (
          <div className="space-y-3 rounded-xl border border-stone-200 bg-white p-5">
            <p role="alert" className="text-small text-stone-700">Setup didn&apos;t load. Check your connection, then try again.</p>
            <Button type="button" variant="outline" onClick={read.retry}>Try again</Button>
          </div>
        ) : (
          <p role="status" className="flex items-center gap-2 text-small text-stone-600">
            <Spinner size="sm" />
            Loading setup…
          </p>
        )
      ) : (
        <>
          <div role="tablist" aria-label="Record types" className="flex flex-wrap gap-2">
            {types.map((rt) => (
              <button
                key={rt.id}
                type="button"
                role="tab"
                id={`${tabsId}-tab-${rt.id}`}
                aria-selected={rt.id === selected}
                aria-controls={`${tabsId}-panel`}
                onClick={() => { setSelected(rt.id); setOutcome(null); }}
                className={`rounded-full border px-4 py-1.5 text-small font-medium transition-colors ${
                  rt.id === selected
                    ? "border-brand bg-brand text-white"
                    : "border-stone-300 bg-white text-stone-700 hover:border-brand hover:text-brand"
                }`}
              >
                {rt.name}
              </button>
            ))}
          </div>

          <div aria-live="polite">
            {outcome && (
              outcome.kind === "done"
                ? <p role="status" className="text-small text-stone-700">{outcome.text}</p>
                : <p role="alert" className={WARNING_NOTICE}>{outcome.text}</p>
            )}
          </div>

          {current && (
            <div
              role="tabpanel"
              id={`${tabsId}-panel`}
              aria-labelledby={`${tabsId}-tab-${current.id}`}
              className="space-y-4"
            >
              <TypeDescription key={`d-${current.id}`} recordType={current} act={act} />
              <Requirements key={`r-${current.id}`} recordType={current} act={act} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

type Act = (work: () => Promise<unknown>, done: string, fallback: string) => Promise<boolean>;

/* -------------------------------------------------------------------------- */
/* The record type's description                                              */
/* -------------------------------------------------------------------------- */

function TypeDescription({ recordType, act }: { recordType: SetupRecordType; act: Act }) {
  const fieldId = useId();
  const [text, setText] = useState(recordType.description);
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    await act(
      () => setupApi.describe(recordType.id, { description: text }),
      `${recordType.name}'s description is saved.`,
      "The description wasn't saved. Try again.",
    );
    setSaving(false);
  };

  return (
    <section aria-labelledby={`${fieldId}-title`} className="rounded-xl border border-stone-200 bg-white p-5">
      <h2 id={`${fieldId}-title`} className="text-heading font-semibold text-stone-900">Description</h2>
      <form onSubmit={(e) => void save(e)} className="mt-3 space-y-3">
        <div>
          <label htmlFor={fieldId} className={LABEL}>What a {recordType.name} is</label>
          <p className="mb-2 text-label text-stone-600">
            Shown at the top of this type&apos;s Guidelines. Plain text: line breaks are kept and web links become clickable.
          </p>
          <textarea
            id={fieldId}
            value={text}
            maxLength={MAX_DESCRIPTION}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            className={fieldClasses(false)}
          />
        </div>
        <Button type="submit" variant="outline" loading={saving} disabled={text === recordType.description}>
          Save description
        </Button>
      </form>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Requirements & Templates                                                   */
/* -------------------------------------------------------------------------- */

function Requirements({ recordType, act }: { recordType: SetupRecordType; act: Act }) {
  const titleId = useId();
  const [removing, setRemoving] = useState<SetupRequirement | null>(null);
  const [busy, setBusy] = useState(false);
  const list = recordType.requirements;

  const move = (index: number, by: -1 | 1) => {
    const order = list.map((r) => r.id);
    const [moved] = order.splice(index, 1);
    order.splice(index + by, 0, moved);
    void act(
      () => setupApi.reorder(recordType.id, order),
      `${list[index].name} moved ${by < 0 ? "up" : "down"}.`,
      "The order wasn't saved. Try again.",
    );
  };

  const remove = async () => {
    if (!removing) return;
    setBusy(true);
    const target = removing;
    await act(
      () => setupApi.removeRequirement(target.id),
      target.in_use
        ? `${target.name} is hidden. Papers that have files in it keep them.`
        : `${target.name} is removed.`,
      `${target.name} wasn't removed. Try again.`,
    );
    setBusy(false);
    setRemoving(null);
  };

  return (
    <section aria-labelledby={titleId} className="rounded-xl border border-stone-200 bg-white p-5">
      <h2 id={titleId} className="text-heading font-semibold text-stone-900">Requirements &amp; Templates</h2>
      <p className="mt-1 text-small text-stone-600">
        Required and Optional are labels. They tell people what RDCO expects and never stop anyone submitting.
      </p>

      <ol aria-label={`${recordType.name} requirements`} className="mt-4 divide-y divide-stone-100">
        <li className="py-4">
          <ManuscriptRow recordType={recordType} act={act} />
        </li>
        {list.map((requirement, index) => (
          <li key={requirement.id} className="py-4">
            <RequirementRow
              requirement={requirement}
              recordType={recordType}
              act={act}
              onMoveUp={index > 0 ? () => move(index, -1) : undefined}
              onMoveDown={index < list.length - 1 ? () => move(index, 1) : undefined}
              onRemove={() => setRemoving(requirement)}
            />
          </li>
        ))}
      </ol>

      <AddRequirement recordType={recordType} act={act} />

      <ConfirmDialog
        open={removing !== null}
        title={removing ? `Remove ${removing.name}?` : ""}
        message={
          removing?.in_use
            ? "Papers already have files in it, so it will be hidden: it leaves this list, Publish, Guidelines and new document requests, and the files stay on their papers."
            : "Nobody has used it yet, so it will be deleted."
        }
        confirmLabel="Remove"
        danger
        confirming={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </section>
  );
}

function Label({ required }: { required: boolean }) {
  return <Badge variant={required ? "warning" : "neutral"}>{required ? "Required" : "Optional"}</Badge>;
}

function ManuscriptRow({ recordType, act }: { recordType: SetupRecordType; act: Act }) {
  const [editing, setEditing] = useState(false);
  const { description, template_name } = recordType.manuscript;

  return (
    <div role="group" aria-label="Manuscript" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-small font-semibold text-stone-900">Manuscript</h3>
        <Label required />
      </div>
      <p className="text-label text-stone-600">Always first. It can&apos;t be removed or made Optional.</p>
      {editing ? (
        <DescriptionOnlyForm
          initial={description}
          label="Manuscript description"
          onCancel={() => setEditing(false)}
          onSave={async (text) => {
            const ok = await act(
              () => setupApi.describe(recordType.id, { manuscript_description: text }),
              "The Manuscript's description is saved.",
              "The description wasn't saved. Try again.",
            );
            if (ok) setEditing(false);
          }}
        />
      ) : (
        <>
          {description && <PlainTextWithLinks text={description} className="text-small text-stone-700" />}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
              Edit description
            </Button>
          </div>
        </>
      )}
      <TemplateControls
        owner="the Manuscript"
        templateName={template_name}
        act={act}
        upload={(file) => setupApi.setManuscriptTemplate(recordType.id, file)}
        remove={() => setupApi.removeManuscriptTemplate(recordType.id)}
        download={() => setupApi.downloadManuscriptTemplate(recordType.id)}
      />
    </div>
  );
}

function RequirementRow({
  requirement, recordType, act, onMoveUp, onMoveDown, onRemove,
}: {
  requirement: SetupRequirement;
  recordType: SetupRecordType;
  act: Act;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <RequirementForm
        title={`Edit ${requirement.name}`}
        initial={requirement}
        submitLabel="Save"
        onCancel={() => setEditing(false)}
        onSubmit={async (fields) => {
          const ok = await act(
            () => setupApi.editRequirement(requirement.id, fields),
            `${fields.name} is saved.`,
            `${requirement.name} wasn't saved. Try again.`,
          );
          if (ok) setEditing(false);
          return ok;
        }}
        siblings={recordType.requirements.filter((r) => r.id !== requirement.id)}
      />
    );
  }

  return (
    <div role="group" aria-label={requirement.name} className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-small font-semibold text-stone-900">{requirement.name}</h3>
        <Label required={requirement.is_required} />
      </div>
      {requirement.description && (
        <PlainTextWithLinks text={requirement.description} className="text-small text-stone-700" />
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
          Edit
        </Button>
        <Button
          type="button" variant="ghost" size="sm" disabled={!onMoveUp} onClick={onMoveUp}
          aria-label={`Move up ${requirement.name}`}
        >
          Move up
        </Button>
        <Button
          type="button" variant="ghost" size="sm" disabled={!onMoveDown} onClick={onMoveDown}
          aria-label={`Move down ${requirement.name}`}
        >
          Move down
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onRemove} aria-label={`Remove ${requirement.name}`}>
          Remove
        </Button>
      </div>
      <TemplateControls
        owner={requirement.name}
        templateName={requirement.template_name}
        act={act}
        upload={(file) => setupApi.setTemplate(requirement.id, file)}
        remove={() => setupApi.removeTemplate(requirement.id)}
        download={() => setupApi.downloadTemplate(requirement.id)}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Templates                                                                  */
/* -------------------------------------------------------------------------- */

function TemplateControls({
  owner, templateName, act, upload, remove, download,
}: {
  owner: string;
  templateName: string;
  act: Act;
  upload: (file: File) => Promise<unknown>;
  remove: () => Promise<unknown>;
  download: () => Promise<{ data: Blob }>;
}) {
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const choose = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    setProblem(null);
    if (file.size > MAX_TEMPLATE_BYTES) {
      setProblem(`${file.name} is over the 50 MB limit.`);
      return;
    }
    setWorking(true);
    await act(
      () => upload(file),
      `${file.name} is now the Template for ${owner}.`,
      "The Template wasn't uploaded. Try again.",
    );
    setWorking(false);
  };

  const save = async () => {
    setProblem(null);
    try {
      const { data } = await download();
      downloadBlob(data, templateName);
    } catch (err) {
      setProblem(errorDetail(err, "The Template didn't download. Try again."));
    }
  };

  return (
    <div className="rounded-lg bg-stone-50 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-small text-stone-700">
        <i className="fas fa-file-arrow-down text-stone-500" aria-hidden />
        {templateName ? (
          <button
            type="button"
            onClick={() => void save()}
            className="font-medium text-brand underline underline-offset-2"
            aria-label={`Download the Template for ${owner}, ${templateName}`}
          >
            {templateName}
          </button>
        ) : (
          <span className="text-stone-600">No Template</span>
        )}
        <span className="flex-1" />
        <input
          ref={input}
          id={inputId}
          type="file"
          accept={TEMPLATE_ACCEPT}
          className="sr-only"
          tabIndex={-1}
          aria-label={`Template file for ${owner}`}
          onChange={(e) => void choose(e.target.files?.[0])}
        />
        <Button
          type="button" variant="outline" size="sm" loading={working}
          onClick={() => input.current?.click()}
          aria-label={templateName ? `Replace the Template for ${owner}` : `Upload Template for ${owner}`}
        >
          {templateName ? "Replace" : "Upload Template"}
        </Button>
        {templateName && (
          <Button
            type="button" variant="ghost" size="sm"
            aria-label={`Remove the Template for ${owner}`}
            onClick={() => void act(remove, `The Template for ${owner} is removed.`,
                                    "The Template wasn't removed. Try again.")}
          >
            Remove
          </Button>
        )}
      </div>
      <p className="mt-1 text-label text-stone-600">PDF, Word, spreadsheet or image, up to 50 MB. People download it.</p>
      {problem && <p role="alert" className="mt-1 text-small text-brand">{problem}</p>}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Forms                                                                      */
/* -------------------------------------------------------------------------- */

function AddRequirement({ recordType, act }: { recordType: SetupRecordType; act: Act }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="mt-4">
        <Button type="button" variant="outline" onClick={() => setOpen(true)}>
          <i className="fas fa-plus mr-2" aria-hidden />
          Add a requirement
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-lg border border-stone-200 p-4">
      <RequirementForm
        title={`Add a requirement to ${recordType.name}`}
        initial={{ name: "", is_required: false, description: "" }}
        submitLabel="Add requirement"
        onCancel={() => setOpen(false)}
        siblings={recordType.requirements}
        onSubmit={async (fields) => {
          const ok = await act(
            () => setupApi.addRequirement(recordType.id, fields),
            `${fields.name} is added to ${recordType.name}.`,
            "The requirement wasn't added. Try again.",
          );
          if (ok) setOpen(false);
          return ok;
        }}
      />
    </div>
  );
}

function RequirementForm({
  title, initial, submitLabel, onSubmit, onCancel, siblings,
}: {
  title: string;
  initial: RequirementFields;
  submitLabel: string;
  onSubmit: (fields: RequirementFields) => Promise<boolean>;
  onCancel: () => void;
  siblings: SetupRequirement[];
}) {
  const id = useId();
  const [name, setName] = useState(initial.name);
  const [required, setRequired] = useState(initial.is_required);
  const [description, setDescription] = useState(initial.description);
  const [nameError, setNameError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const clean = name.trim();
    if (!clean) return setNameError("Give the requirement a name.");
    if (clean.toLowerCase() === "manuscript") return setNameError("The Manuscript is always the first requirement.");
    if (siblings.some((s) => s.name.toLowerCase() === clean.toLowerCase())) {
      return setNameError("This record type already has a requirement with that name.");
    }
    setNameError(null);
    setSaving(true);
    await onSubmit({ name: clean, is_required: required, description });
    setSaving(false);
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby={`${id}-title`} className="space-y-3">
      <h3 id={`${id}-title`} className="text-small font-semibold text-stone-900">{title}</h3>
      <div>
        <label htmlFor={`${id}-name`} className={LABEL}>Name</label>
        <input
          id={`${id}-name`}
          value={name}
          maxLength={200}
          onChange={(e) => { setName(e.target.value); setNameError(null); }}
          aria-invalid={nameError ? true : undefined}
          aria-describedby={nameError ? `${id}-name-error` : undefined}
          className={fieldClasses(Boolean(nameError))}
        />
        {nameError && <p id={`${id}-name-error`} className="mt-1.5 text-small text-brand">{nameError}</p>}
      </div>
      <fieldset>
        <legend className={LABEL}>Label</legend>
        <div className="flex flex-wrap gap-4 text-small text-stone-800">
          <label className="flex items-center gap-2">
            <input type="radio" name={`${id}-label`} checked={required} onChange={() => setRequired(true)}
                   className="accent-brand" />
            Required
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name={`${id}-label`} checked={!required} onChange={() => setRequired(false)}
                   className="accent-brand" />
            Optional
          </label>
        </div>
      </fieldset>
      <div>
        <label htmlFor={`${id}-description`} className={LABEL}>Description</label>
        <p className="mb-2 text-label text-stone-600">Plain text: line breaks are kept and web links become clickable.</p>
        <textarea
          id={`${id}-description`}
          value={description}
          maxLength={MAX_DESCRIPTION}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className={fieldClasses(false)}
        />
      </div>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={saving}>{submitLabel}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function DescriptionOnlyForm({
  initial, label, onSave, onCancel,
}: {
  initial: string;
  label: string;
  onSave: (text: string) => Promise<void>;
  onCancel: () => void;
}) {
  const id = useId();
  const [text, setText] = useState(initial);
  const [saving, setSaving] = useState(false);

  return (
    <form
      onSubmit={async (e) => { e.preventDefault(); setSaving(true); await onSave(text); setSaving(false); }}
      className="space-y-2"
    >
      <label htmlFor={id} className={LABEL}>{label}</label>
      <textarea
        id={id}
        value={text}
        maxLength={MAX_DESCRIPTION}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        className={fieldClasses(false)}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="sm" loading={saving}>Save</Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
