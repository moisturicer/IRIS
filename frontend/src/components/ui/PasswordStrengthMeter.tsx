import { passwordStrength } from "@/lib/passwordPolicy";

/**
 * How hard the password being typed looks to guess (IR-819, ASVS 2.1.8).
 *
 * Four segments for sight, and the same thing in words for everyone: the
 * segments are decoration, so the label carries the meaning whether or not
 * colour is seen. The label is a polite live region, so a screen reader hears
 * it change without losing its place. It guides only; the server decides.
 * Shows nothing until something is typed.
 */
export function PasswordStrengthMeter({ password }: { password: string }) {
  if (!password) return null;
  const { score, label } = passwordStrength(password);
  return (
    <div className="mt-2">
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4].map((segment) => (
          <span
            key={segment}
            className={`h-1 flex-1 rounded-full ${segment <= score ? "bg-stone-800" : "bg-stone-200"}`}
          />
        ))}
      </div>
      <p className="mt-1 text-small text-stone-600" aria-live="polite">
        Password strength: {label}
      </p>
    </div>
  );
}
