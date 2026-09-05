import { useId, useState } from "react";
import { DPA_SECTIONS, DPA_CHECKBOX_LABEL } from "@/lib/dpaTerms";

interface DpaConsentInlineProps {
  accepted: boolean;
  onAcceptedChange: (value: boolean) => void;
}

/**
 * Step 3 consent (FR-M6-02) — full text expands in place.
 *
 * The mockup's own sidebar note is explicit: "Full text is readable in place,
 * not a click-through." A modal the user can dismiss without opening is
 * exactly the click-through docs/ui-ux/05-submission.md's accessibility
 * section rules out ("never a click-through the user cannot read"), so this
 * replaces `DpaConsentGate`'s modal-link pattern with an inline <details>
 * disclosure — reachable by keyboard, no separate dialog to manage focus for.
 */
export function DpaConsentInline({ accepted, onAcceptedChange }: DpaConsentInlineProps) {
  const [expanded, setExpanded] = useState(false);
  const textId = useId();

  return (
    <section className="rounded-xl border border-brand-200 bg-brand-50/40 p-4">
      <div className="flex items-start gap-2.5 mb-3">
        <i className="fas fa-scale-balanced text-brand text-[14px] mt-0.5" aria-hidden />
        <div>
          <h3 className="text-[13px] font-bold text-stone-900">
            Institutional Consent &amp; Compliance Statements
          </h3>
          <p className="text-[12px] text-stone-500 mt-0.5">
            Data Privacy &amp; Research Integrity Agreement — RA 10173.
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={textId}
        className="mb-3 flex items-center gap-1.5 text-[12px] font-semibold text-brand hover:underline"
      >
        <i className={`fas fa-chevron-${expanded ? "up" : "down"} text-[10px]`} aria-hidden />
        {expanded ? "Hide full DPA terms" : "View DPA terms · expand"}
      </button>

      {expanded && (
        <div
          id={textId}
          className="mb-3 max-h-64 overflow-y-auto rounded-lg border border-stone-200 bg-white p-3.5 text-[12px] text-stone-600 leading-relaxed space-y-3"
        >
          {DPA_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="font-semibold text-stone-800">{section.title}</p>
              {"body" in section && section.body && <p className="mt-0.5">{section.body}</p>}
              {"list" in section && section.list && (
                <ul className="mt-1 list-disc pl-5 space-y-0.5">
                  {section.list.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      <label className="flex items-start gap-3 cursor-pointer group">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => onAcceptedChange(e.target.checked)}
          aria-describedby={`${textId}-label`}
          className="mt-0.5 w-4 h-4 rounded border-stone-300 text-brand focus:ring-brand cursor-pointer"
        />
        <span id={`${textId}-label`} className="text-[12px] text-stone-700 leading-relaxed group-hover:text-stone-900">
          {DPA_CHECKBOX_LABEL}
        </span>
      </label>
    </section>
  );
}
