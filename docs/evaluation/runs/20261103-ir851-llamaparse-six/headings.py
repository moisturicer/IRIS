"""Heading levels against section numbering, from the analysis files' full outlines.

Depth: "2" is 0, "2.1" is 1, "2.1.1" is 2; roman "IV." is 0 and, in a paper
numbered in roman, "B." is 1. A heading is off-level when its level differs
from the level most headings of its depth have in that paper. Nesting is
ordered when that usual level deepens with depth. A caption or running header
returned as a heading counts as a false heading.
"""
import collections, json, re, sys

DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+[A-Za-z]")
ROMAN = re.compile(r"^(?=[IVX]+\.)(X{0,3})(IX|IV|V?I{0,3})\.\s+\S")
LETTER = re.compile(r"^[A-H]\.\s+\S")
FALSE = re.compile(r"^(table|fig\.?|figure)\s*[\dA-Z]|^a preprint$", re.I)


def depth(text, roman_paper):
    if m := DECIMAL.match(text):
        return m.group(1).count(".")
    if ROMAN.match(text):
        return 0
    if roman_paper and LETTER.match(text):
        return 1
    return None


def check(outline):
    roman_paper = sum(1 for _, t in outline if ROMAN.match(t)) >= 2
    numbered = [(lv, t, depth(t, roman_paper)) for lv, t in outline]
    numbered = [(lv, t, d) for lv, t, d in numbered if d is not None and lv is not None]
    by = collections.defaultdict(list)
    for lv, _, d in numbered:
        by[d].append(lv)
    usual = {d: collections.Counter(v).most_common(1)[0][0] for d, v in by.items()}
    order = [usual[d] for d in sorted(usual)]
    off = [(lv, t) for lv, t, d in numbered if lv != usual[d]]
    return {
        "numbered": len(numbered),
        "off_level": len(off),
        "nesting_ordered": order == sorted(order) and len(set(order)) == len(order),
        "off_level_examples": off[:6],
        "false_headings": [t for _, t in outline if FALSE.match(t)],
    }


out = {}
for name in sys.argv[1:]:
    tag = "llamaparse" if "llama" in name else "docling"
    for row in json.load(open(name, encoding="utf-8")):
        out.setdefault(row["title"], {})[tag] = check(row["heading_outline"])
print(json.dumps(out, indent=1, ensure_ascii=False))
