import { cls } from '../tools/dsl.mjs';

// composition: the diamond sits at the owner
const owns = (from, to, mTo = '0..*') => ({ from, to, tail: 'diamond', head: 'none', mFrom: '1', mTo });

export default {
  kind: 'columns',
  format: 'portrait',
  title: 'D-20  Workflow core classes (the thesis contribution)',
  caption: 'Models from backend/apps/records and backend/apps/reviews; operations are the service functions in reviews/routing.py, seats.py, revisions.py, new_version.py, decisions.py, office_review.py and records/embargo.py on main (IR-1021). Clearance-aware resubmission (ADR-003): a new Version resets only the clearance of the office whose ResubmissionRequest it answers; the others are preserved. RESUBMISSION_POLICY=restart_all is the comparison arm (ADR-004).',
  gutter: 66,
  vgap: 36,
  nodes: [
    cls('Record', 'Record', [
      ['pipeline_status', 'record_type → RecordType', 'adviser → User', 'origin', 'embargoed_until', 'embargo_released_at'],
      ['set_embargo()', 'release_embargo()'],
    ]),
    cls('RecordVersion', 'RecordVersion', [
      ['number', 'manuscript', 'manuscript_sha256', 'review_text → ReviewText'],
      ['submit_new_version()'],
    ]),
    cls('RecordAssignment', 'RecordAssignment', [
      ['party', 'state', 'due_at', 'opened_at / closed_at'],
      ['accept_and_route()', 'route()'],
    ]),
    cls('ReviewerSeat', 'ReviewerSeat', [
      ['reviewer → User', 'state', 'source', 'assigned_at / opened_at / done_at'],
      ['claim() / assign() / reassign()', 'open_review() / complete_seat()'],
    ]),
    cls('RecordClearance', 'RecordClearance', [
      ['office', 'status', 'comment', 'reviewed_by → User'],
      ['is_preserved()', 'carryover()'],
    ]),
    cls('ResubmissionRequest', 'ResubmissionRequest', [
      ['party', 'state', 'reason'],
      ['request_revision()', 'withdraw_revision_request()'],
    ]),
    cls('Review', 'Review', [
      ['stage', 'status', 'comment', 'version → RecordVersion'],
      ['record_office_review()', 'decide()'],
    ]),
    cls('ReviewComment', 'ReviewComment', [['severity (Must fix, Suggestion)', 'is_draft', 'anchor_version']]),
    cls('RoutingEvent', 'RoutingEvent', [['from_party', 'to_party', 'suggested_offices']]),
  ],
  columns: [
    ['RecordVersion', 'Review', 'ReviewerSeat'],
    ['Record', 'RecordAssignment', 'ResubmissionRequest'],
    ['RecordClearance', 'ReviewComment', 'RoutingEvent'],
  ],
  edges: [
    owns('Record', 'RecordVersion', '1..*'),
    owns('Record', 'RecordAssignment'),
    owns('Record', 'RecordClearance'),
    owns('Record', 'ResubmissionRequest'),
    owns('Record', 'ReviewComment'),
    owns('Record', 'RoutingEvent'),
    owns('RecordAssignment', 'ReviewerSeat'),
    { from: 'RecordAssignment', to: 'Review', tail: 'odiamond', head: 'none', mFrom: '1', mTo: '0..*' },
    { from: 'ResubmissionRequest', to: 'RecordAssignment', mFrom: '0..*', mTo: '1' },
    { from: 'Review', to: 'RecordVersion', label: 'reviewed against', mFrom: '0..*', mTo: '1' },
  ],
  legend: [
    { line: 'diamond', text: 'owns (composition)' },
    'hollow diamond: groups (aggregation)',
    { line: 'arrow', text: 'refers to' },
    'upper box: attributes · lower box: service functions that act on the class',
  ],
};
