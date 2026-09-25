import { TONES } from "@/components/ui/statusTones";
import { useUIStore, type Toast } from "@/store/ui.store";

type Kind = Toast["type"];

// A kind is carried three ways (IR-359): its tone, its glyph, and a word a
// screen reader hears before the message. Success and error are both dark in
// this palette, so the tone alone would not tell them apart.
const KIND: Record<Kind, { tone: string; icon: string; word: string; dismiss: string }> = {
  success: {
    tone: TONES.settled, icon: "fa-circle-check", word: "Success:",
    dismiss: "text-white/70 hover:text-white",
  },
  error: {
    tone: TONES.attention, icon: "fa-circle-xmark", word: "Error:",
    dismiss: "text-white/70 hover:text-white",
  },
  info: {
    tone: TONES.quiet, icon: "fa-circle-info", word: "Notice:",
    dismiss: "text-stone-600 hover:text-stone-900",
  },
};

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore();

  return (
    <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => {
        const kind = KIND[t.type];
        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 w-80 rounded-xl px-4 py-3 shadow-lg
              text-[13px] ${kind.tone}`}
          >
            <i className={`fa ${kind.icon} mt-0.5 shrink-0`} aria-hidden />
            <span className="sr-only">{kind.word}</span>
            <p className="flex-1">{t.message}</p>
            <button
              onClick={() => removeToast(t.id)}
              className={`shrink-0 ${kind.dismiss}`}
              aria-label="Dismiss"
            >
              <i className="fa fa-times text-[12px]" aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
