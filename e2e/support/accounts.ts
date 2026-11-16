// The accounts `seed_demo --accounts-only` creates (IR-227, IR-478). Journeys
// act as these, and create every Record they touch themselves. They are
// `@iris.test` since IR-1067, which moved them off real CIT-U mailboxes; the
// people journeys register for themselves are still `@cit.edu` (people.ts).
export const PASSWORD = "IrisDemo123!";

export const ACCOUNTS = {
  student: "student@iris.test",
  adviser: "adviser@iris.test",
  rdco: "rdco@iris.test",
  itso: "itso@iris.test",
  ierc: "ierc@iris.test",
  ktto: "ktto@iris.test",
  itsoCoordinator: "itso.coordinator@iris.test",
  iercCoordinator: "ierc.coordinator@iris.test",
  kttoCoordinator: "ktto.coordinator@iris.test",
  rdcoCoordinator: "rdco.coordinator@iris.test",
  admin: "admin@iris.test",
} as const;

export type AccountName = keyof typeof ACCOUNTS;

/** A title no other run or journey has used, so journeys never collide. */
export function uniqueTitle(journey: string): string {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  return `[E2E ${journey}] ${stamp}-${Math.random().toString(36).slice(2, 7)}`;
}
