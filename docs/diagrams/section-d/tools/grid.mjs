// Column layout with orthogonal routing. Used by the ERDs (D-8 to D-15) and by
// the architecture, component and class diagrams (D-16, D-19 to D-21).
//
// - Placement: nodes sit in columns. A diagram either names its columns
//   (spec.columns) or leaves them to a seeded search that puts related nodes in
//   the same or neighbouring columns and keeps the columns level. Same input,
//   same picture.
// - Routing: every line runs on a 6 px grid that excludes the nodes, so no line
//   passes under a node or its text. A foreign key leaves from its own
//   attribute row. Unlabelled lines to the same node share a trunk (joined with
//   a dot); other lines never share a segment and cross at right angles only.
import { FONT } from './style.mjs';

const G = 6; // grid step
const STUB = 12; // straight run at each end, room for the end marker
const up = (v, m) => Math.ceil(v / m) * m;

function rng(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export function layoutColumns(spec, { measure, tw, wrap }, availIn) {
  const nodes = spec.nodes;
  const GUT = up(spec.gutter ?? 42, G), VGAP = up(spec.vgap ?? 24, G);
  if (spec.gutters) spec.gutters = spec.gutters.map((g) => up(g, G)); // everything sits on the routing grid
  const isTable = (n) => n.shape === 'table' || n.shape === 'class';
  const by = Object.fromEntries(nodes.map((n) => [n.id, n]));
  for (const e of spec.edges) for (const k of ['from', 'to']) if (!by[e[k]]) throw new Error(`${spec.id}: edge ${e.from} -> ${e.to}: unknown node ${e[k]}`);
  const outOf = (n) => spec.edges.filter((e) => e.from === n.id && e.from !== e.to);
  const hasIn = (n) => spec.edges.some((e) => e.to === n.id);
  for (const n of nodes) {
    measure(n);
    if (isTable(n)) {
      const rows = (n.sections || []).reduce((s, sec) => s + sec.length, 0), secs = (n.sections || []).filter((s) => s.length).length;
      n._head = 9 + 12 * n._name.length + (n._st ? 12 : 0); // keeps every row centre on the grid
      n.h = rows ? up(n._head + rows * 12 + Math.max(1, secs) * 6 - 3, G) : up(n._head, G);
      if (n.shape === 'class') n.h = Math.max(n.h, up(12 + 12 * spec.edges.filter((e) => e.from === n.id || e.to === n.id).length, G));
    } else {
      // labelled lines need a full text line between ports
      // one port per line; a labelled line needs room for its label above it
      n._gap = (e) => (e && e.label ? up(wrap(e.label, FONT.edge, e.wrap || 80).length * FONT.edge * FONT.lineHeight + 3, G) : G);
      const need = outOf(n).reduce((h, e) => h + n._gap(e), hasIn(n) ? G : 0);
      n.h = up(Math.max(n.h, need + 2 * G), 12);
    }
    n.w = up(n.w, 12);
  }
  const E = spec.edges;
  const deg = Object.fromEntries(nodes.map((n) => [n.id, 0]));
  for (const e of E) { deg[e.from]++; deg[e.to]++; }

  // ----- placement -----
  const avail = availIn - 36; // room for a lane outside the first and last column
  const colH = (c) => c.reduce((h, t) => h + t.h + VGAP + (t.gapBefore || 0), 0);
  function geometry(cols) {
    const colW = cols.map((c) => Math.max(0, ...c.map((t) => t.w)));
    let x = 0; const colX = [];
    let last = 0;
    cols.forEach((c, i) => { colX[i] = x; if (c.length) { last = spec.gutters?.[i] ?? GUT; x += colW[i] + last; } });
    const heights = cols.map((c) => colH(c) - VGAP);
    return { colW, colX, width: x - last, heights };
  }
  function cost(cols) {
    const g = geometry(cols), pos = {};
    cols.forEach((c, i) => { let y = 0; for (const t of c) { pos[t.id] = { y: y + t.h / 2, i }; y += t.h + VGAP; } });
    let len = 0;
    for (const e of E) {
      const a = pos[e.from], b = pos[e.to], hop = Math.abs(a.i - b.i);
      len += Math.abs(a.y - b.y) + hop * 160 + (hop > 1 ? (hop - 1) * 260 : 0);
    }
    return len + Math.max(...g.heights) * (spec.level ?? 20) + Math.max(0, g.width - avail) * 50;
  }
  function search(C) {
    const rand = rng(20261111 + C);
    const order = [...nodes].sort((a, b) => deg[b.id] - deg[a.id] || a.id.localeCompare(b.id));
    let cols = Array.from({ length: C }, () => []);
    for (const t of order) cols.reduce((m, c) => (colH(c) < colH(m) ? c : m)).push(t);
    let cur = cost(cols), bestCols = cols.map((c) => [...c]), bestCost = cur;
    const N = spec.iterations ?? 14000;
    for (let it = 0; it < N; it++) {
      const temp = 400 * (1 - it / N), next = cols.map((c) => [...c]);
      const a = Math.floor(rand() * C), b = Math.floor(rand() * C);
      if (!next[a].length) continue;
      const i = Math.floor(rand() * next[a].length);
      if (rand() < 0.5 && next[b].length) {
        const j = Math.floor(rand() * next[b].length);
        [next[a][i], next[b][j]] = [next[b][j], next[a][i]];
      } else {
        const [t] = next[a].splice(i, 1);
        next[b].splice(Math.floor(rand() * (next[b].length + 1)), 0, t);
      }
      const c2 = cost(next);
      if (c2 < cur || rand() < Math.exp((cur - c2) / Math.max(1, temp))) {
        cols = next; cur = c2;
        if (c2 < bestCost) { bestCost = c2; bestCols = next.map((c) => [...c]); }
      }
    }
    return bestCols.filter((c) => c.length);
  }
  let cols;
  if (Array.isArray(spec.columns)) {
    cols = spec.columns.map((c) => {
      const out = []; let gap = 0;
      for (const item of c) {
        if (typeof item === 'number') { gap += item; continue; }
        if (!by[item]) throw new Error(`${spec.id}: column names unknown node ${item}`);
        by[item].gapBefore = gap; gap = 0; out.push(by[item]);
      }
      return out;
    });
    const placed = new Set(cols.flat().map((n) => n.id));
    for (const n of nodes) if (!placed.has(n.id)) throw new Error(`${spec.id}: node ${n.id} is in no column`);
  } else {
    const widest = Math.max(...nodes.map((t) => t.w));
    let C = spec.columnCount || Math.max(1, Math.floor((avail + GUT) / (widest * 0.82 + GUT)));
    for (; C >= 1; C--) { cols = search(C); if (geometry(cols).width <= avail || C === 1) break; }
  }
  const geo = geometry(cols);
  const totalW = geo.width, totalH = Math.max(...geo.heights);
  cols.forEach((c, i) => {
    let y = spec.align === 'center' ? up((totalH - geo.heights[i]) / 2, 12) : 0;
    for (const t of c) {
      y += t.gapBefore || 0;
      if (t.shape !== 'actor' && t.shape !== 'note' && !t.natural) t.w = geo.colW[i]; // one width per column
      t.x = geo.colX[i] + (geo.colW[i] - t.w) / 2; t.y = y; y += t.h + VGAP;
    }
  });

  // ----- ports -----
  const rowY = (t, field) => {
    let i = 0, sec = 0;
    for (const s of t.sections || []) {
      for (const r of s) { if (typeof r !== 'string' && r.k === field) return t.y + t._head + 3 + 6 + 12 * i + 6 * sec; i++; }
      if (s.length) sec++;
    }
    return null;
  };
  const cyG = (n) => Math.round((n.y + n.h / 2) / G) * G;
  // two nodes one above the other in a column are joined by a straight vertical line
  const colOf = {}, rowOf = {};
  cols.forEach((c, i) => c.forEach((n, j) => { colOf[n.id] = i; rowOf[n.id] = j; }));
  const vertical = (e) => spec.kind !== 'erd' && e.from !== e.to && colOf[e.from] === colOf[e.to] && Math.abs(rowOf[e.from] - rowOf[e.to]) === 1;
  for (const n of nodes) {
    if (n.shape === 'table') continue;
    const outs = outOf(n).filter((e) => !vertical(e)).sort((a, b) => cyG(by[a.to]) - cyG(by[b.to]));
    if (n.shape === 'class') { // a class has one port per line end, down its side
      const ends = spec.edges.filter((e) => !vertical(e) && (e.from === n.id || e.to === n.id) && e.from !== e.to)
        .sort((a, b) => cyG(by[a.from === n.id ? a.to : a.from]) - cyG(by[b.from === n.id ? b.to : b.from]));
      ends.forEach((e, i) => { const y = n.y + 12 + 12 * i; if (e.from === n.id) e.sy = y; else e.ty = y; });
      continue;
    }
    const incoming = spec.edges.some((e) => e.to === n.id && !vertical(e));
    const slots = [...(incoming ? [null] : []), ...outs];
    // each port sits below the room its label needs; the stack is centred on the node
    const total = slots.reduce((h, e) => h + n._gap(e), 0);
    let y = Math.round((n.y + n.h / 2 - total / 2) / G) * G - G / 2 + G / 2;
    for (const e of slots) { y += n._gap(e); if (e) e.sy = y; else n._inY = y; }
  }
  const groups = new Map();
  for (const e of E) {
    const s = by[e.from], t = by[e.to];
    const key = e.mFrom || e.mTo || e.solo || t.shape === 'class' && e.head !== 'tri' ? 'solo' + groups.size : `${e.to}|${e.head ?? 'arrow'}|${e.dash ? 1 : 0}`;
    if (!groups.has(key)) groups.set(key, groups.size);
    e.group = groups.get(key);
    if (s.shape === 'table') e.sy = (e.field && rowY(s, e.field)) ?? s.y + 12;
    if (t.shape === 'table') e.ty = e.head === 'one' || !t.sections?.[0]?.length ? t.y + 12 : t.y + t._head + 9;
    else if (t.shape !== 'class') e.ty = t._inY;
    else if (e.head === 'tri') e.ty = t.y + 12; // every implementer meets at one triangle
    if (e.label) {
      e._lines = wrap(e.label, FONT.edge, e.wrap || 80);
      e._lw = Math.max(...e._lines.map((l) => tw(l, FONT.edge)));
      e._lh = e._lines.length * FONT.edge * FONT.lineHeight;
    }
  }

  // ----- routing grid -----
  const x0 = -18, y0 = -18;
  const NX = Math.round((totalW + 36) / G) + 1, NY = Math.round((totalH + 36) / G) + 1;
  const idx = (ix, iy) => iy * NX + ix;
  const gx = (ix) => x0 + ix * G, gy = (iy) => y0 + iy * G;
  const cellOf = (x, y) => [Math.round((x - x0) / G), Math.round((y - y0) / G)];
  const blocked = new Uint8Array(NX * NY), soft = new Uint8Array(NX * NY); // soft: under a label, avoided but not forbidden
  const block = (x1, y1, x2, y2, arr = blocked) => {
    for (let iy = 0; iy < NY; iy++) for (let ix = 0; ix < NX; ix++) {
      const px = gx(ix), py = gy(iy);
      if (px > x1 && px < x2 && py > y1 && py < y2) arr[idx(ix, iy)] = 1;
    }
  };
  for (const t of nodes) block(t.x - STUB, t.y - G, t.x + t.w + STUB, t.y + t.h + G);
  const hUse = new Int32Array(NX * NY).fill(-1), vUse = new Int32Array(NX * NY).fill(-1);
  const corner = new Int32Array(NX * NY).fill(-1);
  const DX = [1, 0, -1, 0], DY = [0, 1, 0, -1];
  const span = (e) => Math.abs(by[e.from].x - by[e.to].x) + Math.abs(e.sy - e.ty);
  const order = [...E].sort((a, b) => (b.label ? 1 : 0) - (a.label ? 1 : 0) || span(a) - span(b));
  const dots = [];
  for (const e of E.filter(vertical)) {
    const s = by[e.from], t = by[e.to];
    // two lines between the same pair (one each way) run side by side
    const pair = E.filter((q) => vertical(q) && ((q.from === e.from && q.to === e.to) || (q.from === e.to && q.to === e.from)));
    const k = pair.indexOf(e), x = Math.round((s.x + s.w / 2 + (k - (pair.length - 1) / 2) * 24) / G) * G;
    const down = t.y > s.y, y1 = down ? s.y + s.h : s.y, y2 = down ? t.y : t.y + t.h;
    e.pts = [{ x, y: y1 }, { x, y: y2 }];
    const [ix, iy1] = cellOf(x, Math.min(y1, y2)), iy2 = cellOf(x, Math.max(y1, y2))[1];
    for (let iy = iy1; iy < iy2; iy++) vUse[idx(ix, iy)] = 1e6 + ix;
    if (e.label) {
      const left = pair.length > 1 && k === 0, lx = left ? x - 5 - e._lw : x + 5, my = (y1 + y2) / 2;
      e.lbl = { x: lx - 1, y: my - e._lh / 2, w: e._lw + 2, h: e._lh + 1 };
      block(lx - 3, my - e._lh / 2 - 3, lx + e._lw + 3, my + e._lh / 2 + 3, soft);
    }
  }

  for (const e of order) {
    if (vertical(e)) continue;
    const s = by[e.from], t = by[e.to];
    // a labelled line first runs straight under its label; if there is no room, it keeps the short run
    let end = -1, cells = [], startPort, goalIdx;
    const ci = colOf[e.from];
    const room = (side) => { // how far a straight run may go before the next column's nodes
      const g = side === 0 ? (ci < cols.length - 1 ? spec.gutters?.[ci] ?? GUT : 1e6) : (ci > 0 ? spec.gutters?.[ci - 1] ?? GUT : 1e6);
      return Math.floor((g - 18) / G) * G;
    };
    for (const want of e.label ? [up(e._lw + 10, G), STUB] : [STUB]) {
      const starts = [[s.x - Math.min(want, room(2)), 2, s.x, Math.min(want, room(2))], [s.x + s.w + Math.min(want, room(0)), 0, s.x + s.w, Math.min(want, room(0))]];
      const goals = [[t.x - STUB, t.x], [t.x + t.w + STUB, t.x + t.w]];
      goalIdx = new Map();
      for (const g of goals) { const [ix, iy] = cellOf(g[0], e.ty); if (ix >= 0 && ix < NX) goalIdx.set(idx(ix, iy), g); }
      const D = new Float64Array(NX * NY * 4).fill(Infinity), prev = new Int32Array(NX * NY * 4).fill(-1);
      const heap = [];
      const push = (k, d) => { heap.push([d, k]); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
      const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { let m = i; const l = 2 * i + 1, r = l + 1; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
      startPort = new Map();
      for (const [px, dir, portX, run] of starts) {
        const [ix, iy] = cellOf(px, e.sy);
        if (ix < 0 || ix >= NX) continue;
        const c = idx(ix, iy);
        if (blocked[c] && !goalIdx.has(c)) continue;
        // the straight run must be free too
        let clear = true;
        for (let q = STUB; q < run; q += G) { const [jx, jy] = cellOf(portX + (dir === 0 ? q : -q), e.sy); if (blocked[idx(jx, jy)] || vUse[idx(jx, jy)] !== -1 || (jy > 0 && vUse[idx(jx, jy - 1)] !== -1)) clear = false; }
        if (!clear) continue;
        const d0 = corner[c] !== -1 && corner[c] !== e.group ? 30 : 0;
        D[c * 4 + dir] = d0; push(c * 4 + dir, d0); startPort.set(c, portX);
      }
      end = -1;
      while (heap.length) {
        const [d, k] = pop();
        if (d > D[k]) continue;
        const cell = k >> 2, dir = k & 3;
        if (goalIdx.has(cell)) { end = k; break; }
        const ix = cell % NX, iy = (cell / NX) | 0;
        for (let nd = 0; nd < 4; nd++) {
          if (((nd + 2) & 3) === dir) continue;
          const jx = ix + DX[nd], jy = iy + DY[nd];
          if (jx < 0 || jy < 0 || jx >= NX || jy >= NY) continue;
          const nc = idx(jx, jy);
          if (blocked[nc] && !goalIdx.has(nc)) continue;
          let c = 1;
          if (nd !== dir) c += 7 + (corner[cell] !== -1 && corner[cell] !== e.group ? 20 : 0);
          const seg = nd === 0 ? hUse[cell] : nd === 2 ? hUse[nc] : nd === 1 ? vUse[cell] : vUse[nc];
          if (seg !== -1) c += seg === e.group ? -0.7 : 60;
          const horiz = nd === 0 || nd === 2;
          const u1 = horiz ? (jy > 0 ? vUse[idx(jx, jy - 1)] : -1) : (jx > 0 ? hUse[idx(jx - 1, jy)] : -1);
          const u2 = horiz ? vUse[nc] : hUse[nc];
          if ((u1 !== -1 && u1 !== e.group) || (u2 !== -1 && u2 !== e.group)) c += 4;
          if (corner[nc] !== -1 && corner[nc] !== e.group) c += 25;
          if (soft[nc]) c += 45;
          const nk = nc * 4 + nd, nd2 = d + c;
          if (nd2 < D[nk]) { D[nk] = nd2; prev[nk] = k; push(nk, nd2); }
        }
      }
      if (end !== -1) { for (let k = end; k !== -1; k = prev[k]) cells.push(k >> 2); cells.reverse(); break; }
    }
    if (end === -1) throw new Error(`${spec.id}: no route for ${e.from} -> ${e.to}${e.label ? ' (label needs a wider gutter)' : ''}`);
    let joined = false;
    for (let i = 0; i < cells.length - 1; i++) {
      const a = cells[i], b = cells[i + 1], h = Math.abs(a - b) === 1, lo = Math.min(a, b);
      const used = (h ? hUse[lo] : vUse[lo]) === e.group;
      if (used && !joined && i > 0) { joined = true; dots.push({ x: gx(a % NX), y: gy((a / NX) | 0) }); }
      if (h) hUse[lo] = e.group; else vUse[lo] = e.group;
    }
    for (let i = 0; i < cells.length; i++) {
      const p = cells[i - 1], c = cells[i], n = cells[i + 1];
      if (p === undefined || n === undefined || (c - p) !== (n - c)) corner[c] = e.group;
    }
    const g = goalIdx.get(cells[cells.length - 1]), portX = startPort.get(cells[0]);
    const pts = [{ x: portX, y: e.sy }, ...cells.map((c) => ({ x: gx(c % NX), y: gy((c / NX) | 0) })), { x: g[1], y: e.ty }];
    e.pts = simplify(pts);
    if (e.label) {
      const right = gx(cells[0] % NX) > portX;
      const lx = right ? portX + 7 : portX - 7 - e._lw;
      e.lbl = { x: lx - 1, y: e.sy - e._lh - 2.5, w: e._lw + 2, h: e._lh + 1 };
      block(lx - 4, e.sy - e._lh - 6, lx + e._lw + 4, e.sy - 1, soft);
      // the straight run itself stays reserved for this line
      for (let q = STUB; q < Math.abs(gx(cells[0] % NX) - portX); q += G) { const [jx, jy] = cellOf(portX + (right ? q : -q), e.sy); hUse[idx(right ? jx - 1 : jx, jy)] = e.group; corner[idx(jx, jy)] = e.group; }
    }
  }

  // ----- frames around named groups of nodes -----
  const frames = (spec.groups || []).map((g) => {
    const m = g.members.map((id) => { if (!by[id]) throw new Error(`${spec.id}: group ${g.id} names unknown node ${id}`); return by[id]; });
    const pad = g.pad ?? 9, // between two routing lanes, so no line runs along a frame's edge
      x = Math.min(...m.map((n) => n.x)) - pad, y = Math.min(...m.map((n) => n.y)) - pad - (g.label ? 14 : 0);
    const f = { id: g.id, shape: 'group', label: g.label, tone: g.tone, dashed: g.dashed, x, y, w: Math.max(...m.map((n) => n.x + n.w)) + pad - x, h: Math.max(...m.map((n) => n.y + n.h)) + pad - y };
    measure(f);
    return f;
  });
  return { nodes: [...frames, ...nodes], edges: E, dots };
}

function simplify(pts) {
  const out = [pts[0]];
  for (let i = 1; i < pts.length - 1; i++) {
    const a = out[out.length - 1], b = pts[i], c = pts[i + 1];
    if ((a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y)) continue;
    out.push(b);
  }
  out.push(pts[pts.length - 1]);
  return out;
}
