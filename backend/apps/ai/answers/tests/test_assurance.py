"""IR-594: the typed answer contract and its checks (spec §5, A10). Pure."""
from apps.ai.answers.assurance import check, parse_draft, safe_summary
from apps.ai.retrieval.ports import RetrievedChunk


def chunk(pk, title, content, record=None):
    return RetrievedChunk(chunk_id=pk, record_id=record or pk, record_title=title,
                          content=content, context_path=(), source_page=1, score=1.0)


FLOOD = chunk(1, "Flood Prediction", "The LSTM model reached 92.4% accuracy on 30 river gauges.")
POND = chunk(2, "Tilapia Ponds", "Survival was 81% in brackish ponds; F1 was 0.77.")
SOURCES = (FLOOD, POND)
COUNT = {"name": "count", "value": 3, "provenance": {"kind": "metadata", "snapshot": "abc"}}


def codes(raw, *, sources=SOURCES, facts=(), limitations=(), live=None):
    draft = parse_draft(raw)
    live = {s.chunk_id for s in sources} if live is None else live
    return {i.code for i in check(draft, sources, facts=facts, limitations=limitations, live=live)}


def test_harmless_numbering_equations_quotes_and_labels_pass():
    raw = (
        "## 1. Overview\n"
        "1. The LSTM model reached 92.4% accuracy [1].\n"
        "2. Survival was 81% in brackish ponds [2].\n\n"
        "The loss is $L = \\sum_{i=1}^{n} (y_i - \\hat y_i)^2$ as in Figure 3.\n\n"
        "$$\nE = mc^2 + 42\n$$\n\n"
        'Authors call this the "top 5 rule", a phrase rather than a title.\n'
        "A 2-layer network is a common baseline."
    )
    assert codes(raw) == set()


def test_a_cited_number_its_source_does_not_contain_fails():
    assert codes("Flood Prediction reached 97% accuracy [1].") == {"unsupported_number"}


def test_a_number_cited_to_the_wrong_paper_fails():
    assert codes("Survival was 81% in brackish ponds [1].") == {"unsupported_number"}


def test_an_uncited_percentage_or_count_must_be_a_computed_fact():
    assert codes("The model reaches 97% accuracy.") == {"unsupported_number"}
    assert codes("There are 7 papers on floods.", facts=(COUNT,)) == {"unsupported_count"}
    assert codes("There are three papers on floods.", facts=(COUNT,)) == set()


def test_a_count_of_the_cited_papers_is_supported():
    assert codes("Two studies address water [1] [2].") == set()


def test_an_out_of_range_marker_or_handle_is_an_unknown_citation():
    assert codes("Floods are predicted [3].") == {"unknown_citation"}
    assert codes("Floods are predicted [R1].") == {"unknown_citation"}


def test_a_typed_fact_bound_to_the_wrong_metric_or_paper_fails():
    trailer = '\n```bindings\n{"facts": [{"value": 92.4, "metric": "%s", "source": %d}]}\n```'
    good = "Flood Prediction reached 92.4%% accuracy [1]." + trailer
    assert codes(good % ("accuracy", 1)) == set()
    assert codes(good % ("recall", 1)) == {"wrong_binding"}
    assert codes(good % ("accuracy", 2)) == {"wrong_binding"}


def test_a_typed_fact_bound_to_a_computed_fact_must_match_its_value():
    raw = 'There are 4 records.\n```bindings\n{"facts": [{"value": 4, "fact": "count"}]}\n```'
    assert codes(raw, facts=(COUNT,)) == {"wrong_binding", "unsupported_count"}


def test_a_paper_binding_must_name_its_source():
    raw = 'Tilapia Ponds is relevant [1].\n```bindings\n{"papers": [{"title": "Tilapia Ponds", "source": 1}]}\n```'
    assert codes(raw) == {"wrong_binding"}


def test_malformed_bindings_are_reported():
    assert codes("Floods [1].\n```bindings\n{not json\n```") == {"malformed_bindings"}


def test_an_exhaustive_claim_needs_an_exact_count_and_no_gap():
    claim = "These are all the papers on floods [1]."
    assert codes(claim) == {"completeness_overclaim"}
    assert codes(claim, facts=(COUNT,)) == set()
    assert codes(claim, facts=(COUNT,), limitations=("tool_unavailable",)) == {"completeness_overclaim"}


def test_a_sentence_citing_a_withdrawn_source_is_fenced():
    issues = check(parse_draft("Floods [1]. Ponds [2]."), SOURCES, facts=(), limitations=(), live={2})
    assert [(i.code, i.unit) for i in issues] == [("source_withdrawn", 0)]


def test_the_trailer_never_reaches_the_answer_text():
    draft = parse_draft('Floods [1].\n\n```bindings\n{"summary": "Gauges differ."}\n```\n')
    assert draft.text == "Floods [1]." and draft.summary == "Gauges differ."


def test_a_summary_with_tool_narration_markers_or_new_numbers_is_omitted():
    answer = "The LSTM reached 92.4% accuracy [1]."
    assert safe_summary("Evaluation settings differ, so 92.4% is not a ranking.", answer)
    assert safe_summary("I called search_research twice.", answer) == ""
    assert safe_summary("Accuracy is high [1].", answer) == ""
    assert safe_summary("It reached 99% accuracy.", answer) == ""


def test_a_summary_with_markup_a_vendor_name_or_unsupported_names_is_omitted():
    answer, evidence = "The LSTM reached 92.4% accuracy [1].", "Trained on the Mananga catchment."
    assert safe_summary("Settings differ in the Mananga catchment.", answer, evidence)
    assert safe_summary("<think>x</think> Settings differ.", answer) == ""
    assert safe_summary("GPT-6 judged the settings to differ.", answer) == ""
    assert safe_summary("Calling the planner showed a gap.", answer) == ""
    assert safe_summary("The Acme benchmark differs.", answer, evidence) == ""
    assert safe_summary('The paper says "state of the art".', answer, evidence) == ""
    assert safe_summary("x" * 601, answer) == ""
    assert safe_summary("Acme outperforms both baselines.", answer) == ""
    assert safe_summary("Both studies differ in their evaluation settings.", answer)


def test_a_year_or_an_abbreviation_in_a_cited_sentence_is_not_a_failure():
    assert codes("Since 2023, Zhang et al. Reported 92.4% accuracy [1].") == set()


def test_removing_sentences_leaves_no_orphan_markers_or_empty_tables():
    from apps.ai.answers.assurance import without_units

    text = "## Results\n- Bad claim.\n- Kept claim.\n\n| A | B |\n|---|---|\n| x | y |\n\nEnd."
    parts = [u.text for u in units_of(text)]
    drop = {parts.index("Results"), parts.index("Bad claim."), parts.index("| x | y |")}
    assert without_units(text, drop) == "- Kept claim.\n\nEnd."


def units_of(text):
    from apps.ai.answers.assurance import units

    return units(text)
