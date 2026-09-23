"""Turning stored rectangles into drawable ones (IR-334).

Pure: no database, no Django. The rule under test is the one a reader feels —
a highlight lands on the passage, or no highlight is drawn at all. There is no
third outcome, and a box in the wrong place is the failure this guards.
"""

from apps.ai.regions import Region, normalized_regions, regions_wire

LETTER = {"1": [612.0, 792.0]}


def box(**over):
    base = {"page": 1, "left": 61.2, "top": 79.2, "right": 306.0, "bottom": 158.4}
    base.update(over)
    return base


class NormalizationTests:
    def test_a_rectangle_becomes_fractions_of_its_page(self):
        (region,) = normalized_regions([box()], LETTER)

        assert region == Region(page=1, left=0.1, top=0.1, right=0.5, bottom=0.2)

    def test_reading_order_is_preserved(self):
        pages = {"1": [612.0, 792.0], "2": [612.0, 792.0]}
        regions = normalized_regions(
            [
                box(top=396.0, bottom=475.2),
                box(page=2),
                box(top=594.0, bottom=673.2),
            ],
            pages,
        )

        assert [r.page for r in regions] == [1, 2, 1]
        assert [round(r.top, 2) for r in regions] == [0.5, 0.1, 0.75]

    def test_an_integer_page_key_reads_the_same_as_a_stored_string_one(self):
        """`page_sizes` is a dict keyed by int in memory and by string once it
        has been through JSON. Both reach this function."""
        assert normalized_regions([box()], {1: [612.0, 792.0]}) == normalized_regions(
            [box()], LETTER
        )

    def test_coordinates_outside_the_page_are_clamped_rather_than_dropped(self):
        """A rect a few points past the trim edge is a real passage slightly
        mismeasured, not a wrong one. Clamping keeps the highlight on the
        text; dropping it would lose a real citation's mark."""
        (region,) = normalized_regions(
            [box(left=-10.0, right=700.0)], LETTER
        )

        assert region.left == 0.0
        assert region.right == 1.0


class NothingIsBetterThanWrongTests:
    """Each of these would otherwise be drawn somewhere the passage is not."""

    def test_a_degenerate_rectangle_is_not_sent(self):
        assert normalized_regions([box(degenerate=True)], LETTER) == ()

    def test_a_zero_area_rectangle_is_not_sent_even_unflagged(self):
        assert normalized_regions([box(right=61.2)], LETTER) == ()

    def test_an_inverted_rectangle_is_not_sent(self):
        assert normalized_regions([box(top=158.4, bottom=79.2)], LETTER) == ()

    def test_a_rectangle_on_a_page_of_unknown_size_is_not_sent(self):
        """Without the page's size there is no honest way to normalize it, and
        guessing a size puts the box somewhere arbitrary. The page itself
        still travels separately, so the citation still opens correctly."""
        assert normalized_regions([box(page=9)], LETTER) == ()

    def test_a_page_recorded_with_zero_width_is_not_sent(self):
        assert normalized_regions([box()], {"1": [0.0, 792.0]}) == ()

    def test_a_malformed_rectangle_is_skipped_without_taking_its_siblings(self):
        regions = normalized_regions([{"page": 1, "left": "x"}, box()], LETTER)

        assert len(regions) == 1

    def test_no_rectangles_and_no_page_sizes_are_both_simply_empty(self):
        assert normalized_regions([], LETTER) == ()
        assert normalized_regions([box()], {}) == ()
        assert normalized_regions(None, None) == ()


class WireShapeTests:
    def test_the_wire_carries_the_page_and_four_fractions(self):
        assert regions_wire(normalized_regions([box()], LETTER)) == [
            {"page": 1, "left": 0.1, "top": 0.1, "right": 0.5, "bottom": 0.2}
        ]

    def test_fractions_are_rounded_rather_than_sent_as_float_noise(self):
        (row,) = regions_wire(normalized_regions([box(left=1.0)], LETTER))

        assert row["left"] == round(1.0 / 612.0, 6)
