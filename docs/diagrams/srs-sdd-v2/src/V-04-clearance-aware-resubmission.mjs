const msg = (from, to, label) => ({ from, to, label });
const reply = (from, to, label) => ({ from, to, label, dash: true });

export default {
  kind: 'sequence',
  format: 'portrait',
  title: 'V-4  Clearance-aware resubmission (the thesis contribution)',
  caption: 'From apps/reviews/finish_review.py, revisions.py and new_version.py submit_new_version at c01f0ef1 (IR-1275). ADR-003, ADR-004, ADR-032 §5 and §7, ADR-022 Amendment 8. Example: RDCO routed ITSO, IERC and KTTO; IERC and KTTO have cleared; ITSO requests changes, asking for a new version. Under the restart-all comparison arm (ADR-004, WORKFLOW_TABLE) the reset step resets every office instead.',
  participants: [
    { id: 'itso', label: 'ITSO reviewer', tone: 'plain' },
    { id: 'owner', label: 'Owner', tone: 'plain' },
    { id: 'spa', label: 'React', sub: 'Paper View' },
    { id: 'dj', label: 'Django', sub: 'revisions · new_version' },
    { id: 'db', label: 'PostgreSQL', sub: 'one transaction' },
    { id: 'peers', label: 'IERC and KTTO', sub: 'already cleared', tone: 'plain' },
  ],
  steps: [
    msg('itso', 'dj', 'Finish review: Request changes (a new version), with Must fix threads'),
    msg('dj', 'db', 'open ResubmissionRequest (party itso); every clearance left as it is'),
    reply('dj', 'owner', 'notified: changes requested (record awaiting_resubmission)'),
    msg('owner', 'spa', 'answer each Must fix thread; upload in Documents (held until sent)'),
    msg('spa', 'dj', 'store the upload with sent_at null: the owners alone see it'),
    msg('spa', 'dj', 'Submit new version: POST /records/<id>/new-version/'),
    msg('dj', 'db', 'lock the record; check: requests open, something changed, Must fix answered'),
    msg('dj', 'db', 'send every held upload; write Version n+1 naming them; freeze the response letter'),
    msg('dj', 'db', 'resolve every open request as resubmitted; count the resubmission'),
    msg('dj', 'db', "reset ONLY the asking parties' clearances (ITSO) to pending"),
    msg('dj', 'db', 'keep IERC and KTTO cleared: preserved, recorded per office'),
    msg('dj', 'db', "reopen ITSO's assignment with the same Seats (in_review)"),
    msg('dj', 'db', 'write the AuditEvent in the same transaction'),
    reply('db', 'dj', 'commit'),
    reply('dj', 'itso', 'after commit: notification + live hint'),
    reply('dj', 'peers', 'nothing: their work stands'),
    msg('itso', 'dj', 'review Version n+1 and clear'),
    reply('dj', 'itso', 'ITSO cleared; RDCO is notified the office is done'),
  ],
  legend: [
    { line: 'arrow', text: 'request or write' }, { line: 'dash arrow', text: 'response or notice' },
    'restart-all arm: every office resets and reviews again',
  ],
};
