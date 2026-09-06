import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { useUIStore } from "@/store/ui.store";
import {
  DPA_REGISTRY_SUBTITLE,
  DPA_REGISTRY_TITLE,
  DPA_SECTIONS,
  DPA_TERMS_PLAIN_TEXT,
} from "@/lib/dpaTerms";

interface DpaConsentModalProps {
  open:    boolean;
  onClose: () => void;
}

export function DpaConsentModal({ open, onClose }: DpaConsentModalProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [copying, setCopying] = useState(false);

  const handleCopy = async () => {
    setCopying(true);
    try {
      await navigator.clipboard.writeText(DPA_TERMS_PLAIN_TEXT);
      addToast({ type: "success", message: "Terms copied to clipboard." });
    } catch {
      addToast({ type: "error", message: "Could not copy. Select and copy manually." });
    } finally {
      setCopying(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} size="max-w-2xl">
      <div className="-m-5 flex flex-col max-h-[min(85vh,720px)]">
        <div className="shrink-0 px-5 pt-5 pb-4 border-b border-gray-200">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[#6B0F12]">
                {DPA_REGISTRY_TITLE}
              </p>
              <h2 className="text-[15px] font-bold text-gray-900 mt-1 leading-snug">
                {DPA_REGISTRY_SUBTITLE}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-600 shrink-0"
              aria-label="Close"
            >
              <i className="fa fa-times text-[14px]" aria-hidden />
            </button>
          </div>
          <button
            type="button"
            onClick={handleCopy}
            disabled={copying}
            className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200
              text-[12px] font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <i className="fas fa-copy text-[11px]" aria-hidden />
            {copying ? "Copying…" : "Copy content"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-4 space-y-5">
          {DPA_SECTIONS.map((section) => (
            <section key={section.title}>
              <h3 className="text-[13px] font-bold text-gray-900">{section.title}</h3>
              {"body" in section && section.body && (
                <p className="text-[12px] text-gray-600 leading-relaxed mt-1.5">{section.body}</p>
              )}
              {"list" in section && section.list && (
                <ul className="mt-2 space-y-2">
                  {section.list.map((item) => (
                    <li
                      key={item.slice(0, 40)}
                      className="text-[12px] text-gray-600 leading-relaxed pl-3 border-l-2 border-[#6B0F12]/20"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        <div className="shrink-0 px-5 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2.5 rounded-lg bg-[#6B0F12] text-white text-[13px] font-semibold hover:bg-[#7d1215]"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
