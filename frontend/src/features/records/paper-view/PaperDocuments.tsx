import { Link } from "react-router-dom";
import type { RecordFileItem } from "@/types/records";
import { formatDate } from "@/lib/utils";

/** Human-readable file size. Bytes come straight from documents.RecordUpload. */
function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

interface PaperDocumentsProps {
  recordId: number;
  files: RecordFileItem[];
}

/**
 * Attachments on the record.
 *
 * A file whose `url` is null is listed but not linked: the backend withholds
 * the URL when the viewer may not fetch it, and the rail must not imply a
 * download it cannot serve.
 */
export function PaperDocuments({ recordId, files }: PaperDocumentsProps) {
  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400">
          Documents
        </h2>
        <span className="min-w-[1.25rem] px-1.5 h-5 rounded-md bg-stone-100 text-stone-500 text-[11px] font-bold flex items-center justify-center">
          {files.length}
        </span>
      </div>

      {files.length === 0 ? (
        <p className="text-[12px] text-stone-500">
          No documents attached to this record yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {files.map((file) => {
            const inner = (
              <>
                <span className="w-8 h-8 rounded-lg bg-brand-50 text-brand flex items-center justify-center shrink-0">
                  <i className="fas fa-file-lines text-[12px]" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] font-semibold text-stone-800 truncate">
                    {file.filename}
                  </span>
                  <span className="block text-[11px] text-stone-400">
                    {formatBytes(file.size_bytes)} · {formatDate(file.created_at, "d MMM")}
                  </span>
                </span>
                {file.url ? (
                  <i className="fas fa-download text-[11px] text-stone-400 shrink-0" aria-hidden />
                ) : (
                  <i
                    className="fas fa-lock text-[11px] text-stone-300 shrink-0"
                    title="You do not have access to download this file" aria-hidden />
                )}
              </>
            );

            return (
              <li key={file.id}>
                {file.url ? (
                  <a
                    href={file.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2.5 rounded-xl border border-stone-200 px-2.5 py-2 hover:border-brand/30 hover:bg-stone-50 transition-colors"
                  >
                    {inner}
                  </a>
                ) : (
                  <div className="flex items-center gap-2.5 rounded-xl border border-stone-200 px-2.5 py-2 opacity-70">
                    {inner}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Link
        to={`/records/${recordId}/documents`}
        className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-semibold text-brand hover:underline"
      >
        Manage documents
        <i className="fas fa-arrow-right text-[9px]" aria-hidden />
      </Link>
    </section>
  );
}
