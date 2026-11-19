/**
 * Setup's Notice section (ADR-051 decisions 16-17 as amended by ADR-063
 * decision 9; IR-800, moved onto Setup by IR-972). IRIS has one data notice.
 * RDCO publishes its next version by pasting the whole text and reads every
 * version. The System Admin no longer has this page: it reads each publication
 * in the Audit Log, and an old `/notices` link takes it there.
 *
 * Publishing first shows how many people must answer the new version, and
 * says plainly that the data protection officer approves the text first and
 * that a published version can't be changed. A publish raced by another is
 * refused by the server (409 `notice_stale`); the paste is kept and the page
 * shows the version that is current now.
 *
 *   GET  /auth/notice/versions/          RDCO
 *   GET  /auth/notice/versions/impact/   RDCO
 *   POST /auth/notice/versions/          RDCO   {based_on_version, text}
 */
import { useEffect, useId, useState } from "react";
import { noticeApi, staleNoticeFrom, type NoticeDraft, type NoticeVersion } from "@/api/notice";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { failureMessage } from "@/lib/readFailure";
import { Button } from "@/components/ui/Button";
import { WARNING_NOTICE } from "@/components/ui/fieldClasses";
import { Spinner } from "@/components/ui/Spinner";
import { NoticeText } from "@/features/auth/notice/NoticeText";
import { useApiRead } from "@/hooks/useApiRead";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { formatDate } from "@/lib/utils";

function published(v: NoticeVersion): string {
  const by = v.published_by?.name || v.published_by?.email;
  return `published ${formatDate(v.published_at)}${by ? ` by ${by}` : ""}`;
}

function people(n: number): string {
  return n === 1 ? "1 person must" : `${n} people must`;
}

/** Only a list of versions is usable; anything else is a failed read (CODING_STANDARDS F1). */
function isVersionList(data: unknown): data is NoticeVersion[] {
  return Array.isArray(data) && data.every((v) => v && typeof v.version === "number" && typeof v.text === "string");
}

