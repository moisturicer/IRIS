import { useMemo, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import type { RecordListItem } from "@/types/records";
import { buildCitation, CITATION_STYLES, type CitationStyle } from "./discoverUtils";
import { cn } from "@/lib/utils";

interface PaperCiteModalProps {
  record: RecordListItem | null;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Citation builder. Every string is derived from the record's own fields —
 * authors, title and year — so nothing here depends on metadata IRIS does not
 * actually store.
 */
export function PaperCiteModal({ record, isOpen, onClose }: PaperCiteModalProps) {
  const [style, setStyle] = useState<CitationStyle>("APA");
  const [copied, setCopied] = useState(false);

  const citation = useMemo(
    () => (record ? buildCitation(record, style) : ""),
    [record, style],
  );

  if (!record) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(citation);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Modal open={isOpen} onClose={onClose} title="Cite this paper" size="max-w-2xl">
      <div className="space-y-4">
        <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">
          <span className="font-semibold text-slate-700">{record.title}</span>
        </p>

        {/* Style switcher */}
        <div className="flex items-center gap-1.5">
          {CITATION_STYLES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setStyle(option)}
              className={cn(
                "px-3 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer",
                style === option
                  ? "bg-brand text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200/70",
              )}
            >
              {option}
            </button>
          ))}
        </div>

        {/* Citation body */}
        <pre className="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-800 whitespace-pre-wrap break-words font-mono leading-relaxed max-h-64 overflow-y-auto">
          {citation}
        </pre>

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-slate-400">
            Generated from the record&apos;s authors, title and year.
          </p>
          <button
            type="button"
            onClick={handleCopy}
            className="px-4 py-2 rounded-xl bg-brand hover:bg-brand-light text-white text-xs font-bold transition flex items-center gap-1.5 shrink-0"
          >
            <i className={cn("fas text-[10px]", copied ? "fa-check" : "fa-copy")} aria-hidden />
            <span>{copied ? "Copied" : "Copy citation"}</span>
          </button>
        </div>
      </div>
    </Modal>
  );
}
