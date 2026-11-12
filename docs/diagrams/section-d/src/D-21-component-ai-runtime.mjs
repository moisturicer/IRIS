import { cls } from '../tools/dsl.mjs';

const ai = (id, label, rows) => cls(id, label, rows ? [rows] : [], { tone: 'ai' });
const port = (id, rows) => cls(id, id, [rows], { stereotype: 'abstract' });
const adapter = (id) => cls(id, id, []);
const double = (id) => cls(id, id, [], { tone: 'muted', stereotype: 'test double' });
const uses = (from, to, label, o = {}) => ({ from, to, label, ...o });
const implementsPort = (from, to) => ({ from, to, head: 'tri', dash: true });

export default {
  kind: 'columns',
  format: 'landscape',
  title: 'D-21  AI runtime classes: ports and adapters',
  caption: 'From ai/ on main (IR-1021): api/, runs/, agent/, research/, admission/, domain/ports.py and infrastructure/. ADR-014, ADR-049.',
  gutter: 54,
  vgap: 24,
  nodes: [
    ai('api', 'runs.py', ['POST /runs, GET /runs/{id}', 'cancel, retry, conversations']),
    cls('db', 'PostgreSQL iris_ai schema', [], { tone: 'ref' }),
    ai('worker', 'worker.py', ['claims queued runs']),
    ai('RunService', 'RunService', ['submit()', 'retry()', 'run_next()', 'execute()']),
    ai('RunStore', 'RunStore', ['admit() / claim_next()', 'save_checkpoint()', 'commit_final() / fail()', 'status() / reopen()']),
    ai('AgentExecutor', 'AgentExecutor', ['bounded tool loop', 'one repair']),
    ai('agentparts', 'checkpoint, compaction,\ncontext, assurance'),
    ai('ResearchTools', 'ResearchTools', ['search (hybrid)', 'open_passage / read_page', 'outline / read_manuscript', 'resolve_papers / count_records']),
    ai('Admitted', 'AdmittedAgentProvider', ['reserve, recheck, settle']),
    port('LLMProvider', ['generate_response()  {abstract}', 'converse()', 'capacity()']),
    port('EmbeddingProvider', ['embed_documents()  {abstract}', 'embed_query()  {abstract}']),
    adapter('OpenAICompatibleAgentProvider'),
    adapter('OpenAILLMProvider'),
    double('RecordingAgentProvider'),
    adapter('OpenAIEmbeddingProvider'),
    double('DeterministicFakeEmbeddingProvider'),
  ],
  columns: [
    ['api', 150, 'db'],
    ['worker', 'RunService', 'RunStore'],
    ['AgentExecutor', 'agentparts', 48, 'ResearchTools', 48, 'Admitted'],
    [40, 'LLMProvider', 110, 'EmbeddingProvider'],
    ['OpenAICompatibleAgentProvider', 'OpenAILLMProvider', 'RecordingAgentProvider', 60, 'OpenAIEmbeddingProvider', 'DeterministicFakeEmbeddingProvider'],
  ],
  groups: [
    { id: 'g_api', label: 'api (FastAPI routes)', members: ['api'] },
    { id: 'g_runs', label: 'runs', members: ['worker', 'RunService', 'RunStore'] },
    { id: 'g_agent', label: 'agent', members: ['AgentExecutor', 'agentparts'] },
    { id: 'g_research', label: 'research', members: ['ResearchTools'] },
    { id: 'g_admission', label: 'admission', members: ['Admitted'] },
    { id: 'g_domain', label: 'domain (ports)', members: ['LLMProvider', 'EmbeddingProvider'] },
    { id: 'g_infra', label: 'infrastructure (adapters)', members: ['OpenAICompatibleAgentProvider', 'OpenAILLMProvider', 'RecordingAgentProvider', 'OpenAIEmbeddingProvider', 'DeterministicFakeEmbeddingProvider'] },
  ],
  edges: [
    uses('api', 'RunService'),
    uses('worker', 'RunService'),
    uses('RunService', 'RunStore'),
    uses('RunService', 'AgentExecutor'),
    uses('AgentExecutor', 'agentparts'),
    uses('AgentExecutor', 'ResearchTools'),
    uses('AgentExecutor', 'Admitted'),
    implementsPort('Admitted', 'LLMProvider'),
    uses('Admitted', 'OpenAICompatibleAgentProvider', 'wraps'),
    implementsPort('OpenAICompatibleAgentProvider', 'LLMProvider'),
    implementsPort('OpenAILLMProvider', 'LLMProvider'),
    implementsPort('RecordingAgentProvider', 'LLMProvider'),
    implementsPort('OpenAIEmbeddingProvider', 'EmbeddingProvider'),
    implementsPort('DeterministicFakeEmbeddingProvider', 'EmbeddingProvider'),
    uses('RunStore', 'db'),
    uses('ResearchTools', 'db', "under the reader's grant", { wrap: 40 }),
  ],
  legend: [
    { line: 'arrow', text: 'uses' },
    { line: 'dash tri', text: 'implements the port' },
    { tone: 'ai', text: 'AI runtime class' }, { tone: 'core', text: 'port or adapter' },
    { tone: 'muted', text: 'test double (recording and fake adapters)' },
  ],
};
