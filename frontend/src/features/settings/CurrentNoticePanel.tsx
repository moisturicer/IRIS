/**
 * Settings' copy of the data notice in force (ADR-051 decisions 16-17, IR-800):
 * the server's current version, as RDCO published it, through the same
 * `NoticeText` registration and the notice screen use.
 */
import { noticeApi } from "@/api/notice";
import { Button } from "@/components/ui";
import { Spinner } from "@/components/ui/Spinner";
import { NoticeText } from "@/features/auth/notice/NoticeText";
import { useApiRead } from "@/hooks/useApiRead";
import { Message, Panel } from "./settingsParts";

export function CurrentNoticePanel() {
  const read = useApiRead((signal) => noticeApi.current({ signal }).then((r) => r.data), []);
  const notice = read.data;

  return (
    <Panel title="Current data notice" caption="The notice in force now, as RDCO published it.">
      {read.status === "loading" ? (
        <p role="status" className="flex items-center gap-2 text-small text-stone-600">
          <Spinner size="sm" />
          Loading the notice…
        </p>
      ) : read.status !== "ready" || !notice || typeof notice.text !== "string" ? (
        // A wrong shape is treated as a failed read (CODING_STANDARDS F1).
        <div className="space-y-3">
          <Message tone="error" role="alert">The notice didn&apos;t load. Check your connection, then try again.</Message>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={read.retry}>Try again</Button>
          </div>
        </div>
      ) : (
        <div className="max-h-[420px] overflow-y-auto scrollbar-thin pr-1" tabIndex={0} role="group" aria-label="Notice text">
          <NoticeText notice={notice} headingLevel={3} />
        </div>
      )}
    </Panel>
  );
}
