import { AUDIT_EVENT_GROUPS } from "@/types/audit";

/**
 * Turns the event types the server lists into the Audit Log filter's groups
 * (IR-913).
 *
 * The server owns *which* types exist and what each is called; the frontend owns
 * only how they are *grouped*, because a group is presentation. That split is
 * what lets a backend PR add an event type with no frontend change:
 *
 *  - a type the frontend groups appears under its group, with the server's label;
 *  - a type it has never heard of appears under "Other", so it is filterable the
 *    moment the backend has it, and ungrouped until someone groups it here;
 *  - a type still grouped here that the server no longer has is simply not listed,
 *    so a stale key can never put a choice in the filter that the log would refuse.
 */

export interface AuditEventTypeOption {
  type: string;
  label: string;
}

export interface AuditEventTypeGroup {
  group: string;
  types: AuditEventTypeOption[];
}

export const OTHER_GROUP = "Other";

export function groupAuditEventTypes(options: AuditEventTypeOption[]): AuditEventTypeGroup[] {
  const byType = new Map(options.map((option) => [option.type, option]));
  const grouped = new Set<string>();

  const groups: AuditEventTypeGroup[] = [];
  for (const [group, members] of Object.entries(AUDIT_EVENT_GROUPS)) {
    const types: AuditEventTypeOption[] = [];
    for (const type of Object.keys(members)) {
      const option = byType.get(type);
      if (!option) continue;
      types.push(option);
      grouped.add(type);
    }
    if (types.length > 0) groups.push({ group, types });
  }

  const ungrouped = options.filter((option) => !grouped.has(option.type));
  if (ungrouped.length > 0) groups.push({ group: OTHER_GROUP, types: ungrouped });

  return groups;
}
