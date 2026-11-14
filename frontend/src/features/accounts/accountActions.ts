/**
 * What the Users page offers each viewer on each row (ADR-051 §4-5, amended, IR-781).
 *
 * A rendering hint that mirrors the server's rules, which still refuse
 * anything else: the System Admin gives office roles and the coordinator flag,
 * RDCO gives Student or Adviser to someone outside the offices and locks
 * accounts, and nobody acts on a System Admin's account here. Nobody acts on
 * their own row either (IR-1077), so a slip cannot lock yourself out.
 */
import { ALL_ROLES, ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

const AUTHOR_ROLES: readonly string[] = [ROLES.STUDENT, ROLES.ADVISER];

function isOffice(role: string): boolean {
  return (STAFF_ROLES as readonly string[]).includes(role);
}

/** The roles `viewer` may give someone who now holds `target`, or none. */
export function rolesToOffer(viewer: string | null | undefined, target: string): RoleName[] {
  if (target === ROLES.SYSTEM_ADMIN) return [];
  if (viewer === ROLES.SYSTEM_ADMIN) return ALL_ROLES.filter((r) => r !== ROLES.SYSTEM_ADMIN);
  if (viewer === ROLES.RDCO && (target === "" || AUTHOR_ROLES.includes(target))) {
    return [ROLES.STUDENT, ROLES.ADVISER];
  }
  return [];
}

/** Whether `viewer` may make or remove `target` as an office coordinator. */
export function mayCoordinate(viewer: string | null | undefined, target: string): boolean {
  return viewer === ROLES.SYSTEM_ADMIN && isOffice(target);
}

/** Whether `viewer` may lock or unlock `target`'s account. */
export function mayLock(viewer: string | null | undefined, target: string): boolean {
  return viewer === ROLES.RDCO && target !== ROLES.SYSTEM_ADMIN;
}

/** A row's actions, in the order its menu lists them. */
export type RowAction = "change-role" | "coordinator" | "lock";

/**
 * What `viewer` is offered on one row, or nothing. The viewer's own row carries
 * no action at all, whatever the rules above would otherwise allow, and
 * nothing is offered while the viewer's own id is unknown.
 */
export function rowActions(
  viewer: string | null | undefined,
  viewerId: number | null | undefined,
  target: { id: number; role_name: string },
): RowAction[] {
  // Without an id the viewer's own row cannot be told apart, so nothing is offered.
  if (viewerId === null || viewerId === undefined || target.id === viewerId) return [];
  const actions: RowAction[] = [];
  if (rolesToOffer(viewer, target.role_name).length > 0) actions.push("change-role");
  if (mayCoordinate(viewer, target.role_name)) actions.push("coordinator");
  if (mayLock(viewer, target.role_name)) actions.push("lock");
  return actions;
}
