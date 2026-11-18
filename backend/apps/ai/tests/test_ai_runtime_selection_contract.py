"""Ask about a selection: what the runtime accepts as a quoted passage (IR-581).

Pure: the request shape, the canonical form a quote is compared in, and the
rule that it must lie on the page it names. Checking it against PostgreSQL,
and keeping it from a vendor when it fails, is `test_ai_runtime_selection_db.py`'s.
"""

import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.runs.anchor import MAX_QUOTE, Selection, anchored, canonical, parse  # noqa: E402
from ai.runs.store import request_hash  # noqa: E402

REVISION = str(uuid.uuid4())


def body(**over):
    return {"record_id": 7, "manuscript_revision": REVISION, "page": 3,
            "quote": "Flooding rose by 40 percent.", **over}


def test_a_well_formed_selection_parses():
    s = parse(body(quote="  Flooding   rose\nby 40 percent. "))
    assert s == Selection(record_id=7, revision=REVISION, page=3, quote="Flooding rose by 40 percent.")
    assert Selection.from_json(s.to_json()) == s


@pytest.mark.parametrize("over", [
    {"record_id": "x"}, {"record_id": 0}, {"page": 0}, {"page": "2"}, {"quote": " a "},
    {"quote": "x" * (MAX_QUOTE + 1)}, {"manuscript_revision": "not-a-uuid"}, {"manuscript_revision": None},
])
def test_a_malformed_selection_is_refused(over):
    with pytest.raises(ValueError):
        parse(body(**over))


def test_canonical_form_ignores_layout_not_words():
    assert canonical("ex-\nplicit  ﬁndings") == canonical("explicit findings")
    assert canonical("Flood­water") == canonical("Floodwater")
    assert canonical("state-of-the-art") == canonical("state-of-the-art")
    assert canonical("forty percent") != canonical("fifty percent")


def test_canonical_form_matches_a_pdf_text_layer_to_the_indexed_text():
    # As a PDF's own text layer gives them, against the extracted text (a dev paper, IR-581).
    assert canonical("TPS20,21 ad-dresses the time-scale separation") == canonical(
        "TPS 20,21 addresses the time-scale separation")
    assert canonical("the “committor” is ‘learned’") == canonical("the \"committor\" is 'learned'")
    assert canonical("Rare Events") == canonical("rare events")


def test_canonical_form_keeps_the_numbers():
    assert canonical("a rise of 1.5 m") != canonical("a rise of 15 m")
    assert canonical("2,500 households") != canonical("2500 households")
    assert canonical("a rise of 1.5 m") == canonical("a rise of 1.5m")


CHUNKS = [
    (1, "Abstract. A study of flooding in Cebu."),
    (2, "Methods. We surveyed 200 households near the river."),
    (3, "Results. Flooding rose by 40 percent. Households moved"),
    (3, "inland within two years."),
    (4, "Discussion. The drainage plan failed."),
]


def test_a_quote_on_its_page_is_anchored():
    assert anchored("Flooding rose by 40 percent.", 3, CHUNKS)
    # Across two chunks of the same page.
    assert anchored("Households moved inland", 3, CHUNKS)


def test_a_quote_on_another_page_is_not():
    assert not anchored("We surveyed 200 households", 4, CHUNKS)
    assert not anchored("Flooding rose by 40 percent.", 4, CHUNKS)
    assert not anchored("Discussion. The drainage plan failed.", 2, CHUNKS)


def test_an_altered_quote_is_not():
    assert not anchored("Flooding rose by 60 percent.", 3, CHUNKS)


def test_the_chunk_running_onto_a_page_counts_for_it():
    # Chunks are labelled by the page they start on; the last one before page 4 may end on it.
    assert anchored("inland within two years.", 4, CHUNKS)


def test_a_selection_running_onto_the_next_page_is_anchored_where_it_starts():
    assert anchored("inland within two years. Discussion. The drainage", 3, CHUNKS)
    assert not anchored("The drainage plan failed.", 3, CHUNKS)


def test_a_page_inside_a_chunk_that_began_earlier_reads_that_chunk():
    long = [(5, "Chapter two opens here and the long passage carries on to the next page"), (7, "Chapter three.")]
    assert anchored("carries on to the next page", 6, long)
    assert not anchored("Chapter three.", 6, long)


def test_a_page_with_no_text_anchors_nothing():
    assert not anchored("anything", 9, CHUNKS)
    assert not anchored("anything", 1, [])


def test_the_selection_is_part_of_the_request_identity():
    plain = request_hash("Why?", None, None)
    assert request_hash("Why?", None, None, selection=None) == plain
    one = request_hash("Why?", None, None, selection=parse(body()))
    other = request_hash("Why?", None, None, selection=parse(body(page=4)))
    assert len({plain, one, other}) == 3
