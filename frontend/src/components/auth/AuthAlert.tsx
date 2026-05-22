import type { ReactNode } from "react";

export type AuthAlertVariant = "error" | "session" | "warning";

interface AuthAlertProps {
  readonly variant: AuthAlertVariant;
  readonly title: string;
  readonly children: ReactNode;
  readonly onDismiss?: () => void;
}

function AlertIcon({ variant }: { variant: AuthAlertVariant }) {
  const bg =
    variant === "session" ? "bg-red-100 text-red-600" : "bg-red-100 text-brand";

  return (
    <span
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[15px] font-bold ${bg}`}
      aria-hidden
    >
      !
    </span>
  );
}

export function AuthAlert({ variant, title, children, onDismiss }: AuthAlertProps) {
  return (
    <div
      className="relative mb-6 rounded-lg border border-brand/25 bg-red-50 px-4 py-3 text-brand"
      role="alert"
    >
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="absolute top-3 right-3 text-brand/50 hover:text-brand text-[20px] leading-none"
          aria-label="Dismiss"
        >
          ×
        </button>
      )}
      <div className="flex gap-3 pr-6">
        <AlertIcon variant={variant} />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-bold">{title}</p>
          <div className="mt-1 text-[13px] leading-relaxed">{children}</div>
        </div>
      </div>
    </div>
  );
}
