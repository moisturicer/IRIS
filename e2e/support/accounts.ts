// The accounts `seed_demo --accounts-only` creates (IR-227, IR-478). Journeys
// act as these, and create every Record they touch themselves.
export const PASSWORD = "IrisDemo123!";

export const ACCOUNTS = {
  student: "student@cit.edu",
  adviser: "adviser@cit.edu",
  rdco: "rdco@cit.edu",
  itso: "itso@cit.edu",
  ierc: "ierc@cit.edu",
  ktto: "ktto@cit.edu",
  itsoCoordinator: "itso.coordinator@cit.edu",
  iercCoordinator: "ierc.coordinator@cit.edu",
  kttoCoordinator: "ktto.coordinator@cit.edu",
  rdcoCoordinator: "rdco.coordinator@cit.edu",
  admin: "admin@cit.edu",
} as const;

export type AccountName = keyof typeof ACCOUNTS;

/** A title no other run or journey has used, so journeys never collide. */
export function uniqueTitle(journey: string): string {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  return `[E2E ${journey}] ${stamp}-${Math.random().toString(36).slice(2, 7)}`;
}
