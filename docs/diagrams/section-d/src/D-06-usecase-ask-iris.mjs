import { A, X, U, AI, UC_LEGEND } from '../tools/dsl.mjs';

export default {
  kind: 'usecase',
  title: 'D-6  Use cases: Ask IRIS and Paper Chat',
  caption: 'From frontend RuntimeReader, apps/ai grants and the ai/ runtime on main (IR-1021). Research roles only (access.ts RESEARCH_ROLES).',
  system: 'Ask IRIS and Paper Chat',
  left: [A('R', 'Researcher\n(Student, Adviser, RDCO,\nITSO, IERC, KTTO)')],
  right: [X('LLM', 'Language model\n(OpenAI-compatible\nendpoint)'), X('V', 'Embedding and rerank\n(Voyage)')],
  cases: [
    AI('UC1', 'Ask a question across the papers I may read', 150),
    AI('UC2', 'Chat about one paper (Paper Chat)', 130),
    AI('UC8', 'Search, read and count permitted papers', 150),
    U('UC3', 'Read the answer with page citations', 130),
    U('UC4', 'Open a cited passage in the paper', 130),
    U('UC5', 'Stop, reconnect or retry a run'),
    U('UC6', 'Reopen or delete a Conversation', 130),
    U('UC7', 'Read, rename or delete a Conversation from before the switch', 170),
  ],
  links: [
    ['R', 'UC1', 'UC2', 'UC5', 'UC6', 'UC7'],
    ['LLM', 'UC1', 'UC2'],
    ['V', 'UC8'],
  ],
  deps: [
    { from: 'UC1', to: 'UC8', label: '«include»' },
    { from: 'UC1', to: 'UC3', label: '«include»' },
    { from: 'UC2', to: 'UC8', label: '«include»' },
    { from: 'UC2', to: 'UC3', label: '«include»' },
    { from: 'UC3', to: 'UC4', label: '«extend»' },
  ],
  notes: [{ on: 'UC8', side: 'left', wrap: 130, text: "Every read goes through the reader's Django-issued grant, checked inside PostgreSQL (ADR-049)" }],
  legend: [...UC_LEGEND, { tone: 'ai', text: 'AI-assisted' }, { tone: 'ext', text: 'external system' }],
};
