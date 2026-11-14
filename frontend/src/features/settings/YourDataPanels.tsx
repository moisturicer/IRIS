/**
 * Settings' self-service for a person's own data (ADR-051 §8 and decision 13,
 * IR-787): download a copy of it, and ask for the account to be deleted.
 *
 * Both act on the signed-in account only. The server takes no id for either,
 * so nothing here can name someone else's account.
 */
import { useCallback, useEffect, useState } from "react";
import { accountsApi, type MyDeletionRequest } from "@/api/accounts";
import { Button } from "@/components/ui";
import { Spinner } from "@/components/ui/Spinner";
import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";
import { formatDate } from "@/lib/utils";
import { Message, Panel } from "./settingsParts";

const FILE_NAME = "iris-my-data.json";

/* -------------------------------------------------------------------------- */
/* Download my data                                                           */
/* -------------------------------------------------------------------------- */

type DownloadState = "idle" | "preparing" | "saved" | "failed";

export function DownloadMyDataPanel() {
  const [state, setState] = useState<DownloadState>("idle");
  const [failure, setFailure] = useState("");

  const download = async () => {
    setState("preparing");
    try {
      const { data } = await accountsApi.downloadMyData();
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = FILE_NAME;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setState("saved");
    } catch (err) {
      // The body of a refused blob request is a Blob, so its detail can't be
      // read here; the status says enough.
      const status = (err as { response?: { status?: number } })?.response?.status;
      setFailure(
        status === 429
          ? "You've downloaded your data several times recently. Try again later."
          : failureMessage(err, { lead: "Your file wasn't downloaded." }),
      );
      setState("failed");
    }
  };

  return (
    <Panel
      title="Download my data"
      caption="A copy of the personal data IRIS keeps about you, as one JSON file. Only you can download it."
    >
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" loading={state === "preparing"} onClick={() => void download()}>
          Download my data
        </Button>
        {state === "preparing" && (
          <p role="status" className="flex items-center gap-2 text-[13px] text-stone-600">
            <Spinner size="sm" />
            Preparing your file…
          </p>
        )}
      </div>
      {state === "saved" && (
        <div className="mt-3">
          <Message tone="ok" role="status">Your file was saved as {FILE_NAME}.</Message>
        </div>
      )}
      {state === "failed" && (
        <div className="mt-3">
          <Message tone="error" role="alert">{failure}</Message>
        </div>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Delete my account                                                          */
/* -------------------------------------------------------------------------- */

/** What a confirmed deletion does, per ADR-051 decision 11. Shown before anyone confirms. */
function WhatDeletionDoes() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <h3 className="text-[14px] font-semibold text-stone-900">What goes</h3>
        <ul className="mt-2 space-y-1.5 text-[13px] text-stone-600 leading-relaxed list-disc pl-5">
          <li>Your profile and photo. You leave people search, the Adviser picker and reviewer pools.</li>
          <li>Your private data, including drafts nobody else is waiting on.</li>
          <li>Your sign-in. You can't sign in again, and your email can later register as a new account.</li>
        </ul>
      </div>
      <div>
        <h3 className="text-[14px] font-semibold text-stone-900">What stays</h3>
        <ul className="mt-2 space-y-1.5 text-[13px] text-stone-600 leading-relaxed list-disc pl-5">
          <li>Your name as an author on published papers.</li>
          <li>Your name as Adviser on a published paper, as plain text with no link.</li>
          <li>Comments and review history, shown as "Former user".</li>
          <li>Audit records, which keep your name and email.</li>
        </ul>
      </div>
    </div>
  );
}

type Phase = "loading" | "failed" | "ready";

export function DeleteAccountPanel() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [request, setRequest] = useState<MyDeletionRequest | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const { data } = await accountsApi.myDeletionRequest({ signal });
      setRequest(data.request);
      setPhase("ready");
    } catch (err) {
      if (!signal?.aborted) { setLoadError(err); setPhase("failed"); }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await accountsApi.requestMyDeletion();
      setRequest(data.request);
      setConfirming(false);
    } catch (err) {
      setError(errorDetail(err, "Your request wasn't sent. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await accountsApi.cancelMyDeletion();
      setRequest(data.request);
    } catch (err) {
      setError(errorDetail(err, "Your request wasn't cancelled. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const pending = request?.status === "pending";

  return (
    <Panel
      title="Delete my account"
      caption="Ask for your account to be deleted. The System Admin confirms it once nobody is waiting on you."
    >
      {phase === "loading" && (
        <p role="status" className="flex items-center gap-2 text-[13px] text-stone-600">
          <Spinner size="sm" />
          Checking for a deletion request…
        </p>
      )}

      {phase === "failed" && (
        <div className="space-y-3">
          <Message tone="error" role="alert">{failureMessage(loadError, { lead: "Your deletion request didn't load." })}</Message>
          <Button type="button" variant="secondary" onClick={() => { setPhase("loading"); void load(); }}>
            Try again
          </Button>
        </div>
      )}

      {phase === "ready" && (
        <div className="space-y-5">
          {pending && request ? (
            <div className="rounded-lg border border-stone-200 p-4 space-y-3" role="group" aria-label="Your deletion request">
              <p className="text-[14px] font-semibold text-stone-900">
                Request sent on {formatDate(request.created_at)}, waiting for the System Admin
              </p>
              {request.blockers.length > 0 ? (
                <div>
                  <p className="text-[13px] text-stone-600">It can't be confirmed until this is cleared:</p>
                  <ul className="mt-2 space-y-1.5 text-[13px] text-stone-700 leading-relaxed list-disc pl-5">
                    {request.blockers.map((b) => (
                      <li key={`${b.kind}-${b.record}`}>{b.message}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-[13px] text-stone-600">Nothing is waiting on you, so it can be confirmed.</p>
              )}
              {request.can_cancel && (
                <div className="flex flex-wrap gap-3">
                  <Button type="button" variant="secondary" loading={busy} onClick={() => void cancel()}>
                    Cancel my request
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <>
              {request?.status === "declined" && (
                <div className="rounded-lg border border-stone-200 p-4" role="group" aria-label="Your last deletion request">
                  <p className="text-[14px] font-semibold text-stone-900">
                    Your last request was rejected{request.decided_at ? ` on ${formatDate(request.decided_at)}` : ""}
                  </p>
                  <p className="text-[13px] text-stone-600 mt-1">Reason: {request.reason}</p>
                </div>
              )}
              {request?.status === "cancelled" && (
                <p role="status" className="text-[13px] text-stone-600">
                  You cancelled your request. Your account stays as it is.
                </p>
              )}

              <WhatDeletionDoes />

              {!confirming ? (
                <div className="flex flex-wrap gap-3">
                  <Button type="button" variant="danger" onClick={() => setConfirming(true)}>
                    Delete my account
                  </Button>
                </div>
              ) : (
                <div className="rounded-lg border border-stone-200 p-4" role="group" aria-label="Delete my account">
                  <p className="text-[13px] text-stone-700">
                    The System Admin deletes your account once they confirm it, and that can't be undone. Until
                    then you can cancel. Send the request?
                  </p>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <Button type="button" variant="danger" loading={busy} onClick={() => void send()}>
                      Send the request
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => { setConfirming(false); setError(null); }}>
                      Keep my account
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}

          {error && <Message tone="error" role="alert">{error}</Message>}
        </div>
      )}
    </Panel>
  );
}
