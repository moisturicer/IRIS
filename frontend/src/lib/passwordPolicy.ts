/**
 * The password rules the server enforces (IR-819, ASVS 2.1.1/2.1.2/2.1.7), as
 * the forms mirror them. `AUTH_PASSWORD_VALIDATORS` in the backend is the
 * authority: these only let a form say so before it submits. Whether a
 * password is common or has appeared in a breach is the server's to decide,
 * and its refusal is shown verbatim.
 */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

export const PASSWORD_POLICY =
  `At least ${PASSWORD_MIN_LENGTH} characters, and not a common, breached or all-numeric password. Spaces count.`;

/** The form-side length check, or `undefined` when the length is fine. */
export function passwordLengthError(password: string, field = "Password"): string | undefined {
  // Characters as the server counts them (code points), so an emoji is one.
  const length = [...password].length;
  if (length < PASSWORD_MIN_LENGTH) return `${field} must be at least ${PASSWORD_MIN_LENGTH} characters.`;
  if (length > PASSWORD_MAX_LENGTH) return `${field} must be at most ${PASSWORD_MAX_LENGTH} characters.`;
  return undefined;
}

export type PasswordStrength = {
  /** 0 = below the minimum, then 1 (weak) to 4 (strong). */
  score: 0 | 1 | 2 | 3 | 4;
  label: "Too short" | "Weak" | "Fair" | "Good" | "Strong";
};

const LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"] as const;

/**
 * A rough guide to how hard a password is to guess, for the strength meter.
 *
 * Length counts most, then the mix of letters, digits and symbols. A password
 * made of one repeated character or a single run like "abcdef…" or "123456…"
 * is weak whatever its length. This is guidance only: it can call a password
 * strong that the server still refuses as breached, and the refusal wins.
 */
export function passwordStrength(password: string): PasswordStrength {
  const length = [...password].length;
  if (length < PASSWORD_MIN_LENGTH) return { score: 0, label: LABELS[0] };

  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z\d]/].filter((kind) => kind.test(password)).length;
  let score = 1;
  if (length >= 16) score += 1;
  if (length >= 20) score += 1;
  if (kinds >= 3) score += 1;
  if (kinds === 4 && length >= 14) score += 1;

  if (/^(.)\1*$/.test(password) || isOneRun(password.toLowerCase())) score = 1;
  const capped = Math.min(4, score) as PasswordStrength["score"];
  return { score: capped, label: LABELS[capped] };
}

function isOneRun(text: string): boolean {
  if (text.length < 3) return false;
  const step = text.charCodeAt(1) - text.charCodeAt(0);
  if (Math.abs(step) !== 1) return false;
  for (let i = 2; i < text.length; i += 1) {
    if (text.charCodeAt(i) - text.charCodeAt(i - 1) !== step) return false;
  }
  return true;
}
