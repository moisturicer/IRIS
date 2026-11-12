// Render every Section D diagram (IR-1021): src/*.mjs and src/*.json -> png/*.png
//
//   node render.mjs            render all
//   node render.mjs D-04 D-11  render the ones whose file name starts with these
//   node render.mjs --svg      also keep the SVG next to each PNG (build/, not committed)
//
// Layout is ELK's layered algorithm with orthogonal edge routing; the sequence
// diagram is laid out on a grid. Style comes only from style.mjs.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ELK from 'elkjs/lib/elk.bundled.js';
import opentype from 'opentype.js';
import { Resvg } from '@resvg/resvg-js';
import { PAGE, COLOR, TONE, FONT, STROKE } from './style.mjs';
import { layoutUsecase } from './usecase.mjs';
import { layoutColumns } from './grid.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const OUT = path.join(HERE, '..', 'png');
const FONT_DIR = path.join(HERE, 'node_modules', '@expo-google-fonts', 'inter');
const FONT_FILES = ['Inter_400Regular.ttf', 'Inter_600SemiBold.ttf'].map((f) => path.join(FONT_DIR, f));
const toAB = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
const REG = opentype.parse(toAB(fs.readFileSync(FONT_FILES[0])));
const BOLD = opentype.parse(toAB(fs.readFileSync(FONT_FILES[1])));

// ---------- text ----------
const tw = (s, size, bold) => (bold ? BOLD : REG).getAdvanceWidth(String(s), size);
const lh = (size) => size * FONT.lineHeight;
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function wrap(text, size, maxW, bold) {
  const out = [];
  for (const para of String(text).split('\n')) {
    if (!maxW) { out.push(para); continue; }
    let line = '';
    for (const word of para.split(' ')) {
      const t = line ? line + ' ' + word : word;
      if (line && tw(t, size, bold) > maxW) { out.push(line); line = word; } else line = t;
    }
    out.push(line);
  }
  return out;
}
const maxW = (lines, size, bold) => Math.max(0, ...lines.map((l) => tw(l, size, bold)));

function textEl(lines, x, y, size, { bold = false, fill = COLOR.ink, anchor = 'start' } = {}) {
  // y is the top of the first line
  return lines.map((l, i) =>
    `<text x="${r(x)}" y="${r(y + size * 0.82 + i * lh(size))}" font-size="${size}" ` +
    `font-weight="${bold ? 600 : 400}" fill="${fill}" text-anchor="${anchor}">${esc(l)}</text>`).join('');
}
const r = (n) => Math.round(n * 100) / 100;

// ---------- node measurement ----------
const PADX = 8, PADY = 6, ROW = 12, HEAD = 18;

function measure(n) {
  const s = n.shape || (n.children ? 'group' : 'box');
  n.shape = s;
  if (s === 'group') {
    n._label = wrap(n.label || '', FONT.node, 0, true);
    return;
  }
  if (s === 'table' || s === 'class') {
    n._name = wrap(n.label, FONT.node, 0, true);
    n._st = n.stereotype ? `«${n.stereotype}»` : null;
    let w = maxW(n._name, FONT.node, true);
    if (n._st) w = Math.max(w, tw(n._st, FONT.edge));
    let h = n._name.length * lh(FONT.node) + (n._st ? lh(FONT.edge) : 0) + 7;
    n._head = h;
    if (n.app) w = Math.max(w, tw(n.label, FONT.node, true) + tw('  ' + n.app, FONT.edge) );
    for (const sec of n.sections || []) {
      for (const row of sec) w = Math.max(w, rowWidth(row));
      h += sec.length * ROW + (sec.length ? 6 : 3);
    }
    n.w = Math.ceil(w + 14); n.h = Math.ceil(h);
    return;
  }
  if (s === 'usecase') {
    n._lines = wrap(n.label, FONT.node, n.wrap || 150);
    const w = maxW(n._lines, FONT.node), h = n._lines.length * lh(FONT.node);
    n.w = Math.ceil(w * 1.18 + 26); n.h = Math.ceil(h + 14 + n._lines.length * 3);
    return;
  }
  if (s === 'actor') {
    n._lines = wrap(n.label, FONT.body, n.wrap || 125);
    n.w = Math.ceil(Math.max(22, maxW(n._lines, FONT.body)) + 4);
    n.h = Math.ceil(30 + n._lines.length * lh(FONT.body));
    return;
  }
  if (s === 'note') {
    n._lines = wrap(n.label, FONT.body, n.wrap || 170);
    n.w = Math.ceil(maxW(n._lines, FONT.body) + 16); n.h = Math.ceil(n._lines.length * lh(FONT.body) + 10);
    return;
  }
  if (s === 'start' || s === 'end') { n.w = 14; n.h = 14; return; }
  if (s === 'bar') { n.w = n.barW || 90; n.h = 4; return; }
  if (s === 'diamond') {
    n._lines = wrap(n.label, FONT.body, n.wrap || 150);
    n.w = Math.ceil(maxW(n._lines, FONT.body) * 1.7 + 36); n.h = Math.ceil(n._lines.length * lh(FONT.body) * 1.5 + 22);
    return;
  }
  // box, db, queue, store
  n._tag = n.tag ? [n.tag] : [];
  n._lines = n.label ? wrap(n.label, FONT.node, n.wrap || 0, !n.plain) : [];
  n._sub = n.sub ? wrap(n.sub, FONT.body, n.wrap || 0) : [];
  const w = Math.max(maxW(n._tag, FONT.edge, true), maxW(n._lines, FONT.node, !n.plain), maxW(n._sub, FONT.body));
  const h = n._tag.length * lh(FONT.edge) + n._lines.length * lh(FONT.node) + n._sub.length * lh(FONT.body);
  const cyl = s === 'db' || s === 'queue' || s === 'store';
  n.w = Math.ceil(w + 2 * PADX); n.h = Math.ceil(h + 2 * PADY + (cyl ? 7 : 0));
}

