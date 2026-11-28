// State diagram drawn with the activity layout: each box is a stored
// PipelineStatus; the in-review box lists the derived WorkflowState values.
const st = (id, label, sub, tone = 'core') => ({ id, shape: 'box', label, sub, tone, wrap: 132 });
const go = (from, to, label) => ({ from, to, label });

export default {
  format: 'portrait',
  direction: 'DOWN',
  title: 'V-3  Record lifecycle and review states',
  caption: 'From core/enums.py (PipelineStatus, WorkflowState) and apps/reviews/tracker.py derive_workflow_state at 2d8d4e4a (IR-1275). ADR-021 §4, ADR-032 §2-§3, ADR-047 §1 and §5, ADR-052 decision 14. Shown names in brackets are what readers see.',
  elk: {
    'elk.layered.spacing.nodeNodeBetweenLayers': '30',
    'elk.spacing.nodeNode': '18',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    'elk.aspectRatio': '0.6',
  },
  nodes: [
    { id: 'start', shape: 'start' },
    st('draft', 'draft', "the creator's alone (404 to everyone else)", 'plain'),
    st('review', 'in_review', 'derived, first match wins: awaiting_resubmission · awaiting_document · submitted · final_review · in_review'),
    st('approved', 'approved  [Accepted]', 'Proposal only; may be continued as a Thesis or Project'),
    st('published', 'published', 'listed in Discover; the only state the AI reads (ADR-052, 2026-11-21)'),
    st('completed', 'completed  [Unlisted]', 'Thesis / Research or Project kept unlisted by RDCO'),
    st('rejected', 'rejected  [Archived]', 'terminal'),
    st('pending', 'pending_delete', 'holds accepted work while RDCO reviews a delete request'),
    { id: 'end', shape: 'end' },
  ],
  edges: [
    go('start', 'draft', 'author creates'),
    go('draft', 'review', 'submit: the Adviser holds it'),
    go('review', 'approved', 'Adviser accepts a Proposal'),
    go('review', 'published', 'RDCO publishes (embargo released)'),
    go('review', 'completed', 'RDCO keeps unlisted'),
    go('review', 'rejected', 'Adviser or RDCO rejects, with a reason'),
    go('completed', 'published', 'RDCO publishes later'),
    go('approved', 'pending', 'owner asks to delete'),
    go('published', 'pending', 'owner asks to delete'),
    go('pending', 'end', 'RDCO approves'),
  ],
  legend: [
    'box: stored PipelineStatus; its second line says what it means',
    'in_review: one stored value; who holds the record is its active assignments',
    'RDCO declining a delete request returns the record to its previous status',
    'a revision request is an open ResubmissionRequest, never a status',
  ],
};
