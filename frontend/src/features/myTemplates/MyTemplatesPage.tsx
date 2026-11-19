/**
 * My Templates (ADR-063 decision 8, IR-975): the proposal Templates an Adviser
 * shares, in any number and in the Adviser's order. Each has a title, a short
 * plain-text description (line breaks kept, links clickable) and a file: PDF,
 * Word, spreadsheet or image, up to 50 MB, which people always download.
 *
 * The list is the Adviser's own: nobody else, RDCO included, can change or
 * remove one. Everyone signed in can see them while the Adviser is an active
 * Adviser. Every change is saved at once and audited by the server.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { myTemplatesApi, type MyTemplate, type TemplateFields } from "@/api/myTemplates";
import { TEMPLATE_ACCEPT } from "@/api/setup";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { PlainTextWithLinks } from "@/components/shared/PlainTextWithLinks";
import { Button } from "@/components/ui/Button";
import { fieldClasses, LABEL, WARNING_NOTICE } from "@/components/ui/fieldClasses";
import { Spinner } from "@/components/ui/Spinner";
import { useApiRead } from "@/hooks/useApiRead";
import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";
import { downloadBlob } from "@/lib/utils";

const MAX_TEMPLATE_BYTES = 50 * 1024 * 1024;
const MAX_TITLE = 200;
const MAX_DESCRIPTION = 2000;
const FILE_RULES = "PDF, Word, spreadsheet or image, up to 50 MB. People download it.";

/** Only a list of Templates is usable; anything else is a failed read (CODING_STANDARDS F1). */
function isTemplateList(data: unknown): data is MyTemplate[] {
  return Array.isArray(data) && data.every(
    (t) => t && typeof t.id === "number" && typeof t.title === "string" && typeof t.file_name === "string",
  );
}

type Outcome = { kind: "done" | "failed"; text: string } | null;
type Act = (work: () => Promise<unknown>, done: string, fallback: string) => Promise<boolean>;

/** Why a chosen file can't be sent, before sending it. */
function fileProblem(file: File | null): string | null {
  if (!file) return "Choose a file.";
  if (file.size > MAX_TEMPLATE_BYTES) return `${file.name} is over the 50 MB limit.`;
  return null;
}

export default function MyTemplatesPage() {
  const read = useApiRead((signal) => myTemplatesApi.list({ signal }).then((r) => r.data), []);
  const [templates, setTemplates] = useState<MyTemplate[] | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);

  useEffect(() => {
    if (read.status === "ready" && isTemplateList(read.data)) setTemplates(read.data);
  }, [read.status, read.data]);

  /** Re-read after a change, keeping the list on screen meanwhile. */
  const refresh = async () => {
    try {
      const { data } = await myTemplatesApi.list();
      if (isTemplateList(data)) setTemplates(data);
    } catch {
      setOutcome({ kind: "failed", text: "Your change was saved, but the list didn't reload. Refresh the page." });
    }
  };

  const act: Act = async (work, done, fallback) => {
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="My Templates"
        description="Proposal formats and forms you share. Everyone signed in can see and download them while you are an Adviser. Only you can change or remove them."
      />
      <div aria-live="polite">
        {outcome && (
          outcome.kind === "done"
            ? <p role="status" className="text-small text-stone-700">{outcome.text}</p>
            : <p role="alert" className={WARNING_NOTICE}>{outcome.text}</p>
        )}
      </div>
      {read.status === "interrupted" && !templates ? (
        <InterruptedState what="your Templates" onRetry={read.retry} framed />
      ) : read.status === "failed" && !templates ? (
        <LoadFailedAlert message={failureMessage(read.error, { lead: "Your Templates didn't load." })} onRetry={read.retry} />
      ) : !templates ? (
        read.status === "ready" ? (
          <div className="space-y-3 rounded-card border border-stone-200 bg-white p-5">
            <p role="alert" className="text-small text-stone-700">Your Templates didn&apos;t load: IRIS sent an answer this page can&apos;t read. Try again.</p>
            <Button type="button" variant="outline" onClick={read.retry}>Try again</Button>
          </div>
        ) : (
          <p role="status" className="flex items-center gap-2 text-small text-stone-600">
            <Spinner size="sm" />
            Loading your Templates…
          </p>
        )
      ) : (
        <TemplateList templates={templates} act={act} />
      )}
    </div>
  );
}

