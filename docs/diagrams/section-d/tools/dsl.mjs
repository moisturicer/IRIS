// Small helpers so a diagram source reads as a list of things and links.
export const A = (id, label, o = {}) => ({ id, label, ...o }); // actor
export const X = (id, label, o = {}) => ({ id, label, tone: 'ext', ...o }); // external actor
export const U = (id, label, wrap, o = {}) => ({ id, label, wrap: wrap || 150, ...o }); // use case
export const AI = (id, label, wrap) => U(id, label, wrap, { tone: 'ai' }); // AI-assisted use case
export const UC_LEGEND = [
  { line: 'solid', text: 'actor takes part' },
  { line: 'dash arrow', text: 'dependency between use cases' },
];
export const GEN_LEGEND = { line: 'tri', text: 'is a kind of' };

export const box = (id, label, sub, o = {}) => ({ id, shape: 'box', label, sub, ...o });
export const group = (id, label, children, o = {}) => ({ id, label, children, ...o });
export const cls = (id, label, sections, o = {}) => ({ id, shape: 'class', label, sections, ...o });
