"""Comparing two Versions' review texts (ADR-058 §3, IR-873). Pure: two
readings in, a comparison out, no database and no clock, so the same two
readings always give the same result.

A reading is the dict `review_text.store` stores and serves: ``page_count``,
``warnings`` and ``sections``, each section with ``key``, ``heading``,
``page``, ``text_hash`` and ``passages`` (``text``, ``page``, ``regions``).
Both readings must come from one reader (`review_text.readings.pair`); this
module doesn't check, because it is never told which reader made them.

Matching, in stages:

1. a section whose ``text_hash`` is the same on both sides is unchanged;
2. sections are paired by ``key`` (the heading without its numbering), then
   by their content when the heading changed, which reads *renamed*;
3. inside a pair, passages are matched exactly after normalisation, then a
   reworded passage is paired with the most similar one (`difflib`);
4. **any difference after normalisation is *changed*,** never *unchanged*
   because it is similar enough, and the words that differ are marked, so a
   changed number, term or citation always shows;
5. what is left is *added* or *removed*, and a passage removed in one place
   and added word for word in another is *moved*.

When a side's sections couldn't be identified (``sections_unreliable``), the
whole paper is compared in one pass and changes are listed by page. When the
amount of text looks wrong, the comparison says so, and the changes that could
be text the reader missed are marked ``tentative``.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher


def _reader_norm(text: str) -> str:
    """The reader's own normalisation (`reader.norm`): compatibility forms
    (ligatures), straight quotes and single spaces. Repeated here because the
    reader runs only in the sandbox and is never imported into this process;
    `test_comparison.py` fails the day the two differ."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


#: A hyphen between two letters. The reader decides whether a word broken at a
#: line end keeps its hyphen from the paper's own spellings, so the same words
#: can read "small-scale" in one Version and "smallscale" in the next because
#: an unrelated paragraph was removed (found on the drawn pairs, IR-873).
#: ADR-058 §3 normalises hyphenation before matching; between digits a hyphen
#: is kept, so "2-3" and "23" still differ.
LETTER_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")


def norm(text: str) -> str:
    """Text as matched, never as shown: the reader's normalisation, without
    hyphens between letters."""
    return LETTER_HYPHEN.sub("", _reader_norm(text))

#: Raised whenever the matching below changes, so a result can be told apart
#: from one an earlier version of this module gave. Never shown to users.
COMPARISON_VERSION = 1

#: How much of two sections' words must be shared to pair them when their
#: headings differ (a renamed section).
SECTION_MATCH = 0.6
#: How similar two passages must be to read as one passage *changed* rather
#: than one *removed* and another *added*.
PASSAGE_MATCH = 0.6
#: How many new passages ahead a reworded one is looked for. Pairing keeps
#: order, so a rewrite is near where it was; the bound keeps a long rewritten
#: run from costing every passage against every other.
PAIR_WINDOW = 25
#: A change in the number of words beyond this share, while the page count
#: stays within `PAGE_STEADY`, suggests text a reader missed, not an edit.
TEXT_JUMP = 0.4
PAGE_STEADY = 0.1

ESTABLISHED, TENTATIVE = "established", "tentative"
CHANGED, ADDED, REMOVED, MOVED = "changed", "added", "removed", "moved"
UNCHANGED, REPLACED = "unchanged", "replaced"


# --- the comparison -------------------------------------------------------------

def compare(old: dict, new: dict) -> dict:
    """Compare reading ``old`` (the earlier Version) with ``new``."""
    notices, doubtful_side = _notices(old, new)
    by_page = any(_unreliable(r) for r in (old, new))
    if by_page:
        changes = _merge_moves_in_list(_diff_passages(_flat(old), _flat(new)))
        result = {"mode": "pages", "changes": changes, "sections": []}
        every_change = changes
    else:
        sections = _compare_sections(old["sections"], new["sections"])
        _merge_moves_in_sections(sections)
        result = {"mode": "sections", "sections": sections, "changes": []}
        every_change = _unique(c for s in sections for c in s["changes"])
    if doubtful_side:
        _mark_tentative(every_change, doubtful_side)
    counts = _counts(every_change)
    counts["sections_renamed"] = sum(s["renamed"] for s in result["sections"])
    counts["sections_moved"] = sum(s["moved"] for s in result["sections"])
    result.update({
        "comparison_version": COMPARISON_VERSION,
        "notices": notices,
        "counts": counts,
    })
    return result


