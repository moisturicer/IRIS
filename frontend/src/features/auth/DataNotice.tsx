import { noticeApi } from "@/api/notice";
import { Spinner } from "@/components/ui/Spinner";
import { useApiRead } from "@/hooks/useApiRead";
import { NoticeText } from "./notice/NoticeAnswerFields";

/**
 * The "Data privacy" panel of the sign-in and registration frame: the server's
 * current notice (ADR-051 decisions 16-17, IR-800). IRIS holds no notice text
 * of its own; RDCO publishes it on the Notices page, and every screen reads it
 * from `GET /auth/notice/`, shown through the one `NoticeText`.
 */
export function DataNotice() {
  const read = useApiRead((signal) => noticeApi.current({ signal }).then((r) => r.data), []);
  const notice = read.data;

  if (read.status === "loading") {
    return (
      <p role="status" className="flex items-center gap-2 text-small text-stone-600">
        <Spinner size="sm" />
        Loading the data notice…
      </p>
    );
  }
  // A wrong shape is treated as a failed read (CODING_STANDARDS F1).
  if (read.status !== "ready" || !notice || typeof notice.text !== "string") {
    return (
      <div className="space-y-2 text-small text-stone-700">
        <p role="alert">The data notice didn&apos;t load. Check your connection, then try again.</p>
        <button type="button" onClick={read.retry} className="font-semibold text-brand underline underline-offset-4">
          Try again
        </button>
      </div>
    );
  }
  return <NoticeText notice={notice} headingLevel={3} />;
}
