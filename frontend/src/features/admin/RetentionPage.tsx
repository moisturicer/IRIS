/**
 * The System Admin's Retention page (ADR-051 §3 and §19, IR-795).
 *
 * Lists each kind of personal data the daily cleanup can erase, with its
 * period and when the cleanup last ran. A blank period erases nothing, and a
 * period is entered only once the data protection officer has approved it:
 * the page says both before anything else.
 *
 * Saving a period first asks the server how many items it would erase now.
 * If any would go, the count is shown and the System Admin confirms before
 * the period is saved. Saving blank, or a period that would erase nothing,
 * saves at once. A refused value shows against its field.
 *
 *   GET   /settings/<key>/
 *   GET   /settings/<key>/erasure-preview/?days=N
 *   PATCH /settings/<key>/                         {value}
 *   GET   /audit/?event_type=RETENTION_CLEANUP_RUN  the latest run and its counts
 */
import { useId, useState, type FormEvent } from "react";
import { accountsApi } from "@/api/accounts";
import { auditApi } from "@/api/audit";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LOAD_ERROR, WARNING_NOTICE } from "@/components/ui/fieldClasses";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { failureMessage } from "@/lib/readFailure";
import { useApiRead } from "@/hooks/useApiRead";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { formatDate } from "@/lib/utils";

const FAILED = "That did not go through. Please try again.";

/**
 * The kinds of data the cleanup erases, one per type registered in
 * `backend/apps/*\/retention.py`. A type added there needs its row here.
 */
export const RETENTION_TYPES = [
  {
    key: "download_notes",
    settingKey: "retention.download_notes_days",
    label: "Download request notes",
    /** What `n` erased items are, in words: the cleanup counts requests, not notes. */
    items: (n: number) => `the notes of ${n} download ${n === 1 ? "request" : "requests"}`,
    description:
      "A reader's note on a download request, and RDCO's decline or revocation note. " +
      "Only the text is erased: the request, its status, dates and people stay. " +
      "A pending request is never touched. Age counts from the last thing that happened to the request.",
  },
] as const;

type RetentionType = (typeof RETENTION_TYPES)[number];

interface LastRun {
  at: string;
  counts: Record<string, number>;
}

function periodText(value: string): string {
  const days = value.trim();
  if (!days) return "Not set. Nothing is erased.";
  return `${days} ${days === "1" ? "day" : "days"}`;
}

function lastRunText(type: RetentionType, run: LastRun | null): string {
  if (!run) return "The cleanup hasn't run yet.";
  const when = formatDate(run.at, "MMM d, yyyy, h:mm a");
  const erased = run.counts[type.key];
  if (erased === undefined) return `${when}. This kind of data wasn't part of that run.`;
  return erased === 0 ? `${when}. Nothing was erased.` : `${when}. Erased ${type.items(erased)}.`;
}

