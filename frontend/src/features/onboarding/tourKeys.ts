import keys from "./tourKeys.json";

/**
 * The student guided tours (IR-1342), one per page plus Publish.
 *
 * The same closed list as the server's `apps/accounts/tours.TOUR_KEYS`: the
 * backend test `test_tours.py` holds `tourKeys.json` equal to it, and
 * `tourKeys.test.ts` holds this list equal to the JSON. A key the server does
 * not know is refused with a 400, so the three must move together.
 */
export const TOUR_KEYS = ["discover", "library", "ask", "calls", "guidelines", "notifications", "publish"] as const;

export type TourKey = (typeof TOUR_KEYS)[number];

/** The JSON the backend checks, re-exported for the drift test. */
export const TOUR_KEYS_JSON: readonly string[] = keys;

/** The address parameter Settings › Help uses to start a tour again. */
export const TOUR_PARAM = "tour";
