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

/**
 * The server's messages for one field of a refused form (DRF's
 * `{field: ["message", ...]}`), joined, or `null` when it named none.
 */
export function fieldError(err: unknown, field: string): string | null {
  const messages = (err as { response?: { data?: Record<string, unknown> } } | null)?.response?.data?.[field];
  if (typeof messages === "string") return messages;
  if (Array.isArray(messages)) {
    const text = messages.filter((m): m is string => typeof m === "string").join(" ");
    return text || null;
  }
  return null;
}