function rowWidth(row) {
  if (typeof row === 'string') return tw(row, FONT.body);
  return tw(row.k, FONT.body, row.pk) + (row.v ? 5 + tw(row.v, FONT.body) : 0);
}

// ---------- ELK ----------
const elk = new ELK();
const BASE = {
  'elk.algorithm': 'layered',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
  'elk.layered.spacing.nodeNodeBetweenLayers': '30',
  'elk.spacing.nodeNode': '10',
  'elk.spacing.edgeNode': '9',
  'elk.spacing.edgeEdge': '6',
  'elk.layered.spacing.edgeNodeBetweenLayers': '10',
  'elk.layered.spacing.edgeEdgeBetweenLayers': '6',
  'elk.spacing.componentComponent': '14',
  'elk.spacing.edgeLabel': '2',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.thoroughness': '40',
  'elk.padding': '[top=0,left=0,bottom=0,right=0]',
};

function toElk(n) {
  measure(n);
  if (n.shape === 'group') {
    const lw = maxW(n._label, FONT.node, true) + 20;
    return {
      id: n.id,
      children: n.children.map(toElk),
      layoutOptions: {
        'elk.padding': `[top=${n.label ? 22 : 8},left=${n.pad ?? 9},bottom=${n.pad ?? 9},right=${n.pad ?? 9}]`,
        'elk.nodeSize.constraints': 'MINIMUM_SIZE',
        'elk.nodeSize.minimum': `(${Math.ceil(lw)},24)`,
        ...(n.elk || {}),
      },
    };
  }
  return { id: n.id, width: n.w, height: n.h, layoutOptions: n.elk || {} };
}

function walk(nodes, fn, parent = null) {
  for (const n of nodes) { fn(n, parent); if (n.children) walk(n.children, fn, n); }
}

async function layoutGraph(spec) {
  const byId = {};
  const children = spec.nodes.map(toElk);
  walk(spec.nodes, (n) => { byId[n.id] = n; });
  const edges = [];
  spec.edges.forEach((e, i) => {
    e.id = 'e' + i;
    for (const k of ['from', 'to']) if (!byId[e[k]]) throw new Error(`${spec.id}: edge ${e.from} -> ${e.to}: unknown node ${e[k]}`);
    if (e.manual) return;
    const el = { id: e.id, sources: [e.reverse ? e.to : e.from], targets: [e.reverse ? e.from : e.to] };
    if (e.label) {
      e._lines = wrap(e.label, FONT.edge, e.wrap || 0);
      el.labels = [{ text: e.label, width: Math.ceil(maxW(e._lines, FONT.edge) + 6), height: Math.ceil(e._lines.length * lh(FONT.edge) + 2) }];
    }
    edges.push(el);
  });
  const graph = {
    id: 'root',
    layoutOptions: { ...BASE, 'elk.direction': spec.direction || 'RIGHT', ...(spec.elk || {}) },
    children, edges,
  };
  const res = await elk.layout(graph);
  // absolute node boxes
  const abs = { root: { x: 0, y: 0 } };
  (function place(list, ox, oy) {
    for (const c of list) {
      const n = byId[c.id];
      n.x = ox + c.x; n.y = oy + c.y; n.w = c.width; n.h = c.height;
      abs[c.id] = { x: n.x, y: n.y };
      if (c.children) place(c.children, n.x, n.y);
    }
  })(res.children, 0, 0);
  const elkEdges = {};
  (function collect(node) {
    for (const e of node.edges || []) elkEdges[e.id] = e;
    for (const c of node.children || []) collect(c);
  })(res);
  for (const e of spec.edges) {
    if (e.manual) continue;
    const ee = elkEdges[e.id];
    const off = abs[ee.container || 'root'] || abs.root;
    const sec = ee.sections[0];
    let pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map((p) => ({ x: p.x + off.x, y: p.y + off.y }));
    if (e.reverse) pts.reverse();
    clipEllipse(pts, byId[e.from], 0); clipEllipse(pts, byId[e.to], pts.length - 1);
    e.pts = pts;
    if (ee.labels && ee.labels[0]) { const l = ee.labels[0]; e.lbl = { x: l.x + off.x, y: l.y + off.y, w: l.width, h: l.height }; }
  }
  manualEdges(spec, byId);
  return byId;
}

