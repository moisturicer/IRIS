/**
 * Reads a `text/event-stream` body (IR-329). Not `EventSource` -- that's
 * GET-only and can't carry the `Authorization` header this stream needs.
 */

export interface SSEEvent {
  event: string;
  data: unknown;
}

function parseBlock(block: string): SSEEvent | null {
  let name: string | null = null;
  let data: string | null = null;
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data = line.slice("data:".length).trim();
    }
  }
  if (!name) return null;
  return { event: name, data: data ? JSON.parse(data) : null };
}

/**
 * Yields one `SSEEvent` per record. Buffers by `\n\n` rather than per
 * network chunk -- a record can arrive split across two reads.
 */
export async function* readSSE(response: Response): AsyncGenerator<SSEEvent> {
  const body = response.body;
  if (!body) return;

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separator;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const parsed = parseBlock(block);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
