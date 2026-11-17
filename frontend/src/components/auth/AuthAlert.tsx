import type { ReactNode, Ref } from "react";

export type AuthAlertVariant = "error" | "warning";

interface AuthAlertProps {
  readonly variant: AuthAlertVariant;
  readonly title: string;
  readonly children: ReactNode;
  /**
   * Given, the alert can take focus, so a screen can move focus to it as an
   * error summary (IR-642, ADR-045 §7). Without it, nothing changes.
   */
  readonly focusRef?: Ref<HTMLDivElement>;
}

// Errors stop the sign-in, so they take solid maroon; a warning is soft maroon
// (IR-359). Why a session ended is a dialog now (SessionNoticeDialog, IR-1197). The glyph and the title carry the meaning.
function AlertIcon({ variant }: { variant: AuthAlertVariant }) {
  const bg =
    variant === "warning" ? "bg-stone-100 text-brand" : "bg-brand text-white";

  return (
    <span
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-heading font-bold ${bg}`}
      aria-hidden
    >
      !
    </span>
  );
}

export function AuthAlert({ variant, title, children, focusRef }: AuthAlertProps) {
  return (
    <div
      ref={focusRef}
      tabIndex={focusRef ? -1 : undefined}
      className="relative mb-6 rounded-control border border-stone-300 bg-surface px-4 py-3 text-brand"
      role="alert"
    >
      <div className="flex gap-3">
        <AlertIcon variant={variant} />
        <div className="min-w-0 flex-1">
          <p className="text-body font-bold">{title}</p>
          <div className="mt-1 text-body leading-relaxed">{children}</div>
        </div>
      </div>
    </div>
  );
}
