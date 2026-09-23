/**
 * Reading Ask IRIS's SSE wire format (IR-329) -- the frontend half of the
 * shape `apps/ai/views/chatbot.py`'s `_sse` emits and
 * `test_ask_stream_http.py`'s `_parse_sse` already asserts server-side.
 */
import { describe, expect, it } from "vitest";
import { readSSE } from "./sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(response: Response) {
  const events = [];
  for await (const event of readSSE(response)) events.push(event);
  return events;
}

describe("reading Ask IRIS's event stream", () => {
  it("parses one event per record", async () => {
    const response = new Response(
      streamOf(
        'event: retrieval_started\ndata: {}\n\n' +
          'event: text_delta\ndata: {"text": "Rainfall "}\n\n' +
          'event: done\ndata: {"answer": "Rainfall gauges."}\n\n',
      ),
    );

    const events = await collect(response);

    expect(events).toEqual([
      { event: "retrieval_started", data: {} },
      { event: "text_delta", data: { text: "Rainfall " } },
      { event: "done", data: { answer: "Rainfall gauges." } },
    ]);
  });

  it("reassembles a record split across two network chunks", async () => {
    const response = new Response(
      streamOf('event: text_delta\ndata: {"te', 'xt": "gauges"}\n\n'),
    );

    const events = await collect(response);

    expect(events).toEqual([{ event: "text_delta", data: { text: "gauges" } }]);
  });

  it("yields nothing for a body with no events", async () => {
    const response = new Response(streamOf(""));

    expect(await collect(response)).toEqual([]);
  });

  it("yields nothing when the response carries no body", async () => {
    const response = new Response(null);

    expect(await collect(response)).toEqual([]);
  });
});