function clipEllipse(pts, n, i) {
  if (n.shape !== 'usecase') return;
  const p = pts[i], q = pts[i === 0 ? 1 : i - 1];
  const cx = n.x + n.w / 2, cy = n.y + n.h / 2, a = n.w / 2, b = n.h / 2;
  if (Math.abs(p.y - q.y) < 0.01) { // horizontal end segment
    const dy = (p.y - cy) / b; if (Math.abs(dy) >= 1) return;
    const dx = a * Math.sqrt(1 - dy * dy);
    p.x = q.x < cx ? cx - dx : cx + dx;
  } else if (Math.abs(p.x - q.x) < 0.01) {
    const dx = (p.x - cx) / a; if (Math.abs(dx) >= 1) return;
    const dy = b * Math.sqrt(1 - dx * dx);
    p.y = q.y < cy ? cy - dy : cy + dy;
  }
}

// Edges drawn after layout, outside ELK: generalisation between actors that sit
// in the same column, routed through a lane on the column's left.
function manualEdges(spec, byId) {
  const lanes = {};
  for (const e of spec.edges) {
    if (e.manual !== 'gen') continue;
    const a = byId[e.from], b = byId[e.to];
    if (!(e.to in lanes)) lanes[e.to] = Object.keys(lanes).length;
    const fig = (n) => ({ x: n.x + n.w / 2 - 9, y: n.y + 13 });
    const pa = fig(a), pb = fig(b);
    const x = Math.min(...spec.edges.filter((g) => g.manual === 'gen').flatMap((g) => [byId[g.from].x, byId[g.to].x])) - 9 - lanes[e.to] * 8;
    e.pts = [pa, { x, y: pa.y }, { x, y: pb.y }, pb];
  }
}

// ---------- markers ----------
function marker(kind, p, q) {
  // p = end point on the node, q = previous point. Returns {svg, trim}.
  const len = Math.hypot(p.x - q.x, p.y - q.y) || 1;
  const d = { x: (p.x - q.x) / len, y: (p.y - q.y) / len }, n = { x: -d.y, y: d.x };
  const at = (back, side = 0) => `${r(p.x - d.x * back + n.x * side)},${r(p.y - d.y * back + n.y * side)}`;
  const st = `stroke="${COLOR.line}" stroke-width="${STROKE.edge}"`;
  const ln = (a, b) => `<path d="M${a} L${b}" ${st} fill="none"/>`;
  const circ = (back) => `<circle cx="${r(p.x - d.x * back)}" cy="${r(p.y - d.y * back)}" r="2.5" fill="${COLOR.paper}" ${st}/>`;
  switch (kind) {
    case 'arrow': return { svg: `<path d="M${at(6.5, 3)} L${at(0)} L${at(6.5, -3)}" ${st} fill="none" stroke-linejoin="round" stroke-linecap="round"/>`, trim: 0 };
    case 'tri': return { svg: `<path d="M${at(0)} L${at(8.5, 4.3)} L${at(8.5, -4.3)} Z" ${st} fill="${COLOR.paper}" stroke-linejoin="round"/>`, trim: 8.5 };
    case 'diamond': return { svg: `<path d="M${at(0)} L${at(5.5, 3.2)} L${at(11)} L${at(5.5, -3.2)} Z" ${st} fill="${COLOR.line}"/>`, trim: 11 };
    case 'odiamond': return { svg: `<path d="M${at(0)} L${at(5.5, 3.2)} L${at(11)} L${at(5.5, -3.2)} Z" ${st} fill="${COLOR.paper}"/>`, trim: 11 };
    case 'one': return { svg: ln(at(3.5, 3.6), at(3.5, -3.6)) + ln(at(6.5, 3.6), at(6.5, -3.6)), trim: 0 };
    case 'zero-one': return { svg: ln(at(3.5, 3.6), at(3.5, -3.6)) + circ(8.6), trim: 0 };
    case 'zero-many': return { svg: ln(at(6.5), at(0, 3.8)) + ln(at(6.5), at(0, -3.8)) + circ(9.2), trim: 0 };
    default: return { svg: '', trim: 0 };
  }
}