def _unreliable(reading) -> bool:
    return any(w.get("code") == "sections_unreliable" for w in reading.get("warnings", []))


def _flat(reading) -> list:
    return [(s["key"], p) for s in reading["sections"] for p in s["passages"]]


# --- sections -------------------------------------------------------------------

def _tokens(section) -> Counter:
    return Counter(w for p in section["passages"] for w in norm(p["text"]).lower().split())


def _overlap(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    return sum((a & b).values()) / max(sum(a.values()), sum(b.values()))


def _compare_sections(old: list, new: list) -> list:
    new_index = {s["key"]: j for j, s in enumerate(new)}
    pairs, used = {}, set()            # old index -> (new index, renamed)
    for i, s in enumerate(old):
        j = new_index.get(s["key"])
        if j is not None:
            pairs[i] = (j, False)
            used.add(j)
    # A heading that changed: pair by content, best first, never below the bar.
    old_left = [i for i in range(len(old)) if i not in pairs]
    new_left = [j for j in range(len(new)) if j not in used]
    tokens_old = {i: _tokens(old[i]) for i in old_left}
    tokens_new = {j: _tokens(new[j]) for j in new_left}
    candidates = sorted(
        ((_overlap(tokens_old[i], tokens_new[j]), -i, -j) for i in old_left for j in new_left),
        reverse=True,
    )
    for score, i, j in candidates:
        i, j = -i, -j
        if score < SECTION_MATCH:
            break
        if i not in pairs and j not in used:
            pairs[i] = (j, True)
            used.add(j)

    moved = _out_of_order(pairs)
    out = []
    for j, section in enumerate(new):
        i = next((i for i, (jj, _) in pairs.items() if jj == j), None)
        if i is None:
            out.append(_section(None, section, ADDED, [
                _change(ADDED, None, (section["key"], p)) for p in section["passages"]
            ]))
            continue
        before, renamed = old[i], pairs[i][1]
        if before["text_hash"] == section["text_hash"]:
            changes = []
        else:
            changes = _diff_passages(
                [(before["key"], p) for p in before["passages"]],
                [(section["key"], p) for p in section["passages"]],
            )
        # A renamed heading is a change to the paper even with every passage kept.
        entry = _section(before, section, CHANGED if changes or renamed else UNCHANGED, changes)
        entry["renamed"], entry["moved"] = renamed, i in moved
        out.append(entry)
    # Removed sections, placed after the section that came before them.
    for i, section in enumerate(old):
        if i in pairs:
            continue
        removed = _section(section, None, REMOVED, [
            _change(REMOVED, (section["key"], p), None) for p in section["passages"]
        ])
        out.insert(_position_after(out, old, i), removed)
    for entry in out:
        entry["counts"] = _counts(entry["changes"])
    return out


def _position_after(out, old, i) -> int:
    """Where removed section ``i`` goes: after the nearest earlier old section
    still shown, so it reads where it used to be."""
    for k in range(i - 1, -1, -1):
        for n, entry in enumerate(out):
            if entry["from"] is not None and entry["from"]["key"] == old[k]["key"]:
                return n + 1
    return 0


def _out_of_order(pairs: dict) -> set:
    """The old indices whose sections moved: those outside the longest run of
    pairs that keeps its order in both Versions."""
    items = sorted(pairs.items())                     # by old index
    js = [j for _, (j, _) in items]
    keep = set(_longest_increasing(js))
    return {items[k][0] for k in range(len(items)) if k not in keep}


def _longest_increasing(seq) -> list:
    """Positions of one longest strictly increasing subsequence of ``seq``."""
    if not seq:
        return []
    best, back = [1] * len(seq), [-1] * len(seq)
    for k in range(len(seq)):
        for m in range(k):
            if seq[m] < seq[k] and best[m] + 1 > best[k]:
                best[k], back[k] = best[m] + 1, m
    k = max(range(len(seq)), key=lambda n: best[n])
    out = []
    while k != -1:
        out.append(k)
        k = back[k]
    return out[::-1]


def _section(before, after, status, changes) -> dict:
    return {
        "status": status,
        "renamed": False,
        "moved": False,
        "from": _heading(before),
        "to": _heading(after),
        "changes": changes,
    }


def _heading(section):
    if section is None:
        return None
    return {"key": section["key"], "heading": section["heading"], "page": section["page"]}


# --- passages -------------------------------------------------------------------

def _diff_passages(old: list, new: list) -> list:
    """Changes between two lists of ``(section key, passage)``, in order."""
    a = [norm(p["text"]) for _, p in old]
    b = [norm(p["text"]) for _, p in new]
    changes = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        changes.extend(_pair_block(old, new, a, b, range(i1, i2), range(j1, j2)))
    return changes


def _pair_block(old, new, a, b, olds, news) -> list:
    """Within one run of differing passages, pair each old passage with the
    most similar new one after it, keeping order; the rest are added or removed."""
    out, start = [], news.start
    for i in olds:
        best, best_j = 0.0, None
        for j in range(start, min(news.stop, start + PAIR_WINDOW)):
            matcher = SequenceMatcher(None, a[i], b[j], autojunk=False)
            if matcher.quick_ratio() < PASSAGE_MATCH:
                continue   # an upper bound, so the exact ratio can't reach the bar
            score = matcher.ratio()
            if score > best:
                best, best_j = score, j
        if best_j is None or best < PASSAGE_MATCH:
            out.append(_change(REMOVED, old[i], None))
            continue
        out.extend(_change(ADDED, None, new[j]) for j in range(start, best_j))
        out.append(_change(CHANGED, old[i], new[best_j],
                           words=_words(old[i][1]["text"], new[best_j][1]["text"])))
        start = best_j + 1
    out.extend(_change(ADDED, None, new[j]) for j in range(start, news.stop))
    return out


def _words(a: str, b: str) -> list:
    """The two texts as runs of equal, deleted and inserted words, so the
    words that differ can be marked on both sides. Words are matched as
    `norm` matches them and shown as each Version has them."""
    ta, tb = _reader_norm(a).split(), _reader_norm(b).split()
    keys_a, keys_b = [norm(w) for w in ta], [norm(w) for w in tb]
    out = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, keys_a, keys_b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(ta[i1:i2])})
            continue
        if i2 > i1:
            out.append({"op": "delete", "text": " ".join(ta[i1:i2])})
        if j2 > j1:
            out.append({"op": "insert", "text": " ".join(tb[j1:j2])})
    return out


