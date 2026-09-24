/**
 * The server's refusal, `{"detail": "..."}`, or `fallback` when there is none.
 * Every document-request route answers a refusal in that one shape.
 */
export function errorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
  );
}
