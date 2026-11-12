import { box } from '../tools/dsl.mjs';

const svc = (id, label, sub) => box(id, label, sub, { wrap: 88 });
const ai = (id, label, sub) => box(id, label, sub, { wrap: 88, tone: 'ai' });
const ext = (id, label, sub) => box(id, label, sub, { wrap: 84, tone: 'ext' });
const store = (id, label, sub) => ({ id, shape: 'db', label, sub, wrap: 88 });
const to = (from, to, label, o = {}) => ({ from, to, label, ...o });

export default {
  kind: 'columns',
  format: 'landscape',
  align: 'center',
  title: 'D-16  Deployment architecture (production)',
  caption: 'From docker-compose.prod.yml, deploy/caddy/Caddyfile, frontend/nginx.conf and deploy/aws/iris-demo.yaml on main (IR-1021). Only Caddy publishes ports. Every container rotates its logs (10 MB × 3); the restart policy brings services back after a reboot.',
  nodes: [
    { id: 'browser', shape: 'actor', label: 'Browser' },
    ext('net', 'Internet'),
    ext('dns', 'DuckDNS', 'iris-citu.duckdns.org'),
    svc('caddy', 'caddy', 'TLS 1.2/1.3, ports 80 and 443'),
    svc('nginx', 'frontend (nginx)', 'React build, /api proxy, runtime edge with auth_request'),
    svc('django', 'backend', 'Django 5 + DRF, Gunicorn with Uvicorn workers (ASGI)'),
    ai('gw', 'ai-gateway', 'FastAPI, no public port'),
    store('db', 'db', 'PostgreSQL 16 + pgvector: Django tables + iris_ai schema'),
    store('redis', 'redis', 'Celery broker, cache, run wake-ups'),
    store('media', 'media_files volume', 'uploaded manuscripts'),
    svc('migrate', 'migrate', 'runs once before the others'),
    svc('beat', 'celery-beat', 'scheduled jobs, Manila time'),
    svc('cdef', 'celery-default'),
    svc('cext', 'celery-extraction', 'concurrency 2'),
    svc('cemb', 'celery-embedding', 'concurrency 4'),
    ai('rw', 'ai-runs-worker', 'python -m ai.runs.worker'),
    ext('smtp', 'SMTP email'),
    ext('llp', 'LlamaParse', 'manuscript extraction'),
    ext('voy', 'Voyage AI', 'embedding, rerank'),
    ext('llm', 'Language model', 'OpenAI-compatible endpoint (OpenRouter)'),
  ],
  columns: [
    ['browser', 30, 'net', 30, 'dns'],
    ['caddy', 36, 'nginx'],
    ['django', 30, 'gw'],
    ['media', 'db', 'redis'],
    ['migrate', 'cdef', 'cext', 'cemb', 'rw', 'beat'],
    ['smtp', 'llp', 'voy', 'llm'],
  ],
  gutters: [54, 102, 90, 42, 90],
  groups: [{
    id: 'ec2', label: 'AWS EC2 instance (Ubuntu 24.04, Docker Compose)',
    members: ['caddy', 'nginx', 'django', 'gw', 'db', 'redis', 'media', 'migrate', 'beat', 'cdef', 'cext', 'cemb', 'rw'],
  }],
  edges: [
    to('browser', 'net', 'HTTPS'),
    to('net', 'caddy'),
    to('dns', 'caddy', 'name', { dash: true }),
    to('caddy', 'nginx', 'HTTP, internal'),
    to('nginx', 'django', '/api/, /static/, edge-grant check', { wrap: 82 }),
    to('nginx', 'gw', '/api/v1/ai/runtime/… + service secret', { wrap: 82 }),
    to('django', 'media'),
    to('django', 'db'),
    to('django', 'redis'),
    to('gw', 'db', 'iris_ai, as iris_ai_runtime', { wrap: 74 }),
    to('gw', 'redis', 'wake workers'),
    to('migrate', 'db'),
    to('cdef', 'db'), to('cdef', 'redis'), to('cdef', 'smtp'),
    to('cext', 'media'), to('cext', 'db'), to('cext', 'redis'), to('cext', 'llp'),
    to('cemb', 'db'), to('cemb', 'redis'), to('cemb', 'voy'), to('cemb', 'llm', 'AI Overview'),
    to('rw', 'db'), to('rw', 'redis'), to('rw', 'voy', 'query embedding'), to('rw', 'llm', 'answers'),
    to('beat', 'redis'),
  ],
  legend: [
    { tone: 'core', text: 'IRIS service' }, { tone: 'ai', text: 'AI runtime' }, { tone: 'ext', text: 'external service' },
    { line: 'arrow', text: 'calls or reads and writes' }, { line: 'dash arrow', text: 'name resolution' },
    'lines to the same service share a trunk, joined with a dot',
  ],
};