function RetentionItem({ type, saved, lastRun }: { type: RetentionType; saved: string; lastRun: LastRun | null }) {
  const headingId = useId();
  const inputId = useId();
  const [current, setCurrent] = useState(saved);
  const [value, setValue] = useState(saved);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fieldErr, setFieldErr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, setPending] = useState<{ days: string; count: number } | null>(null);

  const changed = value.trim() !== current.trim();

  const refused = (err: unknown) => {
    const onField = fieldError(err, "days", "value");
    if (onField) setFieldErr(onField);
    else setError(errorDetail(err, FAILED));
  };

  const save = async (days: string) => {
    setSaving(true);
    setError(null);
    try {
      const { data } = await accountsApi.updateSetting(type.settingKey, days);
      setCurrent(data.value);
      setValue(data.value);
      setPending(null);
      setDone(data.value.trim() ? `Saved. The period is now ${periodText(data.value)}.` : "Saved. Nothing of this kind is erased.");
    } catch (err) {
      setPending(null);
      refused(err);
    } finally {
      setSaving(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!changed || checking || saving) return;
    setFieldErr(null);
    setError(null);
    setDone(null);
    const days = value.trim();
    if (!days) {
      await save("");
      return;
    }
    setChecking(true);
    try {
      const { data } = await accountsApi.retentionPreview(type.settingKey, days);
      if (data.count > 0) setPending({ days, count: data.count });
      else await save(days);
    } catch (err) {
      refused(err);
    } finally {
      setChecking(false);
    }
  };

  return (
    <li aria-labelledby={headingId} className="bg-white rounded-xl border border-stone-200 p-4">
      <h2 id={headingId} className="text-[15px] font-semibold text-stone-900">{type.label}</h2>
      <p className="mt-1 text-[14px] text-stone-700 leading-relaxed">{type.description}</p>

      <dl className="mt-3 grid gap-x-6 gap-y-1 text-[14px] sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-stone-700">Period</dt>
        <dd className="text-stone-900">{periodText(current)}</dd>
        <dt className="font-medium text-stone-700">Last ran</dt>
        <dd className="text-stone-900">{lastRunText(type, lastRun)}</dd>
      </dl>

      <form onSubmit={submit} noValidate className="mt-4 flex flex-wrap items-start gap-3">
        <div className="w-full max-w-[16rem]">
          <Input
            id={inputId}
            label="Period in days"
            inputMode="numeric"
            value={value}
            onChange={(e) => { setValue(e.target.value); setFieldErr(null); setDone(null); }}
            error={fieldErr ?? undefined}
            hint="Whole days. Leave blank to erase nothing."
            optional
          />
        </div>
        <Button type="submit" className="sm:mt-6" disabled={!changed} loading={checking || (saving && !pending)}>
          Save period
        </Button>
      </form>

      {error && (
        <p role="alert" className={`mt-3 ${LOAD_ERROR}`}>
          <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
          {error}
        </p>
      )}
      {done && <p role="status" className="mt-3 text-[14px] text-stone-700">{done}</p>}

      <ConfirmDialog
        open={pending !== null}
        title="Erase existing data?"
        message={
          pending
            ? `With a period of ${periodText(pending.days)}, the next daily cleanup erases ` +
              `${type.items(pending.count)}, which are older than that now. Erased text can't be recovered.`
            : ""
        }
        confirmLabel="Save and erase"
        danger
        focusCancel
        confirming={saving}
        onConfirm={() => { if (pending) void save(pending.days); }}
        onCancel={() => setPending(null)}
      />
    </li>
  );
}

async function readPage(signal: AbortSignal) {
  const [settings, runs] = await Promise.all([
    Promise.all(RETENTION_TYPES.map((t) => accountsApi.getSetting(t.settingKey, { signal }).then(({ data }) => data.value))),
    auditApi.list({ event_type: "RETENTION_CLEANUP_RUN", page_size: 1 }, { signal }),
  ]);
  const latest = runs.data.results[0];
  const lastRun: LastRun | null = latest
    ? { at: latest.created_at, counts: ((latest.metadata as { counts?: Record<string, number> })?.counts) ?? {} }
    : null;
  return { settings, lastRun };
}

export default function RetentionPage() {
  const read = useApiRead(readPage, []);
  const data = read.data;

  return (
    <div>
      <PageHeader
        title="Retention"
        description="How long IRIS keeps personal data before the daily cleanup erases it."
      />

      <div className={`mb-4 ${WARNING_NOTICE}`}>
        <i className="fas fa-exclamation-triangle mt-0.5 flex-shrink-0" aria-hidden />
        <div className="space-y-1">
          <p>
            <strong>A blank period erases nothing.</strong> Every period starts blank, and IRIS has no default.
          </p>
          <p>
            Enter a period only after the <strong>data protection officer has approved it</strong>.
            The cleanup runs every day at 3:00 a.m. Philippine time, and erased data can't be recovered. The Audit Log is never erased.
          </p>
        </div>
      </div>

      {read.status === "interrupted" ? (
        <InterruptedState what="retention periods" onRetry={read.retry} />
      ) : read.status === "loading" ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading retention periods" onRetry={read.retry} />
        </div>
      ) : read.status === "failed" || !data ? (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The retention periods didn't load." })}
          onRetry={read.retry}
        />
      ) : (
        <ul aria-label="Retention periods" className="space-y-3">
          {RETENTION_TYPES.map((type, i) => (
            <RetentionItem key={type.key} type={type} saved={data.settings[i]} lastRun={data.lastRun} />
          ))}
        </ul>
      )}
    </div>
  );
}
