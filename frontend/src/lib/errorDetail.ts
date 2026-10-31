/** The server's refusal, with an actionable wait for HTTP rate limits. */
export function errorDetail(err: unknown, fallback: string): string {
  const response = (err as { response?: {
    status?: number;
    headers?: Record<string, unknown>;
    data?: { detail?: unknown };
  } } | null)?.response;
  const detail = response?.data?.detail;
  if (response?.status === 429) {
    const header = response.headers?.["retry-after"] ?? response.headers?.["Retry-After"];
    let seconds = typeof header === "string" || typeof header === "number" ? Number(header) : NaN;
    if (!Number.isFinite(seconds) || seconds <= 0) {
      const match = typeof detail === "string" ? /available in (\d+(?:\.\d+)?) seconds?/i.exec(detail) : null;
      seconds = match ? Number(match[1]) : NaN;
    }
    if (Number.isFinite(seconds) && seconds > 0) {
      const unit = seconds < 60 ? "second" : seconds < 3600 ? "minute" : "hour";
      const count = Math.ceil(seconds / (unit === "second" ? 1 : unit === "minute" ? 60 : 3600));
      return `Too many requests — try again in about ${count} ${unit}${count === 1 ? "" : "s"}.`;
    }
    return "Too many requests — try again later.";
  }
  return typeof detail === "string" && detail.trim() ? detail : fallback;
}

/** Every string inside a DRF error value: a message, a list, or a list's per-item object. */
function messagesIn(value: unknown): string[] {
  if (typeof value === "string") return value.trim() ? [value] : [];
  if (Array.isArray(value)) return value.flatMap(messagesIn);
  if (value && typeof value === "object") return Object.values(value).flatMap(messagesIn);
  return [];
}

/**
 * The server's messages for the named fields of a refused form (DRF's
 * `{field: ["message", ...]}`), in field order and joined, or `null` when it
 * named none of them. A list field's per-item errors (`{"0": [...]}`) count.
 */
export function fieldError(err: unknown, ...fields: string[]): string | null {
  const data = (err as { response?: { data?: Record<string, unknown> } } | null)?.response?.data;
  if (!data || typeof data !== "object") return null;
  const text = fields.flatMap((field) => messagesIn(data[field])).join(" ");
  return text || null;
}
