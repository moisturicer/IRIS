/**
 * Reference lists, fetched once per session (IR-1249).
 *
 * Classifications, PSCED codes, record types and colleges change only when an
 * administrator edits them in Django admin, yet every visit to Discover asked
 * for them again, and for classifications twice. `once` shares one request
 * among every caller in the session:
 *
 *  - callers asking at the same moment share the request in flight;
 *  - a failure is not kept, so the next caller asks again;
 *  - each caller gets its own copy of the data, so one screen sorting a list
 *    cannot reorder another's;
 *  - sign-out forgets every list (`auth.store` logout), so another account
 *    never reads the last one's.
 *
 * A list an administrator edits mid-session shows on the next reload. Setup
 * cannot change any of these: the public record-type list is id and name, and
 * Setup edits descriptions, templates and requirements through its own endpoint.
 */
import type { AxiosResponse } from "axios";

const kept = new Map<string, Promise<AxiosResponse>>();

export function once<T>(key: string, load: () => Promise<AxiosResponse<T>>): Promise<AxiosResponse<T>> {
  let shared = kept.get(key) as Promise<AxiosResponse<T>> | undefined;
  if (!shared) {
    shared = load();
    kept.set(key, shared);
    shared.catch(() => {
      if (kept.get(key) === shared) kept.delete(key);
    });
  }
  return shared.then((response) => ({ ...response, data: structuredClone(response.data) }));
}

/** Forget every kept list: on sign-out, and between tests. */
export function forgetReferenceLists(): void {
  kept.clear();
}
