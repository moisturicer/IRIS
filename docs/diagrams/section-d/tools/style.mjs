// Shared style for every Section D diagram (IR-1021).
// One palette, one typeface, one set of sizes and one line style, so every
// diagram reads the same. Nothing in a diagram source sets a colour or a size.

export const PAGE = {
  // Logical canvas widths. Every PNG is exactly one of the two, so text is the
  // same physical size in every figure placed at full text width.
  portrait: 720, // fits a 6.5 in text block on A4/Letter portrait
  landscape: 1040, // fits a 9.4 in text block on a landscape page
  margin: 14,
  scale: 2.75, // PNG pixels per logical pixel: 1980 px and 2860 px wide (about 300 dpi)
};

export const COLOR = {
  ink: '#1F2937',
  muted: '#5B6B7F',
  line: '#475569',
  paper: '#FFFFFF',
  panel: '#F8FAFC',
  panelBorder: '#94A3B8',
};

// Tone = meaning. The same five tones are used by every diagram and legend.
export const TONE = {
  core: { fill: '#E0F2FE', stroke: '#0369A1', label: 'IRIS' },
  ai: { fill: '#DCFCE7', stroke: '#15803D', label: 'AI runtime / AI-assisted' },
  ext: { fill: '#FEF3C7', stroke: '#B45309', label: 'external service' },
  ref: { fill: '#F1F5F9', stroke: '#94A3B8', label: 'drawn in full on another diagram' },
  muted: { fill: '#F1F5F9', stroke: '#94A3B8', label: 'kept read only / test double' },
  plain: { fill: '#FFFFFF', stroke: '#475569', label: '' },
};

export const FONT = {
  family: 'Inter',
  title: 12.5,
  node: 10, // node names
  body: 9, // attribute rows, sub-lines, notes
  edge: 8.5, // relationship labels, multiplicities
  caption: 8.5,
  lineHeight: 1.28,
};

export const STROKE = { node: 0.9, edge: 0.9, group: 0.8 };
