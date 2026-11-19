import axios from "axios";
import { IDLE_HEADER, idleSeconds } from "@/lib/activity";
import { API_BASE } from "@/lib/constants";
import { FIRST_PARTY, type RefreshedTokens } from "@/lib/tokenRefresh";
import { DEFAULT_TIMEOUT_MS } from "./requestPolicy";

/**
 * Ask the server for a new access token (ADR-072). The one refresh request,
 * used by page load (`hydrateAuth`) and by `apiClient`'s 401 handler.
 *
 * The refresh token is in an HttpOnly cookie the browser sends by itself, so
 * the body is empty and the request says it comes from IRIS (`FIRST_PARTY`).
 * The server sets the rotated token in the same cookie.
 *
 * **Bare `axios`, never `apiClient`.** Through the instance, a 401 here would
 * reach the 401 handler, which starts a refresh of its own and waits on the
 * shared gate this request is holding -- a deadlock that leaves page load on
 * the spinner. A signed-out visitor's load is exactly that 401 (`no_session`).
 */
export async function requestNewTokens(): Promise<RefreshedTokens> {
  // The idle header here too: this refresh is usually caused by a poll's 401,
  // and counting it as activity would hand the poll the session back.
  const { data } = await axios.post(
    `${API_BASE}/auth/token/refresh/`,
    {},
    // A refresh that never answers would leave every 401'd request waiting on
    // it, so it carries the same timeout (IR-914). A timeout here ends the
    // session like any other failed refresh.
    {
      headers: { [IDLE_HEADER]: String(idleSeconds()), ...FIRST_PARTY },
      timeout: DEFAULT_TIMEOUT_MS,
      withCredentials: true,
    },
  );
  return { access: data.access, remembered: data.remembered === true };
}
