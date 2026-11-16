import type { Notification } from "@/types/notifications";

/**
 * Where a notification opens: the page the server names (`target`, IR-765,
 * for a notice such as a Call's that has no Record), else its Record, else
 * nowhere. The bell and the Notifications page both read it, so they agree.
 */
export function notificationHref(n: Pick<Notification, "record" | "target">): string | null {
  if (n.target) return n.target;
  return n.record != null ? `/records/${n.record}` : null;
}
