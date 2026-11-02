/**
 * The ORCID iD check Settings runs as you type (IR-699).
 *
 * The server is the authority (IR-695 refuses an invalid iD with its own
 * message); this only lets the person see a typo before they save. An iD is
 * four groups of four separated by hyphens, the last character a digit or X,
 * and that last character is an ISO 7064 Mod 11-2 check over the other 15.
 */

const FORMAT = /^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$/;

export const ORCID_EXAMPLE = "0000-0002-1825-0097";

/** Why `value` is not a usable ORCID iD, or `null` when it is (or is empty). */
export function orcidProblem(value: string): string | null {
  const id = value.trim();
  if (!id) return null;
  if (!FORMAT.test(id)) return `Enter an ORCID iD like ${ORCID_EXAMPLE}.`;

  const digits = id.replace(/-/g, "");
  let total = 0;
  for (const ch of digits.slice(0, 15)) total = (total + Number(ch)) * 2;
  const result = (12 - (total % 11)) % 11;
  const expected = result === 10 ? "X" : String(result);

  return digits[15].toUpperCase() === expected
    ? null
    : "This ORCID iD doesn't check out — look for a mistyped digit.";
}