function drawEdge(e) {
  let pts = e.pts.map((p) => ({ ...p }));
  let svg = '';
  const ends = [[e.tail, 0, 1], [e.head ?? 'arrow', pts.length - 1, pts.length - 2]];
  const marks = [];
  for (const [kind, i, j] of ends) {
    if (!kind || kind === 'none') continue;
    const m = marker(kind, pts[i], pts[j]);
    marks.push(m.svg);
    if (m.trim) {
      const p = pts[i], q = pts[j], len = Math.hypot(p.x - q.x, p.y - q.y) || 1;
      pts[i] = { x: p.x - ((p.x - q.x) / len) * m.trim, y: p.y - ((p.y - q.y) / len) * m.trim };
    }
  }
  const dstr = pts.map((p, i) => `${i ? 'L' : 'M'}${r(p.x)},${r(p.y)}`).join(' ');
  svg += `<path d="${dstr}" fill="none" stroke="${COLOR.line}" stroke-width="${STROKE.edge}" stroke-linejoin="round"${e.dash ? ' stroke-dasharray="4 3"' : ''}/>`;
  svg += marks.join('');
  let over = '';
  if (e.lbl) {
    over += `<rect x="${r(e.lbl.x)}" y="${r(e.lbl.y)}" width="${r(e.lbl.w)}" height="${r(e.lbl.h)}" fill="${COLOR.paper}" fill-opacity="0.92"/>`;
    over += textEl(e._lines, e.lbl.x + e.lbl.w / 2, e.lbl.y + 1, FONT.edge, { fill: COLOR.muted, anchor: 'middle' });
  }
  // multiplicities next to each end
  for (const [txt, i, j] of [[e.mFrom, 0, 1], [e.mTo, e.pts.length - 1, e.pts.length - 2]]) {
    if (!txt) continue;
    const p = e.pts[i], q = e.pts[j], len = Math.hypot(p.x - q.x, p.y - q.y) || 1;
    const d = { x: (q.x - p.x) / len, y: (q.y - p.y) / len };
    const w = tw(txt, FONT.edge);
    const horiz = Math.abs(d.x) > 0.5;
    const x = horiz ? p.x + d.x * (4 + (d.x < 0 ? w : 0)) + (d.x < 0 ? 0 : 0) : p.x + 4;
    const y = horiz ? p.y - 11 : p.y + d.y * 12 - 5 + (d.y < 0 ? 0 : 0);
    const xx = horiz ? (d.x > 0 ? p.x + 4 : p.x - 4 - w) : x;
    const yy = horiz ? y : (d.y > 0 ? p.y + 3 : p.y - 12);
    over += textEl([txt], xx, yy, FONT.edge, { fill: COLOR.muted });
  }
  return { svg, over };
}

// ---------- node drawing ----------
function tone(n) { return TONE[n.tone || 'core']; }