function TemplateList({ templates, act }: { templates: MyTemplate[]; act: Act }) {
  const titleId = useId();
  const [removing, setRemoving] = useState<MyTemplate | null>(null);
  const [busy, setBusy] = useState(false);
  /* One move at a time: a second built from the list before the first saved would send a stale order. */
  const [moving, setMoving] = useState(false);

  const move = async (index: number, by: -1 | 1) => {
    const order = templates.map((t) => t.id);
    const [moved] = order.splice(index, 1);
    order.splice(index + by, 0, moved);
    setMoving(true);
    await act(
      () => myTemplatesApi.reorder(order),
      `${templates[index].title} moved ${by < 0 ? "up" : "down"}.`,
      "The order wasn't saved. Try again.",
    );
    setMoving(false);
  };

  const remove = async () => {
    if (!removing) return;
    const target = removing;
    setBusy(true);
    await act(() => myTemplatesApi.remove(target.id), `${target.title} is removed.`,
              `${target.title} wasn't removed. Try again.`);
    setBusy(false);
    setRemoving(null);
  };

  return (
    <section aria-labelledby={titleId} className="rounded-card border border-stone-200 bg-white p-5">
      <h2 id={titleId} className="text-heading font-semibold text-stone-900">Your Templates</h2>
      {templates.length === 0 ? (
        <p className="mt-2 text-small text-stone-600">You haven&apos;t shared any Templates yet.</p>
      ) : (
        <ol aria-label="Your Templates" className="mt-2 divide-y divide-stone-100">
          {templates.map((template, index) => (
            <li key={template.id} className="py-4">
              <TemplateRow
                template={template}
                act={act}
                onMoveUp={index > 0 && !moving ? () => void move(index, -1) : undefined}
                onMoveDown={index < templates.length - 1 && !moving ? () => void move(index, 1) : undefined}
                onRemove={() => setRemoving(template)}
              />
            </li>
          ))}
        </ol>
      )}

      <AddTemplate act={act} />

      <ConfirmDialog
        open={removing !== null}
        title={removing ? `Remove ${removing.title}?` : ""}
        message="It stops showing to everyone, and its file is deleted."
        confirmLabel="Remove"
        danger
        confirming={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </section>
  );
}

function TemplateRow({
  template, act, onMoveUp, onMoveDown, onRemove,
}: {
  template: MyTemplate;
  act: Act;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <TemplateForm
        title={`Edit ${template.title}`}
        initial={template}
        submitLabel="Save"
        onCancel={() => setEditing(false)}
        onSubmit={async (fields) => {
          const ok = await act(() => myTemplatesApi.edit(template.id, fields), `${fields.title} is saved.`,
                               `${template.title} wasn't saved. Try again.`);
          if (ok) setEditing(false);
        }}
      />
    );
  }

  return (
    <div role="group" aria-label={template.title} className="space-y-2">
      <h3 className="text-small font-semibold text-stone-900">{template.title}</h3>
      {template.description && (
        <PlainTextWithLinks text={template.description} className="text-small text-stone-700" />
      )}
      <FileControls template={template} act={act} />
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}
                aria-label={`Edit ${template.title}`}>
          Edit
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={!onMoveUp} onClick={onMoveUp}
                aria-label={`Move up ${template.title}`}>
          Move up
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={!onMoveDown} onClick={onMoveDown}
                aria-label={`Move down ${template.title}`}>
          Move down
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onRemove} aria-label={`Remove ${template.title}`}>
          Remove
        </Button>
      </div>
    </div>
  );
}