def _change(kind, old, new, words=None) -> dict:
    change = {"kind": kind, "certainty": ESTABLISHED, "from": _ref(old), "to": _ref(new)}
    if words is not None:
        change["words"] = words
    return change


def _ref(item):
    if item is None:
        return None
    key, passage = item
    return {"section": key, "text": passage["text"], "page": passage["page"],
            "regions": passage.get("regions", [])}


def _moves(changes: list) -> dict:
    """A passage removed in one place and added word for word elsewhere is one
    *moved* change. Maps each such removal and addition (by ``id``) to it."""
    added = {}
    for change in changes:
        if change["kind"] == ADDED:
            added.setdefault(norm(change["to"]["text"]), []).append(change)
    replaced = {}
    for change in changes:
        if change["kind"] != REMOVED:
            continue
        candidates = added.get(norm(change["from"]["text"]))
        if not candidates:
            continue
        target = candidates.pop(0)
        moved = {"kind": MOVED, "certainty": ESTABLISHED, "from": change["from"], "to": target["to"]}
        replaced[id(change)] = moved
        replaced[id(target)] = moved
    return replaced


def _merge_moves_in_list(changes: list) -> list:
    """By page: a move is listed once, at the first of its two places."""
    replaced, merged = _moves(changes), []
    for change in changes:
        new = replaced.get(id(change), change)
        if new is not change and any(m is new for m in merged):
            continue
        merged.append(new)
    return merged


def _merge_moves_in_sections(sections: list) -> None:
    """By section: a move is shown in both sections, and counted once."""
    replaced = _moves([c for s in sections for c in s["changes"]])
    if not replaced:
        return
    for section in sections:
        section["changes"] = [replaced.get(id(c), c) for c in section["changes"]]
        section["counts"] = _counts(section["changes"])


def _unique(changes) -> list:
    seen, out = set(), []
    for change in changes:
        if id(change) not in seen:
            seen.add(id(change))
            out.append(change)
    return out


def _counts(changes) -> dict:
    counts = {CHANGED: 0, ADDED: 0, REMOVED: 0, MOVED: 0}
    for change in _unique(changes):
        counts[change["kind"]] += 1
    return counts


# --- how far it can be trusted --------------------------------------------------