function drawNode(n) {
  const t = tone(n), sw = `stroke="${t.stroke}" stroke-width="${STROKE.node}"`;
  const { x, y, w, h } = n;
  const cx = x + w / 2;
  switch (n.shape) {
    case 'group': {
      const gt = n.tone ? TONE[n.tone] : { fill: COLOR.panel, stroke: COLOR.panelBorder };
      return `<rect x="${r(x)}" y="${r(y)}" width="${r(w)}" height="${r(h)}" rx="4" fill="${n.tone ? gt.fill : COLOR.panel}" fill-opacity="${n.tone && n.tone !== 'plain' ? 0.35 : 1}" stroke="${gt.stroke}" stroke-width="${STROKE.group}"${n.dashed ? ' stroke-dasharray="4 3"' : ''}/>` +
        textEl(n._label, x + 9, y + 6, FONT.node, { bold: true });
    }
    case 'table': case 'class': {
      let s = `<rect x="${r(x)}" y="${r(y)}" width="${r(w)}" height="${r(h)}" rx="3" fill="${COLOR.paper}" ${sw}/>`;
      s += `<path d="M${r(x + 3)},${r(y)} h${r(w - 6)} a3,3 0 0 1 3,3 v${r(n._head - 3)} h${r(-w)} v${r(-(n._head - 3))} a3,3 0 0 1 3,-3 z" fill="${t.fill}" ${sw}/>`;
      let ty = y + 3.5;
      if (n._st) { s += textEl([n._st], cx, ty, FONT.edge, { anchor: 'middle', fill: COLOR.muted }); ty += lh(FONT.edge); }
      s += textEl(n._name, cx, ty, FONT.node, { bold: true, anchor: 'middle', fill: n.tone === 'muted' ? COLOR.muted : COLOR.ink });
      let ry = y + n._head;
      (n.sections || []).filter((sec) => sec.length).forEach((sec, si) => {
        if (si) s += `<path d="M${r(x)},${r(ry)} h${r(w)}" stroke="${t.stroke}" stroke-width="0.6"/>`;
        ry += 3;
        for (const row of sec) {
          if (typeof row === 'string') s += textEl([row], x + 7, ry, FONT.body, { fill: row.startsWith('…') ? COLOR.muted : COLOR.ink });
          else {
            s += textEl([row.k], x + 7, ry, FONT.body, { bold: row.pk });
            if (row.v) s += textEl([row.v], x + 7 + tw(row.k, FONT.body, row.pk) + 5, ry, FONT.body, { fill: COLOR.muted });
          }
          ry += ROW;
        }
        ry += 3;
      });
      return s;
    }
    case 'usecase':
      return `<ellipse cx="${r(cx)}" cy="${r(y + h / 2)}" rx="${r(w / 2)}" ry="${r(h / 2)}" fill="${t.fill}" ${sw}/>` +
        textEl(n._lines, cx, y + (h - n._lines.length * lh(FONT.node)) / 2, FONT.node, { anchor: 'middle' });
    case 'actor': {
      const c = n.tone === 'ext' ? TONE.ext.stroke : COLOR.ink, a = `stroke="${c}" stroke-width="1" fill="none" stroke-linecap="round"`;
      return `<circle cx="${r(cx)}" cy="${r(y + 4.5)}" r="4" fill="${n.tone === 'ext' ? TONE.ext.fill : COLOR.paper}" stroke="${c}" stroke-width="1"/>` +
        `<path d="M${r(cx)},${r(y + 8.5)} v10 M${r(cx - 7)},${r(y + 12.5)} h14 M${r(cx)},${r(y + 18.5)} l-6,8 M${r(cx)},${r(y + 18.5)} l6,8" ${a}/>` +
        textEl(n._lines, cx, y + 29, FONT.body, { anchor: 'middle' });
    }
    case 'note':
      return `<path d="M${r(x)},${r(y)} h${r(w - 7)} l7,7 v${r(h - 7)} h${r(-w)} z" fill="${COLOR.panel}" stroke="${COLOR.panelBorder}" stroke-width="0.8"/>` +
        `<path d="M${r(x + w - 7)},${r(y)} v7 h7" fill="none" stroke="${COLOR.panelBorder}" stroke-width="0.8"/>` +
        textEl(n._lines, x + 7, y + 5, FONT.body, { fill: COLOR.ink });
    case 'start': return `<circle cx="${r(cx)}" cy="${r(y + h / 2)}" r="6" fill="${COLOR.ink}"/>`;
    case 'end': return `<circle cx="${r(cx)}" cy="${r(y + h / 2)}" r="6.3" fill="${COLOR.paper}" stroke="${COLOR.ink}" stroke-width="1"/><circle cx="${r(cx)}" cy="${r(y + h / 2)}" r="3.6" fill="${COLOR.ink}"/>`;
    case 'bar': return `<rect x="${r(x)}" y="${r(y)}" width="${r(w)}" height="${r(h)}" rx="1.5" fill="${COLOR.ink}"/>`;
    case 'diamond':
      return `<path d="M${r(cx)},${r(y)} L${r(x + w)},${r(y + h / 2)} L${r(cx)},${r(y + h)} L${r(x)},${r(y + h / 2)} Z" fill="${COLOR.panel}" stroke="${COLOR.line}" stroke-width="${STROKE.node}"/>` +
        textEl(n._lines, cx, y + (h - n._lines.length * lh(FONT.body)) / 2, FONT.body, { anchor: 'middle' });
    default: {
      const cyl = n.shape === 'db' || n.shape === 'queue' || n.shape === 'store';
      let s;
      if (cyl) {
        const e = 4.5;
        s = `<path d="M${r(x)},${r(y + e)} v${r(h - 2 * e)} a${r(w / 2)},${e} 0 0 0 ${r(w)},0 v${r(-(h - 2 * e))}" fill="${t.fill}" ${sw}/>` +
          `<ellipse cx="${r(cx)}" cy="${r(y + e)}" rx="${r(w / 2)}" ry="${e}" fill="${t.fill}" ${sw}/>`;
      } else s = `<rect x="${r(x)}" y="${r(y)}" width="${r(w)}" height="${r(h)}" rx="4" fill="${t.fill}" ${sw}/>`;
      let ty = y + PADY + (cyl ? 6 : 0);
      const tx = n.center ? cx : x + PADX, anchor = n.center ? 'middle' : 'start';
      if (n._tag.length) { s += textEl(n._tag, tx, ty, FONT.edge, { bold: true, fill: t.stroke, anchor }); ty += lh(FONT.edge); }
      s += textEl(n._lines, tx, ty, FONT.node, { bold: !n.plain, anchor }); ty += n._lines.length * lh(FONT.node);
      s += textEl(n._sub, tx, ty, FONT.body, { fill: COLOR.muted, anchor });
      return s;
    }
  }
}

