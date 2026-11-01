/**
 * RDCO's download-request queue (ADR-048): the only one. Gated to RDCO by
 * ProtectedRoute in router/index.tsx; the server refuses everyone else anyway.
 *
 * Backend endpoints:
 *   GET  /records/download-requests/                → list all requests
 *   POST /records/download-requests/<id>/approve/   → approve (a time-limited grant)
 *   POST /records/download-requests/<id>/decline/   → decline, with a note
 *   POST /records/download-requests/<id>/revoke/    → end a live grant, with a note
 *
 * Each row shows the reader's note and each grant's expiry. Declining and
 * revoking ask for a note the reader is sent (IR-688); approving takes none.
 */
import { useEffect, useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { Spinner }     from "@/components/ui/Spinner";
import { EmptyState }  from "@/components/shared/EmptyState";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { formatDate }  from "@/lib/utils";
import type { DownloadRequest } from "@/types/records";

/** The longest note RDCO may leave (IR-688; the server enforces it too). */
const NOTE_MAX_LENGTH = 500;
/** Shown where a request made before notes existed has none (IR-688). */
const NO_NOTE = "No note recorded";

const STATUS_STYLES: Record<DownloadRequest["status"], string> = {
  pending:   "bg-amber-50  text-amber-700  border-amber-200",
  approved:  "bg-green-50  text-green-700  border-green-200",
  declined:  "bg-red-50    text-red-700    border-red-200",
  revoked:   "bg-red-50    text-red-700    border-red-200",
  cancelled: "bg-stone-50  text-stone-600  border-stone-200",
};

type Filter = "" | "pending" | "approved" | "declined" | "revoked";
const FILTERS: readonly Filter[] = ["pending", "approved", "declined", "revoked", ""];

/** A decline or a revocation: both say why, in a note the reader is sent. */
type NoteAct = { kind: "decline" | "revoke"; request: DownloadRequest };

const NOTE_ACTS = {
  decline: {
    title:  "Decline download request",
    submit: "Decline",
    intro:  "The reader is told in-app and by email, with your note, and may request again.",
    send:   recordsApi.declineDownloadRequest,
  },
  revoke: {
    title:  "Revoke download access",
    submit: "Revoke",
    intro:  "The reader can no longer download this paper. They are told in-app and by email, " +
            "with your note, and may request again.",
    send:   recordsApi.revokeDownloadRequest,
  },
} as const;

function NoteDialog({ act, onClose, onDone }: { act: NoteAct; onClose: () => void; onDone: () => void }) {
  const ids = useId();
  const copy = NOTE_ACTS[act.kind];
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const ready = note.trim() !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await copy.send(act.request.id, note.trim());
      onDone();
    } catch (err) {
      // The note stays in the box beside the server's reason.
      setError(fieldError(err, "note") ?? errorDetail(err, "That did not go through. Please try again."));
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const noteId = `${ids}-note`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title={copy.title}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!ready} loading={sending}>
            {copy.submit}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          <span className="font-semibold text-stone-900">{act.request.requested_by_name ?? act.request.requested_by_email}</span>
          {" · "}
          {act.request.record_title}. {copy.intro}
        </p>
        <div>
          <label htmlFor={noteId} className={LABEL}>
            Note to the reader
          </label>
          <textarea
            id={noteId}
            required
            rows={4}
            maxLength={NOTE_MAX_LENGTH}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-describedby={`${noteId}-help`}
            className={fieldClasses(false)}
          />
          <p id={`${noteId}-help`} className="mt-1 text-[13px] text-stone-600">
            The reader sees this as you write it. Up to {NOTE_MAX_LENGTH} characters.
          </p>
        </div>
        {error && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

/** Under an approved request: until when, or since when it has expired. */
function grantLine(req: DownloadRequest): string | null {
  if (req.status !== "approved" || !req.grant_expires_at) return null;
  const date = formatDate(req.grant_expires_at, "d MMM yyyy");
  return req.grant_live ? `Until ${date}` : `Expired ${date}`;
}

export default function DownloadRequestsPage() {
  const [requests, setRequests] = useState<DownloadRequest[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [approving, setApproving] = useState<number | null>(null);
  const [noteAct,  setNoteAct]  = useState<NoteAct | null>(null);
  const [error,    setError]    = useState<string | null>(null);

  const [filterStatus, setFilterStatus] = useState<Filter>("pending");

  const load = () => {
    setLoading(true);
    setError(null);
    const params: Record<string, unknown> = {};
    if (filterStatus) params.status = filterStatus;
    recordsApi.listDownloadRequests(params)
      .then(({ data }) => setRequests(data.results ?? []))
      .catch(() => setError("Failed to load requests."))
      .finally(() => setLoading(false));
  };

  useEffect(load, [filterStatus]);

  const handleApprove = async (id: number) => {
    if (!confirm("Approve this download request? The requester is told in-app and by email.")) return;
    setApproving(id);
    try {
      await recordsApi.approveDownloadRequest(id);
      load();
    } catch (err) {
      setError(errorDetail(err, "Action failed. Please try again."));
    } finally {
      setApproving(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Download Requests"
        description="Approve or decline requests to download a paper, and revoke access granted earlier."
      />

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4">
        {FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilterStatus(s)}
            aria-pressed={filterStatus === s}
            className={`px-3 py-1.5 rounded-lg text-[13px] font-semibold border transition-colors ${
              filterStatus === s
                ? "bg-[#6B0F12] text-white border-[#6B0F12]"
                : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
            }`}
          >
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-[13px] text-gray-500 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
        >
          <i className={`fas fa-sync-alt text-[12px] ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[14px] text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading download requests" /></div>
      ) : requests.length === 0 ? (
        <EmptyState
          icon="fa-download"
          title="No download requests"
          message={filterStatus === "pending" ? "No requests are currently pending." : "No requests match this filter."}
        />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <span className="text-[13px] text-gray-500 font-medium">
              {requests.length} request{requests.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left">
                  <th className="px-4 py-3 font-semibold text-gray-600">Record</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Requested By</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Reader's note</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-gray-600 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.map((req) => {
                  const grant = grantLine(req);
                  const endedByRdco = req.status === "declined" || req.status === "revoked";
                  return (
                    <tr key={req.id} className="hover:bg-gray-50 transition-colors align-top">
                      <td className="px-4 py-3">
                        <Link
                          to={`/records/${req.record}`}
                          className="text-[#6B0F12] font-medium hover:underline line-clamp-1"
                        >
                          {req.record_title}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-800">{req.requested_by_name ?? "—"}</p>
                        <p className="text-[12px] text-gray-500">{req.requested_by_email}</p>
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        {req.note
                          ? <p className="text-stone-700 whitespace-pre-line break-words">{req.note}</p>
                          : <p className="text-stone-500 italic">{NO_NOTE}</p>}
                      </td>
                      <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                        {formatDate(req.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[12px] font-semibold border ${STATUS_STYLES[req.status]}`}>
                          {req.status.charAt(0).toUpperCase() + req.status.slice(1)}
                        </span>
                        {grant && <p className="mt-1 text-[12px] text-stone-600 whitespace-nowrap">{grant}</p>}
                        {endedByRdco && (
                          <p className="mt-1 text-[12px] max-w-xs break-words">
                            <span className="text-stone-500">RDCO's note: </span>
                            {req.rdco_note
                              ? <span className="text-stone-700">{req.rdco_note}</span>
                              : <span className="text-stone-500 italic">{NO_NOTE}</span>}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {req.status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => handleApprove(req.id)}
                              disabled={approving === req.id}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium
                                text-green-700 border border-green-200 rounded-lg hover:bg-green-50
                                disabled:opacity-50 transition-colors"
                            >
                              {approving === req.id
                                ? <><Spinner size="sm" /> Approving…</>
                                : <><i className="fas fa-check" aria-hidden /> Approve</>}
                            </button>
                            <button
                              type="button"
                              onClick={() => setNoteAct({ kind: "decline", request: req })}
                              disabled={approving === req.id}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium
                                text-red-600 border border-red-200 rounded-lg hover:bg-red-50
                                disabled:opacity-50 transition-colors"
                            >
                              <i className="fas fa-times" aria-hidden /> Decline
                            </button>
                          </div>
                        ) : req.grant_live ? (
                          <button
                            type="button"
                            onClick={() => setNoteAct({ kind: "revoke", request: req })}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium
                              text-stone-700 border border-stone-300 rounded-lg hover:bg-stone-50 transition-colors"
                          >
                            <i className="fas fa-ban" aria-hidden /> Revoke
                          </button>
                        ) : (
                          <span className="text-[13px] text-gray-500 italic">
                            {req.revoked_at ? formatDate(req.revoked_at)
                              : req.cancelled_at ? `Cancelled ${formatDate(req.cancelled_at)}`
                              : req.reviewed_at ? formatDate(req.reviewed_at) : "Reviewed"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {noteAct && (
        <NoteDialog
          act={noteAct}
          onClose={() => setNoteAct(null)}
          onDone={() => { setNoteAct(null); load(); }}
        />
      )}
    </div>
  );
}
