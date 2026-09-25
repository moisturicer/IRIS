import type { ReactNode } from "react";

/**
 * A wizard field's error, beside the field (IR-360). Maroon like `Input`'s own
 * error (IR-359), with a glyph so it is not carried by colour alone: maroon is
 * also the brand. The glyph is aria-hidden, so a field that points here with
 * aria-describedby is still described by the sentence only.
 */
export function FieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="flex items-start gap-1.5 text-[12px] text-brand mt-1">
      <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
      {children}
    </p>
  );
}
