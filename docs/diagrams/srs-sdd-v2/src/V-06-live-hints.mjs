const msg = (from, to, label) => ({ from, to, label });
const reply = (from, to, label) => ({ from, to, label, dash: true });

export default {
  kind: 'sequence',
  format: 'portrait',
  title: 'V-6  Live updates by server-sent hints',
  caption: 'From apps/live (channels.py, publish.py, stream.py, views.py) and frontend/src/lib/live.ts at c01f0ef1 (IR-1275). ADR-073. A hint names what changed and never carries data; what a page shows after a hint is what a manual refresh would show.',
  participants: [
    { id: 'tab', label: 'React tab', sub: 'lib/live.ts' },
    { id: 'stream', label: 'Django ASGI', sub: 'GET /api/v1/live/' },
    { id: 'redis', label: 'Redis', sub: 'live:* channels' },
    { id: 'act', label: 'Django', sub: 'a workflow act' },
    { id: 'db', label: 'PostgreSQL' },
  ],
  steps: [
    msg('tab', 'stream', 'open one stream per tab (fetch, Authorization header)'),
    msg('stream', 'db', 'authenticate once, then close the DB connection'),
    msg('stream', 'redis', "listen on the server-chosen channels: user, the person's offices, their role"),
    msg('act', 'db', 'e.g. RDCO routes a record to ITSO; commit'),
    msg('act', 'redis', 'on_commit: publish {"topics": ["reviews"]} to live:office:itso'),
    reply('redis', 'stream', 'one PSUBSCRIBE per server process fans out to its streams'),
    reply('stream', 'tab', 'event: hint {"topics": ["reviews"]}'),
    msg('tab', 'act', 'refetch To review and counts through the normal API'),
    reply('act', 'tab', 'data, under the normal permission checks'),
    msg('tab', 'stream', 'stream drops or the tab regains focus: reconnect, then refetch'),
  ],
  legend: [
    { line: 'arrow', text: 'request or publish' }, { line: 'dash arrow', text: 'response or event' },
    'Redis down: the act still succeeds; the publish failure is logged',
  ],
};
