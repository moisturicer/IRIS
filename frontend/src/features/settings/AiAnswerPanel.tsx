/**
 * Settings' "May AI use your papers?" (ADR-054 decisions 11 to 13, IR-793).
 *
 * Shows the person's current answer and the notice version it was given
 * under, and lets them change it at any time. Yes to No reaches only forward:
 * earlier papers keep their Yes. No to Yes asks which papers, with neither
 * choice preselected, through the same `WhichPapers` the notice screen asks.
 *
 * The answer is the person's, never a paper's: each paper keeps the answer it
 * started with, and no screen offers a per-paper control.
 */
import { useCallback, useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import { noticeApi } from "@/api/notice";
import { Button } from "@/components/ui";
import { Spinner } from "@/components/ui/Spinner";
import { PAPERS_REQUIRED, WhichPapers, type PapersChoice } from "@/features/auth/notice/NoticeAnswerFields";
import { errorDetail } from "@/lib/errorDetail";
import { formatDate } from "@/lib/utils";
import type { NoticeAnswer } from "@/types/notice";
import { Message, Panel } from "./settingsParts";

type Phase = "loading" | "failed" | "ready";

function papersNote(count: number): string {
  if (count === 0) return "";
  return count === 1
    ? " 1 paper you're Contact person of now holds your Yes."
    : ` ${count} papers you're Contact person of now hold your Yes.`;
}

export function AiAnswerPanel() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [answer, setAnswer] = useState<NoticeAnswer | null>(null);
  const [changing, setChanging] = useState(false);
  const [papers, setPapers] = useState<PapersChoice | null>(null);
  const [papersError, setPapersError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await noticeApi.current();
      setAnswer(data.answer ?? null);
      setPhase("ready");
    } catch {
      setPhase("failed");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const current = answer?.ai_consent ?? null;
  const next = current !== true;

  const startChange = () => {
    setChanging(true);
    setPapers(null);
    setPapersError(undefined);
    setError(null);
    setSaved(null);
  };

  const stopChange = () => {
    setChanging(false);
    setError(null);
  };

  const save = async () => {
    // Only a No becoming a Yes asks which papers; a first answer has no earlier papers to cover.
    const asksPapers = next && current === false;
    if (asksPapers && papers === null) {
      setPapersError(PAPERS_REQUIRED);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { data } = await accountsApi.changeAiAnswer({
        ai_consent: next,
        ...(asksPapers && papers ? { papers } : {}),
      });
      setAnswer(data.answer);
      setChanging(false);
      setSaved(
        next
          ? `Your answer is now Yes.${papersNote(data.papers_updated)}`
          : "Your answer is now No. It applies to papers from now on.",
      );
    } catch (err) {
      setError(errorDetail(err, "Your answer wasn't changed. Try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel
      title="May AI use your papers?"
      caption="Your answer covers the papers you're Contact person of. Each paper keeps the answer it started with, and there is no setting per paper."
    >
      {phase === "loading" && (
        <p role="status" className="flex items-center gap-2 text-[13px] text-stone-600">
          <Spinner size="sm" />
          Loading your answer…
        </p>
      )}

      {phase === "failed" && (
        <div className="space-y-3">
          <Message tone="error" role="alert">Your answer didn't load. Check your connection, then try again.</Message>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={() => { setPhase("loading"); void load(); }}>
              Try again
            </Button>
          </div>
        </div>
      )}

      {phase === "ready" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-stone-200 p-4" role="group" aria-label="Your answer">
            <p className="text-[14px] font-semibold text-stone-900">
              {current === true && "Yes, AI may use your papers"}
              {current === false && "No, AI doesn't use your papers"}
              {current === null && "You haven't answered yet"}
            </p>
            {answer?.version != null && (
              <p className="text-[13px] text-stone-600 mt-0.5">
                Given under notice version {answer.version}
                {answer.answered_at ? ` on ${formatDate(answer.answered_at)}` : ""}.
              </p>
            )}
          </div>

          {saved && <Message tone="ok" role="status">{saved}</Message>}

          {!changing ? (
            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="secondary" onClick={startChange}>
                {next ? "Change to Yes" : "Change to No"}
              </Button>
            </div>
          ) : (
            <div
              className="rounded-lg border border-stone-200 p-4 space-y-4"
              role="group"
              aria-label={next ? "Change your answer to Yes" : "Change your answer to No"}
            >
              {next ? (
                current === false ? (
                  <WhichPapers
                    value={papers}
                    onChange={(choice) => { setPapers(choice); setPapersError(undefined); }}
                    error={papersError}
                  />
                ) : (
                  <p className="text-[13px] text-stone-700">
                    IRIS may then send your papers&apos; text to AI companies, subject to the embargo and the IP
                    mark. Text already sent can&apos;t be recalled.
                  </p>
                )
              ) : (
                <p className="text-[13px] text-stone-700">
                  This only affects papers from now on. Your earlier papers keep their Yes and stay in use by AI,
                  and what was already processed stays.
                </p>
              )}
              <div className="flex flex-wrap gap-3">
                <Button type="button" loading={saving} onClick={() => void save()}>
                  {next ? "Change to Yes" : "Change to No"}
                </Button>
                <Button type="button" variant="ghost" onClick={stopChange}>
                  Keep my answer
                </Button>
              </div>
            </div>
          )}

          {error && <Message tone="error" role="alert">{error}</Message>}
        </div>
      )}
    </Panel>
  );
}
