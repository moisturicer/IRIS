#!/usr/bin/env python3
"""Resolve a TRACEABILITY.md merge conflict cell-by-cell.

The matrix is a Markdown table whose rows are single, very long lines, so two
branches that each append a note to the same requirement collide on the whole
row even though they touched different sentences. Git cannot see inside a line;
this can. For every conflicted row it splits both sides on `|`, and where only
one side changed a cell it takes that side, where both changed it it splices
both sets of edits in, provided each side only *inserted* text. Inserts are
replayed in offset order (ours first on a tie), so each note keeps the position
its author chose. If either side rewrote or deleted existing text, or a
conflict block holds anything but table rows, the block is left for a human.

Everything outside a conflict block is git's own successful merge and is
copied through untouched.

Usage (during a merge):  python scripts/resolve_traceability.py
"""
import difflib
import re
import subprocess
import sys

PATH = "docs/testing/TRACEABILITY.md"


def stage(n):
    """One side of the conflict as git recorded it, or None."""
    out = subprocess.run(["git", "show", f":{n}:{PATH}"], capture_output=True)
    if out.returncode:
        return None
    return out.stdout.decode("utf-8").replace("\r\n", "\n").split("\n")


def row_key(line):
    """The requirement id in column 1, e.g. FR-M3-02, or None."""
    m = re.match(r"\|\s*\**\s*([A-Z]+-[A-Za-z0-9.\-\u2026, ]+?)\s*\**\s*\|", line)
    return m.group(1).strip() if m else None


def inserts(base, side):
    """Every contiguous insert `side` made into `base`, or None if it did
    anything else. A pure-insert edit is safe to replay alongside another;
    a replace or delete means the two sides disagree about existing text."""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, base, side, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            return None
        out.append((i1, side[j1:j2]))
    return out


def merge_row(b, o, t):
    """One table row merged cell by cell, or None if a human must decide."""
    bf, of, tf = b.split("|"), o.split("|"), t.split("|")
    if not (len(bf) == len(of) == len(tf)):
        return None
    out = []
    for cb, co, ct in zip(bf, of, tf):
        if co == ct or ct == cb:
            out.append(co)
        elif co == cb:
            out.append(ct)
        else:
            ins_o, ins_t = inserts(cb, co), inserts(cb, ct)
            if ins_o is None or ins_t is None:
                return None
            # Ours before theirs at the same offset; otherwise offset order.
            marked = [(off, 0, txt) for off, txt in ins_o]
            marked += [(off, 1, txt) for off, txt in ins_t]
            cell, prev = [], 0
            for off, _, txt in sorted(marked, key=lambda x: (x[0], x[1])):
                cell.append(cb[prev:off])
                cell.append(txt)
                prev = off
            cell.append(cb[prev:])
            out.append("".join(cell))
    return "|".join(out)


def main():
    base, ours, theirs = stage(1), stage(2), stage(3)
    if not all((base, ours, theirs)):
        sys.exit(f"{PATH} is not in a conflicted merge")

    def index(lines):
        return {k: ln for ln in lines if (k := row_key(ln))}

    bi, oi, ti = index(base), index(ours), index(theirs)

    with open(PATH, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")

    out, resolved, unresolved, i = [], [], [], 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<<"):
            out.append(lines[i])
            i += 1
            continue
        try:
            mid = next(j for j in range(i, len(lines))
                       if lines[j].startswith("======="))
            end = next(j for j in range(mid, len(lines))
                       if lines[j].startswith(">>>>>>>"))
        except StopIteration:
            sys.exit(f"{PATH}: malformed conflict block at line {i + 1}")

        our_rows = lines[i + 1:mid]
        their_rows = lines[mid + 1:end]
        merged = None
        if all(row_key(x) for x in our_rows + their_rows):
            merged, seen = [], set()
            for key in [row_key(x) for x in our_rows]:
                b, o, t = bi.get(key), oi.get(key), ti.get(key)
                if key in seen or None in (b, o, t):
                    merged = None
                    break
                seen.add(key)
                line = o if o == t else merge_row(b, o, t)
                if line is None:
                    merged = None
                    break
                merged.append(line)

        if merged is None:
            unresolved.append(f"block at line {i + 1}")
            out.extend(lines[i:end + 1])      # leave it for a human
        else:
            resolved.extend(row_key(x) for x in our_rows)
            out.extend(merged)
        i = end + 1

    with open(PATH, "w", encoding="utf-8", newline="") as fh:
        fh.write(newline.join(out))

    for k in resolved:
        print(f"  merged  {k}")
    for k in unresolved:
        print(f"  MANUAL  {k}")
    if unresolved:
        sys.exit(1)
    subprocess.run(["git", "add", PATH], check=True)
    print(f"{PATH}: {len(resolved)} row(s) resolved and staged")


if __name__ == "__main__":
    main()