export default function NoticeSection() {
  const read = useApiRead((signal) => noticeApi.versions({ signal }).then((r) => r.data), []);
  // A reread after publishing puts the read back to loading. The last history
  // stays on screen meanwhile, so the form, its paste and its outcome stay too.
  const [shown, setShown] = useState<NoticeVersion[] | null>(null);
  useEffect(() => {
    if (read.status === "ready") setShown(isVersionList(read.data) ? read.data : null);
  }, [read.status, read.data]);
  const fresh = isVersionList(read.data) ? read.data : null;
  const list = read.status === "ready" ? fresh : shown;
  const current = list?.[0] ?? null;

  return (
    <div className="space-y-4">
      <p className="text-small text-stone-600">
        The privacy notice every account answers. Publishing a new version asks everyone to read it again.
      </p>

      <div role="note" className={WARNING_NOTICE}>
        <i className="fas fa-exclamation-triangle mt-0.5 flex-shrink-0" aria-hidden />
        <p>
          The data protection officer must approve the text before you publish it. A version can&apos;t be changed
          once it is published: a correction is a new version, which everyone answers again.
        </p>
      </div>

      {read.status === "interrupted" && !list ? (
        <InterruptedState what="notices" onRetry={read.retry} framed />
      ) : read.status === "loading" && !list ? (
        <p role="status" className="flex items-center gap-2 text-small text-stone-600">
          <Spinner size="sm" />
          Loading the notices…
        </p>
      ) : !list || !current ? (
        <div className="space-y-3 rounded-card border border-stone-200 bg-white p-5">
          <p role="alert" className="text-small text-stone-700">{failureMessage(read.error, { lead: "The notices didn't load." })}</p>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="outline" onClick={read.retry}>Try again</Button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="order-2 lg:order-1">
              <PublishForm current={current} onPublished={read.retry} />
            </div>
            <aside
              role="group"
              aria-label="Current version"
              className="order-1 rounded-card border border-stone-200 bg-white p-5 lg:order-2"
            >
              <h2 className="text-heading font-semibold text-stone-900">Live now</h2>
              <p className="mt-1 text-small font-semibold text-stone-900">
                Version {current.version}, {published(current)}
              </p>
            </aside>
          </div>

          <VersionHistory versions={list} />
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Publishing                                                                 */
/* -------------------------------------------------------------------------- */

function PublishForm({ current, onPublished }: { current: NoticeVersion; onPublished: () => void }) {
  const fieldId = useId();
  const errorId = useId();
  const [text, setText] = useState(current.text);
  // The version this paste replaces. It moves only when the page reads a newer
  // one, so a publish raced by someone else is refused, never applied unseen.
  const [base, setBase] = useState(current.version);
  const [preview, setPreview] = useState(false);
  const [confirm, setConfirm] = useState<{ accounts: number } | null>(null);
  const [counting, setCounting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [alert, setAlert] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // The saved draft, if any (IR-1138): read once, and applied only while the
  // paste is still the live text, so it never overwrites what RDCO has typed.
  const [draft, setDraft] = useState<NoticeDraft | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);

  useEffect(() => {
    setBase(current.version);
  }, [current.version]);

  useEffect(() => {
    let live = true;
    Promise.resolve()
      .then(() => noticeApi.draft())
      .then(({ data }) => {
        if (!live || !data) return;
        setDraft(data);
        setText((typed) => (typed === current.text ? data.text : typed));
      })
      // No draft read is no draft: the form still works.
      .catch(() => undefined);
    return () => { live = false; };
    // Read once, when the form opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const next = base + 1;
  const unchanged = text === current.text;
  const blank = text.trim() === "";
  const publishBlockedReason = blank
    ? "Enter the notice text to publish."
    : unchanged
      ? "Change the text to publish a new version."
      : undefined;

  const ask = async () => {
    setCounting(true);
    setAlert(null);
    setDone(null);
    try {
      const { data } = await noticeApi.impact();
      setConfirm({ accounts: data.accounts_to_answer });
    } catch (err) {
      setAlert(errorDetail(err, "The number of people who must answer couldn't be counted. Try again."));
    } finally {
      setCounting(false);
    }
  };

  const saveDraft = async () => {
    setSavingDraft(true);
    setAlert(null);
    setDone(null);
    try {
      const { data } = await noticeApi.saveDraft({ based_on_version: base, text });
      setDraft(data);
      setDone("Draft saved. Only RDCO can see it, and nobody is asked to answer it.");
    } catch (err) {
      setAlert(errorDetail(err, "The draft wasn't saved. Try again."));
    } finally {
      setSavingDraft(false);
    }
  };

  const publish = async () => {
    setPublishing(true);
    setTextError(null);
    try {
      const { data } = await noticeApi.publish({ based_on_version: base, text });
      setConfirm(null);
      setDraft(null);
      setDone(`Version ${data.version} is published. Everyone answers it the next time they use IRIS.`);
      onPublished();
    } catch (err) {
      setConfirm(null);
      const newer = staleNoticeFrom(err);
      if (newer) {
        setAlert(
          `${errorDetail(err, "A newer version was published.")} Version ${newer.version} is current now. ` +
          `Read it below before publishing your text as version ${newer.version + 1}.`,
        );
        onPublished();
      } else {
        const refused = fieldError(err, "text", "based_on_version");
        if (refused) setTextError(refused);
        else setAlert(errorDetail(err, "The notice wasn't published. Try again."));
      }
    } finally {
      setPublishing(false);
    }
  };

  return (
    <section aria-labelledby={`${fieldId}-title`} className="rounded-card border border-stone-200 bg-white p-5 space-y-4">
      <h2 id={`${fieldId}-title`} className="text-heading font-semibold text-stone-900">Publish a new version</h2>

      {alert && <p role="alert" className={WARNING_NOTICE}>{alert}</p>}
      {done && <p role="status" className="text-small text-stone-700">{done}</p>}
      {draft && (
        <p className="text-label text-stone-600">
          Draft saved {formatDate(draft.updated_at)}{draft.updated_by ? ` by ${draft.updated_by}` : ""}.
          {draft.based_on_version < current.version &&
            ` It started from version ${draft.based_on_version}; version ${current.version} is live now.`}
        </p>
      )}

      <div>
        <label htmlFor={fieldId} className="block text-small font-semibold text-stone-900">Notice text</label>
        <p className="mt-1 text-label text-stone-600">
          Paste the whole notice. It is shown exactly as written, line breaks included, with no formatting or links.
        </p>
        <textarea
          id={fieldId}
          value={text}
          onChange={(e) => { setText(e.target.value); setTextError(null); }}
          rows={16}
          aria-invalid={textError ? true : undefined}
          aria-describedby={textError ? errorId : undefined}
          className="mt-2 w-full rounded-control border border-field px-3 py-2 font-mono text-small text-stone-900"
        />
        {textError && <p id={errorId} className="mt-1.5 text-small text-brand">{textError}</p>}
      </div>

      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          variant="outline"
          loading={savingDraft}
          disabled={blank}
          disabledReason={blank ? "Enter the notice text to save a draft." : undefined}
          onClick={() => void saveDraft()}
        >
          Save draft
        </Button>
        <Button type="button" variant="outline" aria-expanded={preview} onClick={() => setPreview((p) => !p)}>
          {preview ? "Hide preview" : "Preview"}
        </Button>
        <Button
          type="button"
          loading={counting}
          disabled={unchanged || blank}
          disabledReason={publishBlockedReason}
          onClick={() => void ask()}
        >
          Publish version {next}
        </Button>
      </div>

      {preview && (
        <section aria-label="Preview" className="rounded-card border border-stone-200 bg-stone-50 px-4 py-3">
          <NoticeText notice={{ version: next, text, published_at: null }} headingLevel={3} />
        </section>
      )}

      <ConfirmDialog
        open={confirm !== null}
        title={`Publish version ${next}?`}
        message={
          confirm
            ? `${people(confirm.accounts)} answer it before they can keep using IRIS. ` +
              "A published version can't be changed."
            : ""
        }
        confirmLabel="Publish"
        confirming={publishing}
        onConfirm={() => void publish()}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* History                                                                    */
/* -------------------------------------------------------------------------- */

function VersionHistory({ versions }: { versions: NoticeVersion[] }) {
  const titleId = useId();
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section aria-labelledby={titleId} className="rounded-card border border-stone-200 bg-white p-5">
      <h2 id={titleId} className="text-heading font-semibold text-stone-900">Version history</h2>
      <ul className="mt-4 divide-y divide-stone-100">
        {versions.map((v) => {
          const expanded = open === v.version;
          return (
            <li key={v.version} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-small text-stone-900">
                  <span className="font-semibold">Version {v.version}</span>, {published(v)}
                </p>
                <div className="flex flex-wrap gap-3">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : v.version)}
                  >
                    {expanded ? `Hide version ${v.version}` : `Read version ${v.version}`}
                  </Button>
                </div>
              </div>
              {expanded && (
                <div className="mt-3 rounded-card border border-stone-200 bg-stone-50 px-4 py-3">
                  <NoticeText notice={v} headingLevel={3} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
