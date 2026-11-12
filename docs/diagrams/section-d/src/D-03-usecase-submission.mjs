import { A, X, U, AI, UC_LEGEND } from '../tools/dsl.mjs';

export default {
  kind: 'usecase',
  title: 'D-3  Use cases: submission and versions',
  caption: 'From RecordViewSet actions and apps/documents on main (IR-1021). Authors are Students and Advisers (access.ts AUTHORS).',
  system: 'Submission and versions',
  left: [A('Author', 'Author\n(Student or Adviser)'), A('RDCO', 'RDCO')],
  right: [X('LP', 'Manuscript reader\n(LlamaParse)')],
  cases: [
    U('UC2', 'Accept title and abstract suggestions read from the PDF', 170),
    U('UC1', 'Publish a record: metadata, authors, Adviser, IP type, manuscript PDF', 180),
    AI('UC11', "Extract the manuscript's text and structure", 150),
    U('UC5', 'Submit a new Version after a revision request', 150),
    U('UC3', "Upload supporting documents to the record's slots", 160),
    U('UC4', 'Answer a document request'),
    U('UC6', 'Reply to review threads'),
    U('UC7', 'Name the Contact person'),
    U('UC8', 'Request deletion of a record'),
    U('UC9', 'Import legacy records from an Excel template', 150),
    U('UC10', 'Replace the Adviser, add an owner, withdraw a paper in review', 170),
  ],
  links: [
    ['Author', 'UC1', 'UC5', 'UC3', 'UC4', 'UC6', 'UC7', 'UC8'],
    ['RDCO', 'UC9', 'UC10'],
    ['LP', 'UC11'],
  ],
  deps: [
    { from: 'UC1', to: 'UC2', label: '«extend»' },
    { from: 'UC1', to: 'UC11', label: '«include»' },
    { from: 'UC5', to: 'UC11', label: '«include»' },
  ],
  notes: [{ on: 'UC11', side: 'left', wrap: 120, text: 'Runs in a background worker; only papers the consent and embargo gate permits leave the campus (ADR-056)' }],
  legend: [...UC_LEGEND, { tone: 'ai', text: 'AI-assisted' }, { tone: 'ext', text: 'external system' }],
};