// ---------- sequence diagram ----------
function layoutSequence(spec, W) {
  const P = spec.participants, n = P.length, inner = W - 2 * PAGE.margin, col = inner / n;
  const svg = [], over = [];
  P.forEach((p, i) => {
    p.cx = col * (i + 0.5);
    p._lines = wrap(p.label, FONT.node, col - 16, true);
    p._sub = p.sub ? wrap(p.sub, FONT.edge, col - 12) : [];
  });
  const headH = Math.max(...P.map((p) => p._lines.length * lh(FONT.node) + p._sub.length * lh(FONT.edge))) + 2 * PADY;
  const top = spec.boxes?.length ? 16 : 0;
  const by = Object.fromEntries(P.map((p) => [p.id, p]));
  let y = top + headH + 14;
  const frames = [];
  const emit = (steps, depth) => {
    for (const s of steps) {
      if (s.loop) {
        const y0 = y; y += 16;
        const before = { min: Infinity, max: -Infinity };
        const span = (list) => list.forEach((t) => t.loop ? span(t.steps) : [t.from, t.to].forEach((id) => { before.min = Math.min(before.min, by[id].cx); before.max = Math.max(before.max, by[id].cx); }));
        span(s.steps);
        emit(s.steps, depth + 1);
        y += 4;
        frames.push({ x0: before.min - 30, x1: Math.min(inner, before.max + 30), y0, y1: y, label: s.loop });
        y += 8;
        continue;
      }
      const a = by[s.from], b = by[s.to];
      if (!a || !b) throw new Error(`${spec.id}: unknown participant in ${s.from} -> ${s.to}`);
      const self = a === b;
      const x0 = Math.min(a.cx, b.cx), x1 = Math.max(a.cx, b.cx);
      const lines = wrap(s.label, FONT.edge, self ? 150 : Math.max(x1 - x0 - 14, 178));
      const lw = maxW(lines, FONT.edge), th = lines.length * lh(FONT.edge);
      if (self) {
        const lx = a.cx + 26;
        over.push(textEl(lines, Math.min(lx, inner - lw), y + 1, FONT.edge, { fill: COLOR.ink }));
        const yy = y + 2, y2 = y + Math.max(th, 14);
        const e = { pts: [{ x: a.cx, y: yy }, { x: a.cx + 20, y: yy }, { x: a.cx + 20, y: y2 }, { x: a.cx, y: y2 }], head: 'arrow' };
        svg.push(drawEdge(e).svg);
        y = y2 + 10;
        continue;
      }
      let lx = x0 + 7; if (lx + lw > inner) lx = inner - lw;
      over.push(`<rect x="${r(lx - 2)}" y="${r(y)}" width="${r(lw + 4)}" height="${r(th)}" fill="${COLOR.paper}" fill-opacity="0.94"/>` + textEl(lines, lx, y, FONT.edge, { fill: COLOR.ink }));
      y += th + 2.5;
      svg.push(drawEdge({ pts: [{ x: a.cx, y }, { x: b.cx, y }], head: 'arrow', dash: s.dash }).svg);
      y += 9;
    }
  };
  emit(spec.steps, 0);
  const bottom = y + 2;
  const pre = [];
  for (const bx of spec.boxes || []) {
    const i0 = P.findIndex((p) => p.id === bx.from), i1 = P.findIndex((p) => p.id === bx.to), t = TONE[bx.tone || 'ai'];
    pre.push(`<rect x="${r(col * i0 + 1)}" y="0" width="${r(col * (i1 - i0 + 1) - 2)}" height="${r(bottom)}" rx="4" fill="${t.fill}" fill-opacity="0.4" stroke="${t.stroke}" stroke-width="0.6" stroke-dasharray="4 3"/>` +
      textEl([bx.label], col * (i0 + i1 + 1) / 2, 3, FONT.edge, { bold: true, anchor: 'middle', fill: t.stroke }));
  }
  for (const p of P) {
    const t = TONE[p.tone || 'core'], w = col - 10;
    pre.push(`<path d="M${r(p.cx)},${r(top + headH)} V${r(bottom)}" stroke="${COLOR.panelBorder}" stroke-width="0.8" stroke-dasharray="3 3"/>`);
    pre.push(`<rect x="${r(p.cx - w / 2)}" y="${top}" width="${r(w)}" height="${r(headH)}" rx="4" fill="${t.fill}" stroke="${t.stroke}" stroke-width="${STROKE.node}"/>`);
    const th = p._lines.length * lh(FONT.node) + p._sub.length * lh(FONT.edge);
    const ty = top + (headH - th) / 2;
    pre.push(textEl(p._lines, p.cx, ty, FONT.node, { bold: true, anchor: 'middle' }));
    pre.push(textEl(p._sub, p.cx, ty + p._lines.length * lh(FONT.node), FONT.edge, { anchor: 'middle', fill: COLOR.muted }));
  }
  for (const f of frames) {
    const lw = tw(f.label, FONT.edge) + 40;
    pre.push(`<rect x="${r(f.x0)}" y="${r(f.y0)}" width="${r(f.x1 - f.x0)}" height="${r(f.y1 - f.y0)}" rx="3" fill="none" stroke="${COLOR.line}" stroke-width="0.8"/>`);
    over.push(`<path d="M${r(f.x0)},${r(f.y0)} h30 v8 l-5,5 h-25 z" fill="${COLOR.panel}" stroke="${COLOR.line}" stroke-width="0.8"/>` +
      textEl(['loop'], f.x0 + 4, f.y0 + 1.5, FONT.edge, { bold: true }) + textEl([`[${f.label}]`], f.x0 + 36, f.y0 + 2, FONT.edge, { fill: COLOR.muted }));
    void lw;
  }
  return { body: pre.join('') + svg.join('') + over.join(''), bw: inner, bh: bottom, minX: 0, minY: 0 };
}

