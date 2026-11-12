// Activity diagram. Each action names its partition (who does it) on its first
// line, the UML alternative to swimlane columns, which keeps the figure narrow.
const act = (id, tag, label, tone = 'core') => ({ id, shape: 'box', tag, label, plain: true, tone, wrap: 178 });
const then = (from, to, label) => ({ from, to, label });

export default {
  format: 'portrait',
  direction: 'DOWN',
  title: 'D-17  Manuscript processing: upload to searchable passages',
  caption: 'From apps/documents/tasks.py, apps/ai/tasks.py, apps/records/tasks.py, CELERY_TASK_ROUTES and ADR-052, ADR-054, ADR-056, ADR-058 on main (IR-1021).',
  elk: {
    'elk.layered.spacing.nodeNodeBetweenLayers': '16',
    'elk.spacing.nodeNode': '22',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
    'elk.layered.wrapping.strategy': 'SINGLE_EDGE',
    'elk.layered.wrapping.correctionFactor': '1.4',
    'elk.aspectRatio': '0.9',
  },
  nodes: [
    { id: 'start', shape: 'start' },
    act('upload', 'Author', 'Upload the manuscript PDF', 'plain'),
    act('check', 'Django (backend)', 'Check it is a real PDF with at least one page and at most 50 MB (validators, IR-665)'),
    act('save', 'Django (backend)', 'Save the Version and its file'),
    { id: 'fork', shape: 'bar', barW: 200 },
    act('review', 'celery-default', 'read_review_text: pdfplumber on campus (no AI, every Version, ADR-058)'),
    act('extract', 'celery-extraction', 'extract_manuscript_text'),
    { id: 'gate', shape: 'diamond', wrap: 170, label: 'Embargo released and Contact person answered Yes to AI use? (ADR-052, ADR-054)' },
    act('halt', 'celery-extraction', 'Stop: nothing leaves campus'),
    { id: 'end_no', shape: 'end' },
    act('admit', 'celery-extraction', 'Admit the paid call when provider admission is enforced (ADR-041)'),
    act('parse', 'LlamaParse', 'Parse the PDF into structure', 'ext'),
    act('store', 'celery-extraction', 'Store PdfExtraction and Figures'),
    act('chunk', 'celery-default', 'chunk_extraction: labelled-structure chunks (voyage-context-4 tokens, ceiling 700)'),
    act('swap', 'celery-default', 'Swap in the new ChunkSet atomically'),
    act('embed', 'celery-embedding', 'embed_chunk_set'),
    act('voyage', 'Voyage AI', 'Contextualized chunk embeddings', 'ext'),
    act('vectors', 'celery-embedding', 'Store ChunkEmbedding (pgvector, HNSW)'),
    act('overview', 'celery-embedding', 'generate_record_overview (needs a summary model)'),
    act('serve', 'AI runtime', 'Search, read and cite the passages for readers who may read the paper', 'ai'),
    { id: 'end', shape: 'end' },
  ],
  edges: [
    then('start', 'upload'), then('upload', 'check'), then('check', 'save'), then('save', 'fork'),
    then('fork', 'review'), then('fork', 'extract'),
    then('extract', 'gate'),
    then('gate', 'halt', 'no'), then('halt', 'end_no'),
    then('gate', 'admit', 'yes'),
    then('admit', 'parse'), then('parse', 'store'), then('store', 'chunk'), then('chunk', 'swap'),
    then('swap', 'embed'), then('embed', 'voyage'), then('voyage', 'vectors'), then('vectors', 'overview'),
    then('overview', 'serve'), then('serve', 'end'),
  ],
  legend: [
    'first line of an action: who does it',
    { tone: 'core', text: 'IRIS service' }, { tone: 'ai', text: 'AI runtime' }, { tone: 'ext', text: 'external service' },
    'bar: work that continues in parallel',
  ],
};
