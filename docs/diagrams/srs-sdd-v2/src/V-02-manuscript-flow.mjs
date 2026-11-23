// Activity diagram. Each action names its partition (who does it) on its first
// line, as D-17 does. Corrects D-17 for ADR-067 (Unstructured), ADR-074 (ClamAV)
// and ADR-052's 2026-11-21 amendment (only a published paper reaches the AI).
const act = (id, tag, label, tone = 'core', wrap = 144) => ({ id, shape: 'box', tag, label, plain: true, tone, wrap });
const then = (from, to, label) => ({ from, to, label });

export default {
  format: 'portrait',
  direction: 'DOWN',
  title: 'V-2  Manuscript processing: upload to searchable passages',
  caption: 'From apps/documents/validators.py, apps/documents/scanning.py, apps/documents/tasks.py, apps/ai/tasks.py, apps/ai/policy/disclosure.py and CELERY_TASK_ROUTES at a46d7fc4 (IR-1275). ADR-052 (as amended 2026-11-21), ADR-054, ADR-058, ADR-067, ADR-074.',
  elk: {
    'elk.layered.spacing.nodeNodeBetweenLayers': '16',
    'elk.spacing.nodeNode': '22',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
    'elk.layered.wrapping.strategy': 'SINGLE_EDGE',
    'elk.layered.wrapping.correctionFactor': '1.4',
    'elk.aspectRatio': '0.6',
  },
  nodes: [
    { id: 'start', shape: 'start' },
    act('upload', 'Author', 'Upload the manuscript PDF', 'plain'),
    act('check', 'Django (backend)', 'Check it is a real PDF with at least one page and at most 50 MB (validators, IR-665)'),
    act('scan', 'clamav', 'Scan the bytes during the upload (clamd INSTREAM, ADR-074)'),
    { id: 'clean', shape: 'diamond', wrap: 150, label: 'Clean, and the scanner answered?' },
    act('refuse', 'Django (backend)', 'Refuse (400), store nothing, audit it', 'core', 104),
    { id: 'end_bad', shape: 'end' },
    act('save', 'Django (backend)', 'Save the Version and its file'),
    { id: 'fork', shape: 'bar', barW: 200 },
    act('review', 'celery-default', 'Review text: pdfplumber on the server, no AI (ADR-058)', 'core', 112),
    { id: 'gate', shape: 'diamond', wrap: 150, label: 'Published, embargo released, IP mark released by KTTO, Contact person said Yes to AI? (disclosure gate)' },
    act('halt', 'Django (backend)', 'Send nothing out; publishing queues it', 'core', 104),
    { id: 'end_no', shape: 'end' },
    act('extract', 'celery-extraction', 'extract_manuscript_text; admit the paid read when admission is enforced (ADR-041)'),
    act('parse', 'Unstructured', 'Platform API hi_res: text, layout, tables, figures', 'ext'),
    act('store', 'celery-extraction', 'Store PdfExtraction and Figures'),
    act('chunk', 'celery-default', 'chunk_extraction: labelled-structure chunks (target 700, ceiling 2,000 voyage-context-4 tokens)'),
    act('swap', 'celery-default', 'Swap in the new ChunkSet atomically'),
    act('embed', 'celery-embedding', 'embed_chunk_set: only chunks whose text changed'),
    act('voyage', 'Voyage AI', 'Contextualized chunk embeddings, 1024 dimensions', 'ext'),
    act('vectors', 'celery-embedding', 'Store ChunkEmbedding (pgvector, HNSW cosine)'),
    act('overview', 'celery-embedding', 'generate_record_overview: the cited AI Overview'),
    act('serve', 'AI runtime', 'Search, read and cite the passages for readers who may read the paper', 'ai'),
    { id: 'end', shape: 'end' },
  ],
  edges: [
    then('start', 'upload'), then('upload', 'check'), then('check', 'scan'), then('scan', 'clean'),
    then('clean', 'refuse', 'no'), then('refuse', 'end_bad'),
    then('clean', 'save', 'yes'), then('save', 'fork'),
    then('fork', 'review'), then('fork', 'gate'),
    then('gate', 'halt', 'no'), then('halt', 'end_no'),
    then('gate', 'extract', 'yes'),
    then('extract', 'parse'), then('parse', 'store'), then('store', 'chunk'), then('chunk', 'swap'),
    then('swap', 'embed'), then('embed', 'voyage'), then('voyage', 'vectors'), then('vectors', 'overview'),
    then('overview', 'serve'), then('serve', 'end'),
  ],
  legend: [
    'first line of an action: who does it',
    { tone: 'core', text: 'IRIS service' }, { tone: 'ai', text: 'AI runtime' }, { tone: 'ext', text: 'external service' },
    'bar: work that continues in parallel',
  ],
};
