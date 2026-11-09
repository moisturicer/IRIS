"""Finding a thread's passage again in a later Version (ADR-032 §7, Outdated
threads; IR-876). Pure: readings are written by hand, so each test controls
exactly what changed between the two Versions."""
from apps.reviews import placement
from apps.reviews.placement import CHANGED, FOUND, REMOVED


def region(page, line):
    """The region of the ``line``-th passage on a page, in exact fractions."""
    return {"page": page, "left": 0.1, "top": line / 20, "right": 0.9, "bottom": (line + 0.5) / 20}


def reading(*sections) -> dict:
    """`sections` are (heading, [(page, text), ...])."""
    out = []
    for i, (heading, passages) in enumerate(sections):
        out.append({
            "key": f"s{i}", "heading": heading, "page": passages[0][0],
            "passages": [
                {"text": text, "page": page, "regions": [region(page, n)]}
                for n, (page, text) in enumerate(passages)
            ],
        })
    return {"page_count": 9, "warnings": [], "sections": out}


METHOD = [
    (3, "We sampled 120 households in Cebu City."),
    (3, "Each household was visited twice."),
    (4, "Answers were coded by two researchers."),
]


def test_an_unchanged_passage_is_found_on_its_new_page():
    old = reading(("Method", METHOD))
    new = reading(("Introduction", [(1, "A new opening paragraph.")]),
                  ("Method", [(5, text) for _, text in METHOD]))

    place = placement.place(old, new, "visited twice")

    assert place.outcome == FOUND
    assert place.page == 5
    assert place.text == "visited twice"
    assert place.regions == [region(5, 1)]


def test_an_edited_passage_is_changed_with_the_new_text_beside_it():
    old = reading(("Method", METHOD))
    new = reading(("Method", [
        (3, "We sampled 120 households in Cebu City."),
        (3, "Each household was visited three times."),
        (4, "Answers were coded by two researchers."),
    ]))

    place = placement.place(old, new, "visited twice")

    assert place.outcome == CHANGED
    assert place.page == 3
    assert place.text == "Each household was visited three times."
    assert place.regions == [region(3, 1)]


def test_a_deleted_passage_is_removed():
    old = reading(("Method", METHOD))
    new = reading(("Method", [METHOD[0], METHOD[2]]))

    place = placement.place(old, new, "visited twice")

    assert place.outcome == REMOVED
    assert (place.page, place.text, place.regions) == (None, "", [])


def test_a_passage_moved_to_another_section_is_found_there():
    old = reading(("Method", METHOD), ("Results", [(6, "Most households said yes.")]))
    new = reading(("Method", [METHOD[0], METHOD[2]]),
                  ("Results", [(6, "Most households said yes."), (6, METHOD[1][1])]))

    place = placement.place(old, new, "visited twice")

    assert (place.outcome, place.page) == (FOUND, 6)


def test_matching_ignores_line_break_hyphens_and_case():
    old = reading(("Method", METHOD))
    new = reading(("Method", [(3, "EACH HOUSE-HOLD WAS VISITED TWICE.")]))

    assert placement.place(old, new, "household was visited").outcome == FOUND