/** The current file, to download or replace. A Template always has one. */
function FileControls({ template, act }: { template: MyTemplate; act: Act }) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const choose = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    const why = fileProblem(file);
    setProblem(why);
    if (why) return;
    setWorking(true);
    await act(() => myTemplatesApi.replaceFile(template.id, file),
              `${file.name} is now the file for ${template.title}.`, "The file wasn't replaced. Try again.");
    setWorking(false);
  };

  const save = async () => {
    setProblem(null);
    try {
      const { data } = await myTemplatesApi.downloadOwn(template.id);
      downloadBlob(data, template.file_name);
    } catch (err) {
      setProblem(errorDetail(err, "The Template didn't download. Try again."));
    }
  };

  return (
    <div className="rounded-card bg-stone-50 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-small text-stone-700">
        <i className="fas fa-file-arrow-down text-stone-500" aria-hidden />
        <button
          type="button"
          onClick={() => void save()}
          className="font-medium text-brand underline underline-offset-2"
          aria-label={`Download ${template.title}, ${template.file_name}`}
        >
          {template.file_name}
        </button>
        <span className="flex-1" />
        <input
          ref={input}
          type="file"
          accept={TEMPLATE_ACCEPT}
          className="sr-only"
          tabIndex={-1}
          aria-label={`New file for ${template.title}`}
          onChange={(e) => void choose(e.target.files?.[0])}
        />
        <Button type="button" variant="outline" size="sm" loading={working}
                onClick={() => input.current?.click()} aria-label={`Replace the file for ${template.title}`}>
          Replace
        </Button>
      </div>
      <p className="mt-1 text-label text-stone-600">{FILE_RULES}</p>
      {problem && <p role="alert" className="mt-1 text-small text-brand">{problem}</p>}
    </div>
  );
}

function AddTemplate({ act }: { act: Act }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="mt-4">
        <Button type="button" variant="outline" onClick={() => setOpen(true)}>
          <i className="fas fa-plus mr-2" aria-hidden />
          Add a Template
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-card border border-stone-200 p-4">
      <TemplateForm
        title="Add a Template"
        initial={{ title: "", description: "" }}
        submitLabel="Add Template"
        withFile
        onCancel={() => setOpen(false)}
        onSubmit={async (fields, file) => {
          if (!file) return;
          const ok = await act(() => myTemplatesApi.add(fields, file), `${fields.title} is added.`,
                               "The Template wasn't added. Try again.");
          if (ok) setOpen(false);
        }}
      />
    </div>
  );
}

function TemplateForm({
  title, initial, submitLabel, withFile = false, onSubmit, onCancel,
}: {
  title: string;
  initial: TemplateFields;
  submitLabel: string;
  /** Adding asks for the file; editing replaces it from the row instead. */
  withFile?: boolean;
  onSubmit: (fields: TemplateFields, file: File | null) => Promise<void>;
  onCancel: () => void;
}) {
  const id = useId();
  const [name, setName] = useState(initial.title);
  const [description, setDescription] = useState(initial.description);
  const [file, setFile] = useState<File | null>(null);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const clean = name.trim();
    const noTitle = clean ? null : "Give the Template a title.";
    const badFile = withFile ? fileProblem(file) : null;
    setTitleError(noTitle);
    setFileError(badFile);
    if (noTitle || badFile) return;
    setSaving(true);
    await onSubmit({ title: clean, description }, file);
    setSaving(false);
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby={`${id}-title`} className="space-y-3">
      <h3 id={`${id}-title`} className="text-small font-semibold text-stone-900">{title}</h3>
      <div>
        <label htmlFor={`${id}-name`} className={LABEL}>Title</label>
        <input
          id={`${id}-name`}
          value={name}
          maxLength={MAX_TITLE}
          onChange={(e) => { setName(e.target.value); setTitleError(null); }}
          aria-invalid={titleError ? true : undefined}
          aria-describedby={titleError ? `${id}-name-error` : undefined}
          className={fieldClasses(Boolean(titleError))}
        />
        {titleError && <p id={`${id}-name-error`} className="mt-1.5 text-small text-brand">{titleError}</p>}
      </div>
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
      {withFile && (
        <div>
          <label htmlFor={`${id}-file`} className={LABEL}>File</label>
          <p className="mb-2 text-label text-stone-600">{FILE_RULES}</p>
          <input
            id={`${id}-file`}
            type="file"
            accept={TEMPLATE_ACCEPT}
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setFileError(null); }}
            aria-invalid={fileError ? true : undefined}
            aria-describedby={fileError ? `${id}-file-error` : undefined}
            className="block w-full text-small text-stone-700 file:mr-3 file:rounded-control file:border file:border-stone-300 file:bg-white file:px-3 file:py-1.5 file:text-small file:font-medium"
          />
          {fileError && <p id={`${id}-file-error`} className="mt-1.5 text-small text-brand">{fileError}</p>}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={saving}>{submitLabel}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
