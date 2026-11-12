import { A, U, AI, UC_LEGEND } from '../tools/dsl.mjs';

export default {
  kind: 'usecase',
  title: 'D-5  Use cases: discovery and reading',
  caption: 'From frontend routes (/, /records/:id, /records/mine, /people/:id, /opportunities) and records/library views on main (IR-1021).',
  system: 'Discovery and reading',
  left: [A('User', 'Signed-in user')],
  right: [A('RDCO', 'RDCO'), A('Poster', 'Adviser or RDCO')],
  cases: [
    U('UC1', 'Search and filter Discover'),
    U('UC2', 'Save a feed; read For you'),
    U('UC3', 'Open a paper in Paper View'),
    U('UC4', 'Find in the paper; follow a citation to its page', 150),
    AI('UC5', 'Read the AI Overview'),
    U('UC6', 'See related research'),
    U('UC7', 'Save to My Library with a reading status', 130),
    U('UC8', 'Comment on a published paper'),
    U('UC9', 'Search people; open a profile'),
    U('UC10', 'Request a download'),
    U('UC11', 'Approve, decline or revoke a download request', 150),
    U('UC12', 'Browse Calls & Conferences'),
    U('UC13', 'Post a call for papers'),
  ],
  links: [
    ['User', 'UC1', 'UC2', 'UC3', 'UC7', 'UC8', 'UC9', 'UC10', 'UC12'],
    ['RDCO', 'UC11'],
    ['Poster', 'UC13'],
  ],
  deps: [
    { from: 'UC3', to: 'UC4', label: '«extend»' },
    { from: 'UC3', to: 'UC5', label: '«extend»' },
    { from: 'UC3', to: 'UC6', label: '«extend»' },
  ],
  notes: [{ on: 'UC10', wrap: 130, text: 'Reading stays open; a download needs RDCO approval (ADR-048)' }],
  legend: [...UC_LEGEND, { tone: 'ai', text: 'AI-assisted' }],
};
