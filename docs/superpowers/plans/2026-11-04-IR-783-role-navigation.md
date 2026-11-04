# IR-783 implementation plan

Authority: ADR-051 decisions 1-7 and the IR-781 amendment; ticket IR-783.

Use the existing access map and shared Users page. Give RDCO and System Admin separate screen keys and routes so navigation and gates keep the same source of truth. Reusing one role-dependent path would complicate router registration; separate page implementations would duplicate the same account UI. System Admin lands on Users and keeps public catalogue access, with no workflow or research-tool navigation. Existing styling and responsive navigation remain.

1. At the approved access-map seam, run a failing test for RDCO addresses and sections, then split Users into RDCO and System Admin entries, change RDCO paths, and update section order. Update old expectations deliberately to the accepted ADR.
2. At the approved landing seam, fail a System Admin landing test, then send that role to its Users page.
3. At the approved rendered sidebar/router seam, prove named groups, links, role refusals, removed addresses, and axe checks. Register all changed routes from the access map. Avoid sending System Admin requests for workflow statistics.
4. Correct Settings and role-specific Help wording, navigation documentation and per-ticket traceability.
5. Run targeted tests through each slice; use GitHub CI for the full frontend suite, lint and typechecking/build, per the user's preference against duplicating CI. Review the task diff against its starting commit along Standards and Spec axes, fix findings, commit, push and open a PR, and record evidence in Jira In Review. Human approval and merge remain the completion gate.
