import { useEffect, useRef, useState } from "react";
import { READER_PROTOCOL, activeRun, compactionRun, type ReaderRun } from "@/api/runtimeReader";
import { useAuthStore } from "@/store/auth.store";

/**
 * The answer as the model writes it, token by token, read from the run's
 * draft stream. Unchecked: the committed Turn replaces it. Empty when the
 * deployment publishes no drafts.
 */
export function useDraft(run: ReaderRun | undefined, recordId?: number) {
  const [text, setText] = useState("");
  const latest = useRef("");
  const live = !!run && activeRun(run) && !compactionRun(run) && run.state === "running";
  const runId = run?.id;

  useEffect(() => {
    if (!live || !runId) return;
    const controller = new AbortController();
    let buffer = "";
    let draft = "";
    const show = (next: string) => { draft = next; latest.current = next; setText(next); };
    show("");
    void (async () => {
      try {
        const token = useAuthStore.getState().accessToken;
        const response = await fetch(`/api/v1/ai/runtime/runs/${encodeURIComponent(runId)}/draft`, {
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream", "X-IRIS-Protocol": READER_PROTOCOL,
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(recordId ? { "X-IRIS-Record": String(recordId) } : {}),
          },
        });
        if (!response.ok || !response.body) return;
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) return;
          buffer += value;
          let cut = buffer.indexOf("\n\n");
          while (cut >= 0) {
            const frame = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            cut = buffer.indexOf("\n\n");
            const data = frame.split("\n").filter(l => l.startsWith("data:")).map(l => l.slice(5).trim()).join("");
            if (!data) continue;
            try {
              const event = JSON.parse(data) as { t: string; d?: string };
              if (event.t === "reset") show("");
              else if (event.t === "text" && event.d) show(draft + event.d);
              else if (event.t === "end") return;
            } catch { /* a malformed frame costs one piece of the live view */ }
          }
        }
      } catch { /* aborted, or the stream dropped: the Turn still arrives */ }
    })();
    return () => controller.abort();
  }, [live, runId, recordId]);

  return { text: live ? text : "", last: latest };
}
