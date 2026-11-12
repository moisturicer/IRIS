const msg = (from, to, label) => ({ from, to, label });
const reply = (from, to, label) => ({ from, to, label, dash: true });

export default {
  kind: 'sequence',
  format: 'portrait',
  title: 'D-18  Ask IRIS request flow',
  caption: 'From frontend/runtime-edge.conf, apps/ai/views/grants.py, ai/api/runs.py, ai/runs (service, store, worker) and ai/agent on main (IR-1021). ADR-049.',
  participants: [
    { id: 'reader', label: 'Reader', tone: 'plain' },
    { id: 'spa', label: 'React', sub: 'RuntimeReader' },
    { id: 'edge', label: 'nginx', sub: 'runtime edge' },
    { id: 'dj', label: 'Django', sub: 'edge-grant' },
    { id: 'gw', label: 'ai-gateway', sub: 'FastAPI', tone: 'ai' },
    { id: 'w', label: 'ai-runs-worker', sub: 'AgentExecutor', tone: 'ai' },
    { id: 'db', label: 'PostgreSQL', sub: 'iris_ai + Django tables' },
    { id: 'ext', label: 'Voyage / language model', tone: 'ext' },
  ],
  boxes: [{ label: 'AI runtime', from: 'gw', to: 'w', tone: 'ai' }],
  steps: [
    msg('reader', 'spa', 'ask a question'),
    msg('spa', 'edge', 'POST /api/v1/ai/runtime/runs'),
    msg('edge', 'dj', 'auth_request (JWT)'),
    reply('dj', 'edge', 'reader grant, or 401/403'),
    msg('edge', 'gw', 'run request + grant + service secret'),
    msg('gw', 'db', 'verify grant; insert ask_run (queued)'),
    reply('gw', 'spa', 'run id'),
    msg('gw', 'w', 'wake through Redis (hint only)'),
    msg('w', 'db', 'claim the run (lease, fence)'),
    {
      loop: "research steps within the run's bounds",
      steps: [
        msg('w', 'db', "search / read passages under the reader's row policy"),
        msg('w', 'ext', 'admitted query embedding / model call'),
      ],
    },
    msg('w', 'w', 'check the draft; repair once if it fails'),
    msg('w', 'db', 'commit Turn and citations (fenced)'),
    msg('spa', 'edge', 'GET /runs/<id>?after=N'),
    msg('edge', 'gw', '(grant re-checked)'),
    msg('gw', 'db', 'read the run journal'),
    reply('gw', 'spa', 'events and final answer'),
    msg('spa', 'reader', 'answer with page citations'),
  ],
  legend: [
    { line: 'arrow', text: 'request' }, { line: 'dash arrow', text: 'response' },
    { tone: 'core', text: 'IRIS service' }, { tone: 'ai', text: 'AI runtime' }, { tone: 'ext', text: 'external service' },
  ],
};