// ---------- page ----------
function legendBlock(items, W) {
  let x = PAGE.margin, y = 0, svg = '';
  const lineH = 13, maxX = W - PAGE.margin;
  for (const it of items) {
    const item = typeof it === 'string' ? { text: it } : it;
    const text = item.text ?? TONE[item.tone].label;
    const sym = item.tone ? 15 : item.line ? (item.line.includes('tri') ? 19 : 16) : 0;
    const w = sym + tw(text, FONT.caption) + 14;
    if (x + w - 14 > maxX && x > PAGE.margin) { x = PAGE.margin; y += lineH; }
    if (item.tone) {
      const t = TONE[item.tone];
      svg += `<rect x="${r(x)}" y="${r(y + 1.5)}" width="10" height="8" rx="1.5" fill="${t.fill}" stroke="${t.stroke}" stroke-width="0.8"/>`;
    } else if (item.line) {
      const e = { pts: [{ x, y: y + 5.5 }, { x: x + 12, y: y + 5.5 }], head: 'none', dash: item.line.includes('dash') };
      if (item.line.includes('tri')) { e.head = 'tri'; e.pts[1].x += 2; }
      if (item.line.includes('arrow')) e.head = 'arrow';
      if (item.line.includes('diamond')) e.tail = 'diamond';
      if (item.line.includes('many')) { e.tail = 'zero-many'; e.head = 'one'; e.pts[0].x -= 0; e.pts[1].x += 6; }
      svg += drawEdge(e).svg;
    }
    svg += textEl([text], x + sym + (item.line?.includes('many') ? 6 : 0), y, FONT.caption, { fill: COLOR.ink });
    x += w + (item.line?.includes('many') ? 6 : 0);
  }
  return { svg, h: items.length ? y + lineH : 0 };
}

