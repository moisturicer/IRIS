import { formatDate } from "@/lib/utils";
import type { DataNotice } from "@/types/notice";

/**
 * The one way IRIS shows a data notice (IR-800): the server's `text` as plain
 * text, every line break kept, no markup, no links. React escapes it, so an
 * angle bracket or an address is shown as the characters it is. A draft has
 * no date yet, which is how the Notices page previews one.
 */
export function NoticeText({
  notice, headingLevel = 2,
}: {
  notice: Pick<DataNotice, "version" | "text"> & { published_at: string | null };
  headingLevel?: 2 | 3;
}) {
  const Heading = `h${headingLevel}` as "h2";
  return (
    <div className="space-y-3 text-small text-stone-700">
      <div>
        <Heading className="text-body font-bold text-stone-900">Data notice</Heading>
        <p className="mt-1 text-label text-stone-500">
          {notice.published_at
            ? `Version ${notice.version} · published ${formatDate(notice.published_at)}`
            : `Version ${notice.version} · not published yet`}
        </p>
      </div>
      <p className="whitespace-pre-wrap break-words leading-relaxed">{notice.text}</p>
    </div>
  );
}
