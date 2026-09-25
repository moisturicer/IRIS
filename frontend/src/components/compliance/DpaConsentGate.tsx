import { DPA_CHECKBOX_LABEL } from "@/lib/dpaTerms";

interface DpaConsentGateProps {
  accepted:       boolean;
  onAcceptedChange: (value: boolean) => void;
  onViewTerms:      () => void;
}

/**
 * Step 3 consent checkbox (FR-M6-02). Parent must disable Submit until accepted is true.
 */
export function DpaConsentGate({ accepted, onAcceptedChange, onViewTerms }: DpaConsentGateProps) {
  return (
    <div className="mt-6 rounded-xl border border-brand/20 bg-brand-50/50 p-4">
      <div className="flex items-start gap-2 mb-3">
        <i className="fas fa-shield-halved text-brand text-[14px] mt-0.5" aria-hidden />
        <div>
          <p className="text-[13px] font-semibold text-stone-900">Data privacy consent required</p>
          <p className="text-[12px] text-stone-500 mt-0.5">
            Review RA 10173 terms before submitting your disclosure.
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={onViewTerms}
        className="mb-3 text-[12px] font-semibold text-brand hover:underline"
      >
        Read full DPA terms →
      </button>

      <label className="flex items-start gap-3 cursor-pointer group">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => onAcceptedChange(e.target.checked)}
          className="mt-1 w-4 h-4 rounded border-stone-300 text-brand focus:ring-brand cursor-pointer"
        />
        <span className="text-[12px] text-stone-700 leading-relaxed group-hover:text-stone-900">
          {DPA_CHECKBOX_LABEL}
        </span>
      </label>

      {!accepted && (
        <p className="flex items-start gap-1.5 text-[11px] text-brand mt-2 pl-7">
          <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
          You must accept the terms before you can submit this record.
        </p>
      )}
    </div>
  );
}