async function renderSpec(spec) {
  const W0 = PAGE[spec.format || 'portrait'];
  let body, bw, bh, minX, minY;
  if (spec.kind === 'sequence') ({ body, bw, bh, minX, minY } = layoutSequence(spec, W0));
  else {
    let all, edges, dots = [];
    if (spec.kind === 'usecase') ({ nodes: all, edges } = layoutUsecase(spec, { measure, tw }));
    else if (spec.kind === 'erd' || spec.kind === 'columns') ({ nodes: all, edges, dots } = layoutColumns(spec, { measure, tw, wrap }, W0 - 2 * PAGE.margin));
    else { all = Object.values(await layoutGraph(spec)); edges = spec.edges; }
    const xs = [], ys = [];
    for (const n of all) { xs.push(n.x, n.x + n.w); ys.push(n.y, n.y + n.h); }
    const under = [], top = [], overs = [];
    for (const e of edges) {
      for (const p of e.pts) { xs.push(p.x - 3, p.x + 3); ys.push(p.y - 3, p.y + 3); }
      if (e.lbl) { xs.push(e.lbl.x, e.lbl.x + e.lbl.w); ys.push(e.lbl.y, e.lbl.y + e.lbl.h); }
      const d = drawEdge(e); top.push(d.svg); overs.push(d.over);
    }
    const groups = all.filter((n) => n.shape === 'group'), leaves = all.filter((n) => n.shape !== 'group');
    if (spec.nodes) { // parents before children
      const depth = {}; walk(spec.nodes, (n, p) => { depth[n.id] = p ? depth[p.id] + 1 : 0; });
      groups.sort((a, b) => depth[a.id] - depth[b.id]);
    }
    for (const g of groups) under.push(drawNode(g));
    const dotSvg = dots.map((d) => `<circle cx="${r(d.x)}" cy="${r(d.y)}" r="1.9" fill="${COLOR.line}"/>`).join('');
    body = under.join('') + top.join('') + dotSvg + leaves.map(drawNode).join('') + overs.join('');
    minX = Math.min(...xs); minY = Math.min(...ys);
    bw = Math.max(...xs) - minX; bh = Math.max(...ys) - minY;
  }
  let W = W0;
  const fit = bw <= W0 - 2 * PAGE.margin;
  if (!fit) W = Math.ceil(bw + 2 * PAGE.margin);
  const titleLines = wrap(spec.title, FONT.title, W - 2 * PAGE.margin, true);
  const titleH = titleLines.length * lh(FONT.title) + 8;
  const legend = legendBlock(spec.legend || [], W);
  const cap = spec.caption ? wrap(spec.caption, FONT.caption, W - 2 * PAGE.margin) : [];
  const capH = cap.length * lh(FONT.caption);
  const y0 = PAGE.margin + titleH;
  const H = Math.ceil(y0 + bh + (legend.h ? 12 + legend.h : 0) + (capH ? 8 + capH : 0) + PAGE.margin - 2);
  const ox = (W - bw) / 2 - minX, oy = y0 - minY;
  let ly = y0 + bh + 12;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="${FONT.family}, Arial, sans-serif">` +
    `<rect width="${W}" height="${H}" fill="${COLOR.paper}"/>` +
    textEl(titleLines, PAGE.margin, PAGE.margin, FONT.title, { bold: true }) +
    `<g transform="translate(${r(ox)},${r(oy)})">${body}</g>` +
    (legend.h ? `<g transform="translate(0,${r(ly)})">${legend.svg}</g>` : '') +
    textEl(cap, PAGE.margin, ly + (legend.h ? legend.h + 6 : -4), FONT.caption, { fill: COLOR.muted }) +
    `</svg>`;
  void ly;
  const png = new Resvg(svg, {
    fitTo: { mode: 'width', value: Math.round(W * PAGE.scale) },
    font: { fontFiles: FONT_FILES, loadSystemFonts: false, defaultFontFamily: FONT.family },
    background: COLOR.paper,
  }).render().asPng();
  return { svg, png, W, H, fit, format: spec.format || 'portrait' };
}

async function main() {
  const args = process.argv.slice(2);
  const keepSvg = args.includes('--svg');
  const only = args.filter((a) => !a.startsWith('--'));
  const files = fs.readdirSync(SRC).filter((f) => /^D-\d+.*\.(mjs|json)$/.test(f)).sort();
  fs.mkdirSync(OUT, { recursive: true });
  let bad = 0;
  for (const f of files) {
    if (only.length && !only.some((o) => f.startsWith(o))) continue;
    const full = path.join(SRC, f);
    const spec = f.endsWith('.json') ? JSON.parse(fs.readFileSync(full, 'utf8'))
      : (await import(pathToFileURL(full).href + '?t=' + Date.now())).default;
    spec.id = f.replace(/\.(mjs|json)$/, '');
    const out = await renderSpec(spec);
    fs.writeFileSync(path.join(OUT, spec.id + '.png'), out.png);
    if (keepSvg) { fs.mkdirSync(path.join(HERE, 'build'), { recursive: true }); fs.writeFileSync(path.join(HERE, 'build', spec.id + '.svg'), out.svg); }
    if (!out.fit) bad++;
    console.log(`${out.fit ? 'ok  ' : 'WIDE'} ${spec.id}  ${out.format} ${out.W}x${out.H}`);
  }
  if (bad) { console.error(`${bad} diagram(s) are wider than their page format`); process.exitCode = 1; }
}

main().catch((e) => { console.error(e); process.exit(1); });
