/**
 * The pieces every Settings & Profile panel is built from, shared so the
 * profile fields (IR-699) look like the panels already there.
 */
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A titled panel. Named by its title, so each one is a landmark region. */
export function Panel({
  title, caption, children,
}: { title: string; caption: string; children: ReactNode }) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="bg-white rounded-xl border border-stone-200 p-5 sm:p-6">
      <h2 id={titleId} className="text-[12px] font-bold uppercase tracking-wider text-stone-500">{title}</h2>
      <p className="text-[13px] text-stone-500 mt-1">{caption}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function Field({
  label, children, hint,
}: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[12px] font-bold uppercase tracking-wider text-stone-500 mb-1.5">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[12px] text-stone-500 mt-1.5">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full px-3 py-2 rounded-lg border border-stone-200 text-[14px] text-stone-900 " +
  "focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/40";

export const readOnlyClass =
  "w-full px-3 py-2 rounded-lg border border-stone-200 bg-stone-50 text-[14px] text-stone-500";

export const secondaryButtonClass =
  "px-3.5 py-2 rounded-lg text-[13px] font-semibold text-stone-600 " +
  "border border-stone-200 hover:bg-stone-50 disabled:opacity-40";

export const primaryButtonClass =
  "px-4 py-2 rounded-lg text-[13px] font-bold uppercase tracking-wider " +
  "bg-brand text-white hover:bg-brand-light disabled:opacity-40";

export function Notice({ tone, children }: { tone: "ok" | "error"; children: ReactNode }) {
  return (
    <p
      role="status"
      className={cn(
        "text-[13px] rounded-lg px-3 py-2 border",
        tone === "ok"
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : "bg-red-50 text-red-700 border-red-200",
      )}
    >
      {children}
    </p>
  );
}
