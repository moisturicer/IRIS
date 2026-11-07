import { useCallback, useEffect, useState, type DependencyList } from "react";

import { isRequestTimeout } from "@/api/requestPolicy";

/**
 * - `loading`: a read is in flight.
 * - `ready`: `data` is the answer to the current inputs.
 * - `interrupted`: the request got no answer in time. Nothing is known about
 *   the server, so the screen offers `retry` rather than a refusal (IR-914).
 * - `failed`: the server or the network answered with an error; `error` has it.
 */
export type ApiReadStatus = "loading" | "ready" | "interrupted" | "failed";

export interface ApiRead<T> {
  status: ApiReadStatus;
  data: T | undefined;
  error: unknown;
  /** Read again. The only way a read is ever repeated (see `api/requestPolicy.ts`). */
  retry: () => void;
}

type Settled<T> = Omit<ApiRead<T>, "retry">;

const LOADING = { status: "loading", data: undefined, error: undefined } as const;

/**
 * A list or detail read tied to the life of a screen (IR-914, ADR-061).
 *
 * `read` gets an `AbortSignal` to pass to the API call; the signal is aborted
 * when the screen unmounts and when `deps` change, so a slow earlier request is
 * cancelled and **a stale response never replaces a newer one**. The second
 * guarantee does not rely on the API call honouring the signal: a response that
 * arrives after its read was cancelled is dropped here.
 *
 * `deps` are the read's inputs, as for `useEffect`; `read` itself is not a
 * dependency, so an inline arrow does not re-read on every render.
 *
 * It never repeats a read by itself. A timeout becomes `interrupted` and the
 * reader chooses `retry`.
 */
export function useApiRead<T>(
  read: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
): ApiRead<T> {
  const [state, setState] = useState<Settled<T>>(LOADING);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState(LOADING);

    // Wrapped so a read that throws before it returns a promise fails like any other.
    new Promise<T>((resolve) => resolve(read(controller.signal))).then(
      (data) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", data, error: undefined });
      },
      (error: unknown) => {
        // A read this hook cancelled is not a failure; its screen has moved on.
        if (controller.signal.aborted) return;
        setState({
          status: isRequestTimeout(error) ? "interrupted" : "failed",
          data: undefined,
          error,
        });
      },
    );

    return () => controller.abort();
    // `read` is deliberately not a dependency; `deps` are its inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { ...state, retry };
}
