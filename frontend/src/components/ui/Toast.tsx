import { useUIStore } from "@/store/ui.store";

const ICON: Record<string, string> = {
  success: "fa-check-circle text-green-500",
  error:   "fa-times-circle text-red-500",
  info:    "fa-info-circle text-blue-500",
};

const BG: Record<string, string> = {
  success: "border-green-200 bg-green-50",
  error:   "border-red-200 bg-red-50",
  info:    "border-blue-200 bg-blue-50",
};

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore();

  return (
    <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-3 w-80 rounded-xl border px-4 py-3 shadow-lg
            text-[13px] text-gray-800 ${BG[t.type]}`}
        >
          <i className={`fa ${ICON[t.type]} mt-0.5 shrink-0`} aria-hidden />
          <p className="flex-1">{t.message}</p>
          <button
            onClick={() => removeToast(t.id)}
            className="text-gray-500 hover:text-gray-600 shrink-0"
            aria-label="Dismiss"
          >
            <i className="fa fa-times text-[12px]" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
