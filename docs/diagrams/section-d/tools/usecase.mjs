// Use case diagram layout (D-1 to D-7).
// Deterministic: actors left and right, one column of use cases inside the
// system boundary. Actor links run through lanes outside the boundary,
// dependencies between use cases through lanes inside it, on the right.
import { FONT } from './style.mjs';

export function layoutUsecase(spec, { measure, tw }) {
  const cases = spec.cases.map((c) => ({ ...c, shape: 'usecase' }));
  const left = (spec.left || []).map((a) => ({ ...a, shape: 'actor', side: 'L' }));
  const right = (spec.right || []).map((a) => ({ ...a, shape: 'actor', side: 'R' }));
  const notes = (spec.notes || []).map((n, i) => ({
    id: 'note' + i, shape: 'note', label: n.text, on: n.on, side: n.side === 'left' ? 'L' : 'R', wrap: n.wrap || 150,
  }));
  const all = [...cases, ...left, ...right, ...notes];
  all.forEach(measure);
  const by = Object.fromEntries(all.map((n) => [n.id, n]));
  const need = (id) => { if (!by[id]) throw new Error(`${spec.id}: unknown id ${id}`); return by[id]; };
  const links = spec.links.flatMap(([a, ...ucs]) => ucs.map((u) => ({ a: need(a), u: need(u) })));
  const LANE = 7;
  // stretch the column when a side column of actors is taller than it
  const sideH = (list) => list.reduce((h, n) => h + n.h + 10, -10);
  const tallest = Math.max(sideH(left), sideH([...right, ...notes]));
  const packed = cases.reduce((h, c) => h + c.h, 0);
  const GAP = Math.max(spec.gap ?? 7, cases.length > 1 ? (tallest - 20 - packed) / (cases.length - 1) : 0);

  // the column of use cases
  const colW = Math.max(...cases.map((c) => c.w));
  let y = 24;
  for (const c of cases) { c.y = y; y += c.h + GAP; }
  const sysH = y - GAP + 10;
  const cyOf = (n) => n.y + n.h / 2;

  // side columns: each actor or note sits level with what it connects to
  const wantOf = (n) => {
    if (n.shape === 'note') return cyOf(need(n.on));
    const ys = links.filter((l) => l.a === n).map((l) => cyOf(l.u));
    return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : sysH / 2;
  };
  const place = (list) => {
    list.forEach((n) => { n._want = wantOf(n) - n.h / 2; });
    list.sort((a, b) => a._want - b._want);
    let prev = -Infinity;
    for (const n of list) { n.y = Math.max(n._want, prev); prev = n.y + n.h + 10; }
    let next = Math.max(sysH, prev);
    for (const n of [...list].reverse()) { if (n.y + n.h > next) n.y = next - n.h; next = n.y - 10; }
  };
  const L = [...left, ...notes.filter((n) => n.side === 'L')];
  const R = [...right, ...notes.filter((n) => n.side === 'R')];
  place(L); place(R);
  const lActors = L.filter((n) => n.shape === 'actor'), rActors = R.filter((n) => n.shape === 'actor');

  // dependencies: the same source and label share one trunk and one label
  const groups = [];
  for (const d of spec.deps || []) {
    let g = groups.find((x) => x.from === d.from && x.label === d.label);
    if (!g) groups.push(g = { from: d.from, label: d.label, tos: [] });
    g.tos.push(d.to);
  }
  const isSrc = new Set(groups.map((g) => g.from)), isTgt = new Set(groups.flatMap((g) => g.tos));
  // right-hand ports of a use case, top to bottom: dependency out, actor, dependency in
  const hasR = (id) => links.some((l) => l.u.id === id && l.a.side === 'R') || (spec.notes || []).some((n) => n.on === id && n.side !== 'left');
  const kinds = (id) => [isSrc.has(id), hasR(id), isTgt.has(id)];
  const port = (id, kind) => {
    const k = kinds(id), n = k.filter(Boolean).length, idx = k.slice(0, kind).filter(Boolean).length;
    return cyOf(need(id)) + (idx - (n - 1) / 2) * 6;
  };
  const srcY = (id) => port(id, 0);
  const tgtY = (id) => port(id, 2);
  for (const g of groups) {
    const ys = [srcY(g.from), ...g.tos.map(tgtY)];
    g.lo = Math.min(...ys); g.hi = Math.max(...ys);
  }
  const laneUse = [];
  for (const g of [...groups].sort((a, b) => (a.hi - a.lo) - (b.hi - b.lo))) {
    let k = 0;
    while (laneUse[k] && laneUse[k].some((o) => g.lo <= o.hi + 8 && o.lo <= g.hi + 8)) k++;
    (laneUse[k] ||= []).push(g); g.lane = k;
  }
  const nDep = laneUse.length;

  // x geometry, left to right
  const lw = Math.max(0, ...L.map((n) => n.w)), lLane0 = lw + 10;
  const sysX = lLane0 + Math.max(0, lActors.length - 1) * LANE + (lActors.length ? 10 : 0);
  const colX = sysX + 12, cx = colX + colW / 2;
  const labelW = Math.max(0, ...groups.map((g) => tw(g.label, FONT.edge)));
  const dLane0 = colX + colW + (nDep ? labelW + 12 : 0);
  const sysR = nDep ? dLane0 + (nDep - 1) * 8 + 12 : colX + colW + 12;
  const rLane0 = sysR + 10, rColX = rLane0 + Math.max(0, rActors.length - 1) * LANE + 10;
  for (const c of cases) c.x = cx - c.w / 2;
  for (const n of L) n.x = lw - n.w;
  for (const n of R) n.x = rColX;
  const tip = (c, yy, sign) => { // x on the ellipse outline at height yy
    const dy = Math.min(0.98, Math.abs(yy - cyOf(c)) / (c.h / 2));
    return cx + sign * (c.w / 2) * Math.sqrt(1 - dy * dy);
  };

  const edges = [];
  for (const [list, sign, lane0] of [[lActors, -1, lLane0], [rActors, 1, rLane0]]) {
    list.forEach((a, i) => {
      const lx = sign < 0 ? lane0 + i * LANE : lane0 + (list.length - 1 - i) * LANE;
      const ay = a.y + 13, ax = a.x + a.w / 2 + sign * -9;
      for (const l of links.filter((q) => q.a === a)) {
        const same = links.filter((q) => q.u === l.u && q.a.side === a.side).sort((p, q) => p.a.y - q.a.y);
        const k = same.findIndex((q) => q.a === a);
        const py = (sign > 0 ? port(l.u.id, 1) : cyOf(l.u)) + (k - (same.length - 1) / 2) * 6;
        edges.push({ pts: [{ x: ax, y: ay }, { x: lx, y: ay }, { x: lx, y: py }, { x: tip(l.u, py, sign), y: py }], head: 'none' });
      }
    });
  }
  for (const g of groups) {
    const s = need(g.from), lx = dLane0 + g.lane * 8, sy = srcY(g.from);
    g.tos.forEach((to, i) => {
      const t = need(to), ty = tgtY(to);
      const e = { pts: [{ x: tip(s, sy, 1), y: sy }, { x: lx, y: sy }, { x: lx, y: ty }, { x: tip(t, ty, 1), y: ty }], head: 'arrow', dash: true };
      if (i === 0) {
        const w = tw(g.label, FONT.edge);
        e._lines = [g.label];
        e.lbl = { x: dLane0 - 5 - w, y: sy - 11.5, w: w + 2, h: 10.5 };
      }
      edges.push(e);
    });
  }
  for (const n of notes) {
    const u = need(n.on), sign = n.side === 'L' ? -1 : 1, py = sign > 0 ? port(u.id, 1) : cyOf(u);
    const nx = sign < 0 ? n.x + n.w : n.x, ny = Math.min(Math.max(py, n.y + 4), n.y + n.h - 4);
    const mid = sign < 0 ? lLane0 - 5 : rLane0 - 5;
    edges.push({ pts: [{ x: tip(u, py, sign), y: py }, { x: mid, y: py }, { x: mid, y: ny }, { x: nx, y: ny }], head: 'none', dash: true });
  }
  // an actor that is a kind of another actor: lanes left of the actor column
  const gens = spec.gens || [];
  if (gens.length) {
    const laneOf = {};
    const x0 = Math.min(...L.map((n) => n.x)) - 8;
    for (const [c, p] of gens) {
      if (!(p in laneOf)) laneOf[p] = Object.keys(laneOf).length;
      const a = need(c), b = need(p), x = x0 - laneOf[p] * 8;
      // leaves from the child's body, arrives at the parent's arm, so the two never overlap
      const out = { x: a.x + a.w / 2, y: a.y + 17 }, into = { x: b.x + b.w / 2 - 9, y: b.y + 12.5 };
      edges.push({ pts: [out, { x, y: out.y }, { x, y: into.y }, into], head: 'tri' });
    }
  }
  const sys = { id: 'sys', shape: 'group', tone: 'plain', label: spec.system, x: sysX, y: 0, w: sysR - sysX, h: sysH };
  measure(sys);
  return { nodes: [sys, ...all], edges };
}
