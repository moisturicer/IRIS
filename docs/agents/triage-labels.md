# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the label strings actually used in IRIS.

**IRIS already has a label taxonomy** — [`issue-tracker.md`](issue-tracker.md). Four of the five roles map onto labels that already exist there; one is new.

| Label in mattpocock/skills | Label in our tracker | Group | Meaning |
|---|---|---|---|
| `needs-triage` | `not-ready` | Flow (exists) | Fails the Definition of Ready; stays out of the pullable queue |
| `needs-info` | `not-ready` | Flow (exists) | Waiting on the reporter for more information — **deliberately merged**, see below |
| `ready-for-agent` | `ready-for-agent` | **new** | Fully specified, ready for an AFK agent |
| `ready-for-human` | `ready-to-pull` | Flow (exists) | Ready to be pulled by a person; no assignee set |
| `wontfix` | `do-not-build` | MVP (exists) | Will not be actioned |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from the middle column.

## Live usage on the IR board

Verified 2026-09-02 over all 57 issues, `ready-for-agent` re-checked 2026-09-03. Every issue is labelled; none is bare.

| Label | Issues | Note |
|---|---|---|
| `ready-to-pull` | 13 | in use |
| `blocked` | 6 | in use — not a triage role, see below |
| `not-ready` | 0 | in the taxonomy, never applied |
| `do-not-build` | 0 | in the taxonomy, never applied |
| `ready-for-agent` | 1 | seeded 2026-09-03 on IR-82 |

## Notes

- **`needs-info` is not a separate label.** It maps onto `not-ready`, which already means *not yet pullable*. Two label strings for one state is how a taxonomy rots — when the reason is a missing answer, say so in a comment on the issue, not in a second label.
- `blocked` is **not** a triage role. It means an item cannot proceed because of an external impediment, and it stays on the item in whatever column it already occupies. Do not use it in place of `not-ready`.
- **Jira Cloud labels are free text.** There is no managed list and no admin step: any user with Edit Issue permission creates a label by typing it into the field. Adding `ready-for-agent` needed no approval — but nothing validates spelling either, so `ready-for-agents` would be accepted silently and be invisible to every board filter. **This is why a new label is seeded once from the picker**: it then appears in autocomplete for everyone, so it gets selected rather than retyped.
- When a new label is first used, add it to the Flow group in [`issue-tracker.md`](issue-tracker.md) rather than letting the two files drift.
- `not-ready` is the marker for the Not Ready state as well as the triage role — one label, one meaning: *not yet pullable*.
