import { useState } from "react";

import { recordsApi } from "@/api/records";
import { cn } from "@/lib/utils";
import type { IpType, RecordDetail } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";

/**
 * IP classification tagger, offered on Paper View's Overview under the
 * `tag_ip` capability. Moved out of the page unchanged (IR-1267).
 */

const IP_TYPE_OPTIONS: Exclude<IpType, "">[] = [
  "patent",
  "copyright",
  "trade_secret",
  "utility_model",
];

interface IpTaggerProps {
  recordId: number;
  currentIpType: IpType;
  onSaved: (updated: RecordDetail) => void;
}

export function IpTagger({ recordId, currentIpType, onSaved }: IpTaggerProps) {
  const [selected, setSelected] = useState<IpType>(currentIpType);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty = selected !== currentIpType;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const { data } = await recordsApi.updateTags(recordId, { ip_type: selected });
      onSaved(data as RecordDetail);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="bg-white border border-stone-200 rounded-card p-5">
      <h2 className="text-heading font-semibold text-stone-900 mb-1">IP classification</h2>
      <p className="text-xs text-stone-500 mb-3">
        Office staff only. Sets the structured IP type recorded against this disclosure.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {IP_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt}
            type="button"
            aria-pressed={selected === opt}
            onClick={() => setSelected(opt === selected ? "" : opt)}
            className={cn(
              "min-h-11 reading-split:min-h-9 px-3 rounded-full text-xs font-semibold border transition-colors",
              selected === opt
                ? "bg-brand text-white border-brand"
                : "bg-white text-stone-600 border-stone-200 hover:border-brand/40",
            )}
          >
            {IP_TYPE_LABELS[opt]}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="min-h-11 reading-split:min-h-9 px-3 rounded-control bg-brand text-white text-xs font-bold hover:bg-brand-light disabled:opacity-40 transition-colors"
        >
          {saving ? "Saving…" : "Save classification"}
        </button>
        {saved && <span className="text-xs font-semibold text-stone-900">Saved</span>}
        {error && <span className="text-xs text-brand">{error}</span>}
      </div>
    </section>
  );
}
