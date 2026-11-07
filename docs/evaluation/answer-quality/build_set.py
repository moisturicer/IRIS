"""Build the IR-956 answer-quality set from existing material plus new labels.

    python docs/evaluation/answer-quality/build_set.py

Reuses `proxy_starter.json` (single facts, meaning-only questions, comparisons,
follow-ups, out-of-corpus questions, Paper Chat questions), the shapes of
`general-tools/conversation_set_v1.json` A03/A04/A06/A11 (listing, naming,
counts, Paper Chat) and of IR-753's long-context draft pack L04 (compaction then
exact-detail recovery). New labels (late-page details, counts, listings, the
private paper) are copied from chunk text in the development database. Labels
were drafted by an agent; correct them in a new version, never in place.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
SET_ID, VERSION = "answer-quality-v1", 1
PRIVATE = "Proving and Improving the Platonic Representation Hypothesis with JEPAs"


def norm(text):
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split())


CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))["papers"]
TITLES = [p["title"] for p in CORPUS]


def title(name):
    """The exact Record title a source label abbreviates."""
    if name in TITLES:
        return name
    words = set(norm(name).split())
    scored = sorted(((len(words & set(norm(t).split())) / len(words), t) for t in TITLES),
                    reverse=True)
    if scored[0][0] < 0.6 or scored[0][0] == scored[1][0]:
        sys.exit(f"cannot place {name!r}: {scored[:2]}")
    return scored[0][1]


PROXY = {q["id"]: q for q in json.loads(
    (EVAL / "proxy_starter.json").read_text(encoding="utf-8"))["questions"]}


def evidence(qid):
    return [(title(e["record"]), e["page"], e["quote"]) for e in PROXY[qid]["expected"]]


#: Labels whose quote sits in a chunk that starts on the page before (audited
#: against chunk text): a citation of that chunk reports the earlier page.
CHUNK_STARTS = {("Noise-adjusted turnover in estimated networks", 2): 1,
                ("From Density to Mass A New Parametrized Framework for Dark Matter Environment "
                 "Around Black Holes", 2): 1}


def page_label(t, p, q):
    also = CHUNK_STARTS.get((t, p))
    return {"record": t, "page": p, "quote": q, **({"also": [also]} if also else {})}


def answer(ev, reference=None):
    records = list(dict.fromkeys(t for t, _, _ in ev))
    return {"outcome": "answer", "records": records,
            "pages": [page_label(t, p, q) for t, p, q in ev],
            "reference": reference or "; ".join(f"{t}: \"{q}\"" for t, _, q in ev)}


CASES = []


def add(family, turns, expect, sources, reader="b", **extra):
    n = sum(c["family"] == family for c in CASES) + 1
    turns = [t if isinstance(t, dict) else {"user": t} for t in turns]
    CASES.append({"id": f"{family}-{n:02d}", "family": family, "reader": reader,
                  "turns": turns, "expect": expect, "sources": sources, **extra})


# F01 single fact: proxy_starter exact-term questions.
for qid in ("q19", "q20", "q21", "q22", "q30", "q33", "q37", "q39", "q42", "q113"):
    add("F01", [PROXY[qid]["question"]], answer(evidence(qid)), [f"proxy_starter:{qid}"])

# F02 meaning only: paraphrased mechanism questions sharing no content word with
# their paper's title or labelled passage.
for qid in ("q01", "q03", "q04", "q07", "q08", "q13", "q14", "q15", "q16", "q17"):
    add("F02", [PROXY[qid]["question"]], answer(evidence(qid)), [f"proxy_starter:{qid}"])

# F03 multi-paper comparison.
for qid in ("q26", "q27", "q28", "q34", "q52"):
    add("F03", [PROXY[qid]["question"]], answer(evidence(qid)), [f"proxy_starter:{qid}"])
add("F03", ["Compare MeshKV and HBFlex: what does each one study about how LLM state is held "
            "in memory?"],
    answer([(title("MeshKV"), 2, "An instrumented FP16 decoder on LLaMA-2-7B"),
            (title("HBFlex"), 2, "distinguishing placement imbalance from access imbalance")],
           "MeshKV instruments an FP16 LLaMA-2-7B decoder to observe KV-cache access patterns "
           "for a network-on-chip cache fabric; HBFlex studies flash-held caches and separates "
           "placement imbalance from access imbalance."),
    ["proxy_starter:q22", "proxy_starter:q17", "new:comparison"])
add("F03", ["Compare the protocluster metallicity study and the IGM transmission study: how "
            "many objects does each start from?"],
    answer([(title("Diverse Metallicities in Protoclusters"), 3,
             "121 protocluster candidates identified by PCFNet"),
            (title("Probing Spatial Variations in IGM Transmission"), 3,
             "projected galaxy density map from the sky distribution of the full parent sample "
             "of 84 HAEs")],
           "The protocluster study starts from 121 protocluster candidates flagged by PCFNet; "
           "the IGM study builds its density map from 84 H-alpha emitters."),
    ["proxy_starter:q30", "proxy_starter:q39", "new:comparison"])
add("F03", ["Compare TTM-Bench and the multimodal conversational ASR work: how large is the "
            "collection each one builds on?"],
    answer([(title("TTM-Bench"), 3,
             "The reference collection comprises 100 commercially released tracks"),
            (title("Multimodal Conversational Context for LLM-Based ASR"), 3,
             "We select about 175k target entities")],
           "TTM-Bench uses 100 commercially released reference tracks; the ASR work selects "
           "about 175k target entities."),
    ["proxy_starter:q20", "proxy_starter:q21", "new:comparison"])


# F04 exact metadata counts (conversation_set_v1 A06 and its category totals).
def category(name):
    return [p["title"] for p in CORPUS if p["category"] == name]


COUNTS = [
    ("How many papers are under Audio and Speech Processing?",
     len(category("audio-and-speech-processing")), "conversation_set_v1:A06-D01"),
    ("How many papers are in Hardware Architecture?",
     len(category("hardware-architecture")), "conversation_set_v1:A06-H01"),
    ("How many readable published papers are there?", len(CORPUS),
     "conversation_set_v1:A06-D02"),
    ("How many papers are in the econometrics category?", len(category("econometrics")),
     "new:count"),
    ("How many papers are filed under astrophysics of galaxies?",
     len(category("astrophysics-of-galaxies")), "new:count"),
    ("How many papers are in cosmology and nongalactic astrophysics?",
     len(category("cosmology-and-nongalactic-astrophysics")), "conversation_set_v1:A06-H02"),
    ("How many papers are listed under active learning?", len(category("active learning")),
     "new:count"),
    ("How many papers are under Marine Biology?", 0, "conversation_set_v1:A06-D01"),
]
for question, count, source in COUNTS:
    add("F04", [question], {"outcome": "count", "count": count, "records": [], "pages": [],
                            "reference": f"Exactly {count}."}, [source])


# F05 listing.
def listing(titles, why):
    return {"outcome": "answer", "records": [], "pages": [], "listing": titles,
            "reference": f"{why}: " + "; ".join(titles)}


for question, name in (
        ("List the papers under Audio and Speech Processing.", "audio-and-speech-processing"),
        ("List the papers you have in hardware architecture.", "hardware-architecture"),
        ("List the econometrics papers.", "econometrics"),
        ("List the papers in active learning.", "active learning"),
        ("List the papers filed under astrophysics of galaxies.", "astrophysics-of-galaxies"),
        ("List the papers in cosmology and nongalactic astrophysics.",
         "cosmology-and-nongalactic-astrophysics")):
    add("F05", [question], listing(category(name), f"The {name} papers"),
        ["conversation_set_v1:A03" if name == "hardware-architecture" else "new:listing"])
add("F05", ["List the papers you have in hardware architecture.",
            "Only the ones about saving power."],
    listing([title("Evaluating Positive Feedback Adiabatic Logic"),
             title("Evaluation of Power-Clock Waveforms for Positive Feedback Adiabatic Logic")],
            "The two adiabatic-logic papers"), ["conversation_set_v1:A03-D01"])
add("F05", ["List every paper whose title mentions dark matter."],
    listing([t for t in TITLES if "dark matter" in norm(t)],
            "Titles that mention dark matter"), ["new:listing"])

# F06 naming a paper by a short, partial or misspelled name (conversation_set_v1 A04).
for question, name in (
        ("Find the MeshKV paper.", "MeshKV"),
        ("Is there a paper called HBFlex?", "HBFlex"),
        ("Find the paper asking whether Fingers of God can be resummed.", "Can Fingers of God"),
        ("Do you have the TTM Bench paper?", "TTM-Bench"),
        ("Look up the Never Giving Up paper about RL for LLMs.", "Never Giving Up"),
        ("Find the Tide and Seek paper.", "Tide-and-Seek"),
        ("Find the paper where GAIA meets LZ.", "GAIA meets LZ"),
        ("Find the ViCTORIA project paper about M49.", "ViCTORIA project"),
        ("Find Stabel Polcy Learning.", "Stable Policy Learning"),
        ("Find the adiabatic logic paper that uses a realistic power-clock.",
         "Evaluating Positive Feedback Adiabatic Logic in 16nm FinFET with a Realistic")):
    t = title(name)
    add("F06", [question], {"outcome": "answer", "records": [t], "pages": [],
                            "reference": f"The paper is \"{t}\"."},
        ["conversation_set_v1:A04"])

# F07 a detail late in a long Manuscript: chunk text on late pages.
LATE = [
    ("Learning to Solve Hard Problems in RL for LLMs by Never Giving Up", 17,
     "In the appendix of Learning to Solve Hard Problems in RL for LLMs by Never Giving Up, how "
     "does Reinforce-Ada relate to their method, and what goes wrong with it on unsolvable "
     "prompts?",
     "equivalent to NGU with probability p = 1",
     "Reinforce-Ada does not stop sampling until a positive is reached, equivalent to NGU with "
     "p = 1, so it stalls on any prompt the model cannot solve."),
    ("Extreme MgII Emission in Recently-Quenched Galaxies", 15,
     "In the discussion of the extreme MgII emission paper, above what bolometric luminosity "
     "are quasars definitely excluded from their post-starburst selection?",
     "we definitely exclude quasars with bolometric luminosities in excess of 1046 erg s-1",
     "Quasars with bolometric luminosities above about 10^46 erg/s are definitely excluded."),
    ("Exploring the observed properties of JWST Little Red Dots", 15,
     "In the JWST Little Red Dots simulation paper, what are the redshift and central black "
     "hole mass of the representative simulated candidate in its SED figure?",
     "representative simulated LRD candidate at z = 6.3",
     "It is at z = 6.3 with a central black hole of about 3.5 x 10^8 solar masses."),
    ("The 2MIG isolated AGNs", 13,
     "In the 2MIG isolated AGNs hot-dust reverberation paper, on what scale does IC 5287 show "
     "its dust response, and how firm is the wavelength ordering of its lags?",
     "IC 5287 shows a characteristic optical-MIR dust response on a scale of approximately "
     "0.1 pc",
     "About 0.1 pc; its W2 delay is longer than W1 but the lag distributions overlap "
     "(probability about 0.65), so the ordering is only tentative."),
    ("Gauge Backreaction in Standard Model Warm Inflation", 20,
     "In Gauge Backreaction in Standard Model Warm Inflation, what range does the gauge coupling "
     "take over the numerical parameter range?",
     "the gauge coupling is g ≃ 0.554 - 0.570",
     "g is about 0.554 to 0.570; the hard-soft hierarchy is checked numerically rather than "
     "assumed."),
    ("Stable Policy Learning", 41,
     "In the appendix of Stable Policy Learning, why can the certainty equivalent never exceed "
     "mean welfare?",
     "The exponential function is convex, so Jensen's inequality gives",
     "Because the exponential function is convex, Jensen's inequality makes the logarithmic "
     "term nonnegative, so the certainty equivalent is at most mean welfare."),
    ("Using machine learning metrics to provide deeper insights", 15,
     "In the paper on machine learning metrics for choice models, which two models have nearly "
     "the same overall accuracy on SwissMetro but different confusion matrices?",
     "Scobit and XGB have a similar score on overall accuracy (0.604 and 0.605, respectively)",
     "Scobit and XGB (accuracy 0.604 and 0.605); on the test sample XGB identifies 29% of Train "
     "observations against Scobit's 22%."),
    ("Diverse Metallicities in Protoclusters", 12,
     "In the protocluster metallicity paper, which two protoclusters show a marginal metallicity "
     "enhancement, and what explanation do the authors offer?",
     "more efficient recycling of metal-rich outflows in overdense environments",
     "COSMOS_ID0_PC3 and COSMOS_ID0_PC4; possibly more efficient recycling of metal-rich "
     "outflows in overdense environments."),
    ("Beyond Linearity Semiparametric Solutions to Contamination Bias", 18,
     "In the appendix of the contamination bias paper, where did the authors search for "
     "articles to replicate?",
     "we searched articles published by the American Economic Association and articles "
     "published in Econometrica",
     "Articles from the American Economic Association and from Econometrica, the Journal of "
     "Political Economy, the Quarterly Journal of Economics and the Review of Economic Studies "
     "(the last two were not included in the replicated sample)."),
    ("Online Adaptive Kernel Mixing for Gaussian Process Decision Making", 23,
     "In the proofs appendix of Online Adaptive Kernel Mixing, which online learning algorithms "
     "do the weight-concentration results cover?",
     "proofs of the weight-concentration results with AdaHedge and Standard Hedge",
     "AdaHedge and standard Hedge."),
]
for name, page, question, quote, reference in LATE:
    t = title(name)
    paper = next(p for p in CORPUS if p["title"] == t)
    assert page >= paper["pages"] * 0.5, (t, page)
    add("F07", [question], answer([(t, page, quote)], reference), ["new:late-page-chunk"])

# F08 multi-turn follow-ups: proxy_starter follow-up-after-grounded questions, with
# the turn that grounds them written from their resolved question.
FOLLOW = {
    "q61": "Which paper deals with uncertainty around Pareto fronts in multiobjective "
           "optimization?",
    "q62": "Which paper keeps sampling hard prompts in RL for LLMs instead of giving up?",
    "q75": "In the paper on FIR filtering on a quantum computer, what are qubits used for?",
    "q76": "Which paper uses a deep learning network to find protocluster candidates?",
    "q77": "Which paper builds GPU ODE solvers for massive ensembles?",
    "q98": "Which paper benchmarks text-to-music systems against real reference tracks?",
    "q99": "Which paper builds speech recognition training data around a pool of target "
           "entities?",
    "q100": "What does MATISSE in the era of GRAVITY+ measure on its test star in the L band?",
    "q101": "Which paper maps galaxy density around an H-alpha selected overdensity at z of "
            "about 6.2?",
    "q102": "Which paper finds post-starburst quasars with extreme MgII emission?",
}
for qid, first in FOLLOW.items():
    q = PROXY[qid]
    add("F08", [first, q["question"]],
        answer(evidence(qid), f"{q['resolved_question']} \"{evidence(qid)[0][2]}\""),
        [f"proxy_starter:{qid}"])

# F09 compaction then exact-detail recovery (long-context pack L04's shape).
for qid in ("q09", "q10", "q18", "q29", "q31", "q35", "q41", "q05"):
    add("F09", [PROXY[qid]["question"],
                "Separately: how many papers are in the econometrics category?",
                {"action": "compact"},
                "Going back to my first question: what exactly did the paper say about it, and "
                "on which page?"],
        answer(evidence(qid)), [f"proxy_starter:{qid}", "long-context-draft:L04"])

# F10 unanswerable or out of corpus.
for qid in sorted((q for q in PROXY if PROXY[q]["kind"] == "off-corpus-research"),
                  key=lambda q: int(q[1:])):
    add("F10", [PROXY[qid]["question"]], {"outcome": "refuse", "records": [], "pages": [],
                                          "reference": "No paper in the repository covers this."},
        [f"proxy_starter:{qid}"])

# F11 Paper Chat scoped to one Record (conversation_set_v1 A11).
for qid in ("q02", "q06", "q11", "q12", "q36", "q38", "q43", "q50"):
    ev = evidence(qid)
    add("F11", [PROXY[qid]["question"]], answer(ev), [f"proxy_starter:{qid}",
                                                      "conversation_set_v1:A11"],
        scope=ev[0][0])

# F12 two readers: reader a owns an unpublished paper reader b cannot read.
PAIRS = [
    ("What CIDEr score on COCO does the captioning approach reach that joins frozen DINOv2 and "
     "DINOv3 image encoders to a text-only language model?",
     [(PRIVATE, 2, "reaching CIDEr .838 on COCO")], "CIDEr .838 on COCO."),
    ("Is there work showing that good views make representation alignment many times more "
     "sample-efficient? By how much?",
     [(PRIVATE, 1, "alignment 42 times more sample-efficient")],
     "Yes: good views make alignment 42 times more sample-efficient."),
    ("Which paper turns the Platonic Representation Hypothesis into a theorem, and what does it "
     "prove?",
     [(PRIVATE, 2, "any number of JEPAs trained separately on renderings of one world learn the "
                   "same embedding up to one rotation each")],
     "JEPAs trained separately on renderings of one world learn the same embedding up to one "
     "rotation each, when their positive pairs relate the same world states."),
]
for n, (question, ev, reference) in enumerate(PAIRS, 1):
    add("F12", [question], answer(ev, reference), ["new:private-paper-chunk"], reader="a",
        pair=f"P{n}")
    add("F12", [question], {"outcome": "refuse", "records": [], "pages": [],
                            "reference": "No readable paper covers this.",
                            "forbidden": [PRIVATE]}, ["new:private-paper-chunk"],
        pair=f"P{n}")
for reader in ("a", "b"):
    add("F12", [PROXY["q19"]["question"]], answer(evidence("q19")), ["proxy_starter:q19"],
        reader=reader, pair="P4")

SET = {
    "schema_version": 1, "set_id": SET_ID, "version": VERSION,
    "label_status": "agent_drafted",
    "notes": "IR-956. Labels drafted by an agent and open to the owner's correction; a "
             "corrected set is a new version with a new lock. Proxy corpus only: never a "
             "finding about CIT-U research.",
    "corpus": {
        "snapshot_id": "proxy-arxiv-40",
        "paper_set_sha256": "6793dcadc793c1a3cdd831bc18b9091816e04d519e674e728e864aeef970c3d0",
        "titles": TITLES,
        "private": {"title": PRIVATE, "readable_by": "a",
                    "note": "An unpublished paper owned by reader a, indexed for Ask IRIS; "
                            "reader b must never see it."},
    },
    "readers": {"a": "owns the private paper", "b": "an ordinary reader of the 40 papers"},
    "cases": CASES,
}

if __name__ == "__main__":
    out = HERE / f"{SET_ID}.json"
    out.write_text(json.dumps(SET, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out.name}: {len(CASES)} cases")