def _words_in(reading) -> int:
    return sum(len(norm(p["text"]).split()) for s in reading["sections"] for p in s["passages"])


def _codes(reading) -> dict:
    return {w.get("code"): w for w in reading.get("warnings", [])}


def _notices(old: dict, new: dict):
    """What the reviewer should know before trusting the comparison, and which
    side may be missing text (``"from"``, ``"to"`` or None)."""
    notices = []
    for side, reading in (("from", old), ("to", new)):
        if _unreliable(reading):
            notices.append({"code": "sections_unidentified", "side": side})

    doubtful = None
    words_old, words_new = _words_in(old), _words_in(new)
    pages_old, pages_new = old.get("page_count") or 0, new.get("page_count") or 0
    pages_steady = abs(pages_old - pages_new) <= max(1, PAGE_STEADY * max(pages_old, pages_new))
    most = max(words_old, words_new)
    if most and pages_steady and abs(words_old - words_new) / most > TEXT_JUMP:
        doubtful = "from" if words_old < words_new else "to"
    else:
        codes_old, codes_new = _codes(old), _codes(new)
        # Characters a reader couldn't map are text it may have lost.
        if "unmapped_characters" in codes_new or "unmapped_characters" in codes_old:
            doubtful = "to" if "unmapped_characters" in codes_new else "from"
        else:
            # Pages with no text matter only when they differ between the two:
            # the same full-page figure in both is no doubt about either.
            blank_old = len(codes_old.get("pages_without_text", {}).get("pages", []))
            blank_new = len(codes_new.get("pages_without_text", {}).get("pages", []))
            if blank_old != blank_new:
                doubtful = "to" if blank_new > blank_old else "from"
    if doubtful:
        notices.append({"code": "may_be_unreliable", "side": doubtful})
    return notices, doubtful


def _mark_tentative(changes, side) -> None:
    """Text the reader may have missed on ``side`` shows there as a removal
    (missed in the later Version) or an addition (missed in the earlier one)."""
    kind = REMOVED if side == "to" else ADDED
    for change in changes:
        if change["kind"] == kind:
            change["certainty"] = TENTATIVE


# --- documents ------------------------------------------------------------------

def compare_documents(old: list, new: list) -> list:
    """Each upload slot's document in two Versions, from IR-872's rows: each
    item ``{"slot", "upload_id"}``. Unchanged, replaced, added or removed."""
    before = {d["slot"]: d["upload_id"] for d in old}
    after = {d["slot"]: d["upload_id"] for d in new}
    out = []
    for slot in sorted(before.keys() | after.keys()):
        a, b = before.get(slot), after.get(slot)
        status = (ADDED if a is None else REMOVED if b is None
                  else UNCHANGED if a == b else REPLACED)
        out.append({"slot": slot, "status": status, "from": a, "to": b})
    return out


# --- where a text appears (IR-876) ----------------------------------------------

def appears_in(reading: dict, text: str) -> list:
    """Where ``text`` appears in ``reading`` (`locate`): for each place it is
    found, a list with one ``{"section", "page", "regions"}`` per passage it
    touches. Empty when it doesn't appear."""
    return [
        [{"section": key, "page": passage["page"], "regions": passage.get("regions", [])}
         for key, passage in spot]
        for spot in locate(reading, text)
    ]


def locate(reading: dict, text: str) -> list:
    """Where ``text`` appears in ``reading``, after normalisation, ignoring case
    and **ignoring whitespace**, even across passages: for each place it is
    found, the ``(section key, passage)`` pairs it touches.

    Whitespace is ignored because a quote taken in the browser loses the space
    where a PDF line wraps (`range.toString()` joins the two words), while the
    reader keeps it: matched with spaces, a quote over a line break was not
    found even in the Version it was taken from (IR-1008)."""
    wanted = _compact(text)
    if not wanted:
        return []
    spans, parts, at = [], [], 0
    for key, passage in _flat(reading):
        piece = _compact(passage["text"])
        spans.append((at, at + len(piece), key, passage))
        parts.append(piece)
        at += len(piece)
    whole = "".join(parts)
    found, start = [], whole.find(wanted)
    while start != -1:
        end = start + len(wanted)
        found.append([(key, passage) for (s, e, key, passage) in spans if s < end and e > start])
        start = whole.find(wanted, start + 1)
    return found


def _compact(text: str) -> str:
    return norm(text).lower().replace(" ", "")
