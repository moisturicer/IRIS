import { useCallback, useEffect, useRef, useState } from "react";
import { authApi } from "@/api/auth";
import { accountsApi } from "@/api/accounts";
import { noticeApi, staleNoticeFrom } from "@/api/notice";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { Button } from "@/components/ui";
import { Spinner } from "@/components/ui/Spinner";
import { errorDetail } from "@/lib/errorDetail";
import { useAuthStore } from "@/store/auth.store";
import { useNoticeStore } from "@/store/notice.store";
import type { DataNotice } from "@/types/notice";
import {
  NO_ANSWERS,
  NoticeAnswerFields,
  NoticeText,
  missingAnswers,
  type NoticeAnswerErrors,
  type NoticeAnswers,
} from "./NoticeAnswerFields";

/**
 * The screen a signed-in person sees until they answer the current data notice
 * (ADR-054 decision 3, IR-790). Until then the server refuses every request but
 * reading the notice, answering it, signing out and requesting deletion, so
 * those are the only things offered here.
 *
 * `ProtectedRoute` renders it in place of the page, so a refresh lands here
 * again and the address the person asked for is kept for afterwards.
 */

type Phase = "loading" | "failed" | "ready";

const NEWER_NOTICE = "A newer notice was published while this one was open. Read it, then answer again.";

export function NoticeAnswerScreen() {
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const user = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);
  const logout = useAuthStore((s) => s.logout);
  const clearNotice = useNoticeStore((s) => s.clear);

  const [phase, setPhase] = useState<Phase>("loading");
  const [notice, setNotice] = useState<DataNotice | null>(null);
  const [answers, setAnswers] = useState<NoticeAnswers>(NO_ANSWERS);
  const [errors, setErrors] = useState<NoticeAnswerErrors>({});
  const [alert, setAlert] = useState<{ title: string; message: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletion, setDeletion] = useState<"idle" | "confirming" | "sending" | "sent">("idle");
  const [deletionError, setDeletionError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const shownVersion = useRef<number | null>(null);

  /** A newer version replaces the text, and the answers start again. */
  const showNotice = useCallback((next: DataNotice) => {
    const replaced = shownVersion.current !== null && shownVersion.current !== next.version;
    shownVersion.current = next.version;
    setNotice(next);
    if (replaced) {
      setAnswers(NO_ANSWERS);
      setErrors({});
      setAlert({ title: "The notice changed", message: NEWER_NOTICE });
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const { data } = await noticeApi.current();
      showNotice(data);
      setPhase("ready");
    } catch {
      setPhase((p) => (p === "ready" ? p : "failed"));
    }
  }, [showNotice]);

  useEffect(() => {
    void load();
  }, [load]);

  // Coming back to the tab re-reads the notice, so one published while the
  // screen sat open replaces the text before they answer.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  useEffect(() => {
    if (phase === "ready") headingRef.current?.focus();
  }, [phase]);

  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!notice) return;
    const missing = missingAnswers(answers);
    setErrors(missing);
    if (missing.agree || missing.ai) return;
    setSubmitting(true);
    setAlert(null);
    try {
      await noticeApi.answer({ notice_version: notice.version, agree_dpa: true, ai_consent: answers.ai === true });
      // The account could not load while the notice was unanswered (a refresh
      // lands here with no user), so load it now, then let the page show.
      if (!user) {
        const { data } = await authApi.me();
        updateUser(data);
      }
      clearNotice();
    } catch (err) {
      const newer = staleNoticeFrom(err);
      if (newer) showNotice(newer);
      else setAlert({ title: "Your answer wasn't saved", message: errorDetail(err, "Try again.") });
    } finally {
      setSubmitting(false);
    }
  };

  const signOut = async () => {
    await authApi.logout(refreshToken ?? "").catch(() => {});
    logout();
  };

  const requestDeletion = async () => {
    setDeletion("sending");
    setDeletionError(null);
    try {
      await accountsApi.requestMyDeletion();
      setDeletion("sent");
    } catch (err) {
      setDeletion("confirming");
      setDeletionError(errorDetail(err, "The request wasn't sent. Try again."));
    }
  };

  return (
    <main className="min-h-screen bg-stone-50 px-4 py-8 sm:py-12">
      <div className="mx-auto max-w-2xl rounded-xl border border-stone-200 bg-white p-5 sm:p-8">
        <h1 ref={headingRef} tabIndex={-1} className="text-title font-bold text-stone-900 focus:outline-none">
          Read and answer the data notice
        </h1>
        <p className="mt-2 text-small text-stone-600">
          IRIS needs your answer to the current notice before you continue.
        </p>

        {phase === "loading" && (
          <div role="status" className="flex items-center gap-2 py-10 text-small text-stone-600">
            <Spinner size="sm" />
            Loading the notice…
          </div>
        )}

        {phase === "failed" && (
          <div className="mt-6">
            <AuthAlert variant="error" title="The notice didn't load">
              Check your connection, then try again.
            </AuthAlert>
            <Button type="button" onClick={() => { setPhase("loading"); void load(); }}>
              Try again
            </Button>
          </div>
        )}

        {phase === "ready" && notice && (
          <form onSubmit={submit} noValidate className="mt-6 space-y-6">
            {alert && (
              <AuthAlert variant="warning" title={alert.title} focusRef={alertRef}>
                {alert.message}
              </AuthAlert>
            )}
            <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-stone-200 bg-stone-50 px-4 py-3" tabIndex={0} role="region" aria-label="Data notice">
              <NoticeText notice={notice} />
            </div>
            <NoticeAnswerFields value={answers} onChange={setAnswers} errors={errors} />
            <Button type="submit" loading={submitting} className="w-full sm:w-auto">
              Save my answer
            </Button>
          </form>
        )}

        <div className="mt-8 border-t border-stone-200 pt-5">
          <h2 className="text-small font-semibold text-stone-900">Not ready to answer?</h2>
          <div className="mt-3 flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
            {deletion === "idle" && (
              <Button type="button" variant="ghost" onClick={() => setDeletion("confirming")}>
                Request account deletion
              </Button>
            )}
          </div>
          {(deletion === "confirming" || deletion === "sending") && (
            <div className="mt-4 rounded-lg border border-stone-200 px-4 py-3" role="group" aria-label="Request account deletion">
              <p className="text-small text-stone-700">
                Your account is deleted once the System Admin confirms it, which they do only when nobody is waiting
                on you. Send the request?
              </p>
              {deletionError && <p role="alert" className="mt-2 text-small text-brand">{deletionError}</p>}
              <div className="mt-3 flex flex-wrap gap-3">
                <Button type="button" variant="danger" loading={deletion === "sending"} onClick={() => void requestDeletion()}>
                  Send the request
                </Button>
                <Button type="button" variant="ghost" onClick={() => { setDeletion("idle"); setDeletionError(null); }}>
                  Keep my account
                </Button>
              </div>
            </div>
          )}
          {deletion === "sent" && (
            <p role="status" className="mt-4 text-small text-stone-700">
              Your request was sent. The System Admin will confirm it once nobody is waiting on you.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
