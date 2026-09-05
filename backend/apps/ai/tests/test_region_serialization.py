"""How a chunk's citation regions are written to and read from storage
(IR-113).

Split out from the repository contract suite deliberately. The contract
suite says what a *repository* guarantees, and "a degenerate rect carries a
flag" is not that — it is a property of the stored JSON, read later by the
citation overlay. Asserting it through the repository would have meant
adding an introspection method to the port for no production caller.
"""

from apps.ai.chunking.document import BoundingBox
from apps.ai.repositories import deserialize_regions, serialize_regions

ORDINARY = BoundingBox(page=4, left=72.0, top=100.0, right=540.0, bottom=130.0)
ZERO_WIDTH = BoundingBox(page=3, left=72.0, top=100.0, right=72.0, bottom=140.0)
ZERO_AREA = BoundingBox(page=3, left=72.0, top=100.0, right=72.0, bottom=100.0)
INVERTED = BoundingBox(page=5, left=100.0, top=50.0, right=20.0, bottom=80.0)


def test_an_ordinary_region_is_stored_without_a_flag():
    assert serialize_regions((ORDINARY,)) == [
        {"page": 4, "left": 72.0, "top": 100.0, "right": 540.0, "bottom": 130.0}
    ]


def test_a_zero_area_region_is_stored_flagged():
    """A scanned page can yield a collapsed rect. Drawing it would put an
    invisible, unclickable box on the page and tell the reader nothing; the
    flag is what lets the overlay skip it deliberately rather than by
    accident."""
    assert serialize_regions((ZERO_AREA,))[0]["degenerate"] is True


def test_a_zero_width_region_is_stored_flagged():
    assert serialize_regions((ZERO_WIDTH,))[0]["degenerate"] is True


def test_an_inverted_region_is_stored_flagged():
    assert serialize_regions((INVERTED,))[0]["degenerate"] is True


def test_the_flag_does_not_change_the_value_read_back():
    """It is a rendering hint added on the way out, not a change to the
    region — the chunk still reports the page it came from."""
    assert deserialize_regions(serialize_regions((ZERO_AREA,))) == (ZERO_AREA,)


def test_regions_round_trip_in_order():
    original = (ORDINARY, ZERO_AREA, INVERTED)

    assert deserialize_regions(serialize_regions(original)) == original


def test_rows_written_before_the_flag_existed_still_read_back():
    """Chunk sets stored before this field was added carry no `degenerate`
    key. They must not need a migration to stay readable."""
    legacy = [{"page": 4, "left": 72.0, "top": 100.0, "right": 540.0, "bottom": 130.0}]

    assert deserialize_regions(legacy) == (ORDINARY,)
