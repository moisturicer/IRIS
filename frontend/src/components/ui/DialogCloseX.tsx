interface DialogCloseXProps {
  readonly onClose: () => void;
}

/**
 * The X in a centred dialog's top-right corner, which closes it (IR-1327).
 * It looks like `Modal`'s X and has the same 44px target. Its accessible name
 * is "Close", so a screen reader still says what it does. The dialog's panel
 * must be `relative`, as every dialog panel here already is.
 *
 * The X is drawn inline, not with Font Awesome's `fa-times`: that font comes
 * from a CDN, and if it fails to load the dialog's only close control would
 * be invisible.
 */
export function DialogCloseX({ onClose }: DialogCloseXProps) {
  return (
    <button
      type="button"
      onClick={onClose}
      className="absolute right-2 top-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-control p-1 text-stone-500 hover:bg-stone-100 hover:text-stone-700"
      aria-label="Close"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden focusable={false}>
        <path d="M6 6l12 12M18 6L6 18" />
      </svg>
    </button>
  );
}
