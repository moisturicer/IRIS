import type { ResponseStyle } from "@/types/ai";

interface ResponseStyleSelectProps {
  value:       ResponseStyle;
  onChange:    (style: ResponseStyle) => void;
  disabled?:   boolean;
}

const OPTIONS: { value: ResponseStyle; label: string }[] = [
  { value: "concise",  label: "Concise" },
  { value: "balanced", label: "Balanced" },
  { value: "thorough", label: "Thorough" },
];

/** How long and structured the next answer should be (IR-332) -- a native
 *  `<select>` rather than a custom dropdown, so it comes with keyboard and
 *  screen-reader support for free. */
export function ResponseStyleSelect({ value, onChange, disabled }: ResponseStyleSelectProps) {
  return (
    <div className="relative shrink-0">
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as ResponseStyle)}
        aria-label="Answer style"
        className="appearance-none rounded-full border border-stone-200 bg-stone-50/80 pl-3.5 pr-8 py-2
          text-[12px] font-medium text-stone-600 outline-none cursor-pointer
          hover:border-stone-300 focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]
          disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <i
        className="fas fa-chevron-down text-[9px] text-stone-400 pointer-events-none absolute right-3 top-1/2 -translate-y-1/2"
        aria-hidden
      />
    </div>
  );
}
