"""Titles and category names match whatever their case, hyphens or punctuation (IR-995)."""

from ai.research import metadata

TITLES = [{"title": t} for t in (
    "TTM-Bench A Framework for Text-to-Music System Performance Benchmarking",
    "Tide-and-Seek Anisotropic scale-dependent bias in the Lyman-alpha forest",
    "Exploring the observed properties of JWST Little Red Dots with cosmological simulations and dust "
    "radiative transfer",
    "MeshKV: A Network-on-Chip KV Cache Fabric",
)]


def matched(reference):
    basis, rows = metadata.title_matches(TITLES, reference)
    return basis, [r["title"][:12] for r in rows]


def test_a_category_slug_and_its_spoken_name_fold_alike():
    assert metadata.fold("hardware-architecture") == metadata.fold("Hardware Architecture ") == "hardware architecture"
    assert metadata.fold("Healthcare & MedTech") == "healthcare medtech"


def test_a_hyphenated_title_is_found_by_its_spoken_name():
    assert matched("TTM Bench") == ("title_phrase", ["TTM-Bench A "])
    assert matched("Tide and Seek") == ("title_phrase", ["Tide-and-See"])


def test_exact_and_short_titles_still_win_first():
    assert matched("MeshKV") == ("short_title", ["MeshKV: A Ne"])


def test_a_described_paper_comes_back_as_a_close_title_to_choose_from():
    assert matched("the JWST Little Red Dots simulation paper") == ("close_title", ["Exploring th"])


def test_an_unrelated_or_one_word_reference_matches_nothing():
    assert matched("coral bleaching recovery") == ("none", [])
    assert matched("simulation paper") == ("none", [])
