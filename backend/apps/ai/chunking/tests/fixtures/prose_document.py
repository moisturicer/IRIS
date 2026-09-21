"""A thesis-shaped prose document, for the IR-287 boundary-equivalence test.

Ordinary academic prose and nothing else: no tables, no code, no formulas.
That is the point. IR-287 promised that changing the counting unit from
whitespace words to real ``voyage-context-4`` tokens, and raising the ceiling
from 512 to 700 in the same breath, would leave chunk boundaries **on
ordinary prose** exactly where they were. Token-dense material is where the
two units diverge, so demonstrating the promise needs material where they do
not.

The paragraphs vary in length on purpose -- some short enough to reach the
merge floor, several long enough that a section must be split -- so the test
exercises packing, the floor and the ceiling rather than one of them.
"""

from apps.ai.chunking.document import (
    HEADING,
    PARAGRAPH,
    DocumentElement,
    NormalizedDocument,
)

TITLE = "Clearance-Aware Resubmission in Institutional Research Workflows"

_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "1 Introduction",
        (
            "The disclosure of intellectual property arising from academic research "
            "depends less on the quality of the underlying invention than on the "
            "administrative machinery that surrounds it. A university that cannot "
            "route a disclosure to the offices responsible for clearing it will "
            "lose the disclosure, not because anyone decided against it, but "
            "because the document stopped moving and nobody noticed that it had. "
            "This study takes that observation as its starting point and asks what "
            "a workflow system would have to do differently in order to keep a "
            "submission in motion through a review process that involves several "
            "independent offices at once.",
            "Prior work on technology transfer in higher education has consistently "
            "identified the interval between invention and disclosure as a "
            "predictor of commercialisation outcomes. Much less attention has been "
            "paid to the mechanisms that produce that interval. The literature "
            "treats the review period as a largely undifferentiated delay, "
            "attributable to institutional capacity or to researcher incentives, "
            "and rarely distinguishes between time spent waiting for a decision "
            "and time spent repeating work that a previous round of review had "
            "already completed. The distinction matters because the two have "
            "entirely different remedies. Waiting for a decision is a staffing "
            "problem. Repeating completed work is a design problem, and design "
            "problems can be solved in software.",
            "The system described here was built for a single institution and "
            "makes no claim to generality beyond the class of institutions that "
            "share its review structure. What it does claim is that a particular "
            "property of that structure, which we call clearance-aware "
            "resubmission, can be stated precisely, implemented, and evaluated.",
        ),
    ),
    (
        "2 Background",
        (
            "An institutional disclosure passes through several offices before it "
            "is approved. In the case studied here the offices are the research "
            "office, which checks that the submission is complete and correctly "
            "classified; the ethics review committee, which considers human and "
            "animal subjects; and the technology transfer office, which assesses "
            "patentability and any prior commitments that might encumber the "
            "work. These offices do not review in sequence. They review in "
            "parallel, and each one issues its own clearance independently of the "
            "others, which is both the source of the process's efficiency and the "
            "source of the problem this study addresses.",
            "The problem appears at the moment one office asks for revisions. In "
            "the paper process, and in most of the software systems that replaced "
            "it, a request for revisions returns the entire submission to the "
            "author and voids every clearance it had accumulated. The author "
            "revises one section in response to one office and then waits for all "
            "three offices to review the document again from the beginning. Two of "
            "those three reviews are repetitions of work already completed, "
            "performed on material that did not change, by people who have already "
            "read it and already agreed to it.",
            "The cost compounds. Each additional round multiplies the number of "
            "redundant reviews, and because the offices are staffed independently "
            "the rounds do not overlap cleanly. A submission that requires three "
            "rounds of revision, each triggered by a different office, can consume "
            "nine reviews where four would have sufficed. Authors respond to this "
            "by batching their revisions and by avoiding resubmission entirely "
            "where they can, which is precisely the behaviour the process was "
            "designed to discourage.",
            "It is worth being clear about what is not being claimed. The offices "
            "are not duplicating work through carelessness or through any failure "
            "of professional judgement. They are duplicating it because the system "
            "they work in has no way to represent the fact that a clearance "
            "survives a change to a part of the document it did not depend on. "
            "The state of the submission is a single flag, and a single flag "
            "cannot hold three independent decisions.",
        ),
    ),
    (
        "3 Method",
        (
            "Review state is modelled as a set of per-office clearances rather "
            "than as a single status. Each clearance records the office that "
            "issued it, the decision, the reviewer, and the version of the "
            "submission the decision was made against. A submission is approved "
            "when every required clearance is present and positive, and the set of "
            "required clearances is determined by the submission's type, so that a "
            "disclosure with no human subjects never waits on an ethics clearance "
            "it does not need.",
            "When an office requires revisions, only that office's clearance is "
            "reset. The others are preserved along with the version they were "
            "issued against. The author revises and resubmits, the submission "
            "returns to the one office that asked for the change, and the other "
            "offices see nothing at all unless the revision touched material their "
            "own clearance depended on. This is the behaviour the study calls "
            "clearance-aware resubmission, and it is the central contribution of "
            "the work.",
            "Determining whether a revision touched material a clearance depended "
            "on is the hard part, and the present implementation takes a "
            "deliberately conservative position on it. Rather than attempting to "
            "infer dependency automatically, the system asks the reviewing office "
            "to declare, at the moment it issues a clearance, which sections of "
            "the submission the clearance rests on. A subsequent revision that "
            "modifies any declared section invalidates the clearance. A revision "
            "that does not, does not. The declaration is coarse, and it is "
            "occasionally wrong in the conservative direction, which is to say it "
            "invalidates a clearance that would have survived a more careful "
            "analysis. That trade was made on purpose: a clearance wrongly "
            "preserved is a governance failure, while a clearance wrongly "
            "invalidated is only a delay of the kind the old process imposed "
            "unconditionally.",
            "The evaluation compares the number of reviews required per approved "
            "submission before and after the change, using the institution's own "
            "records for the baseline period and the system's audit log for the "
            "period after deployment. Because the two periods differ in "
            "submission volume and in the mix of submission types, the comparison "
            "is stratified by type and reported per submission rather than in "
            "aggregate.",
        ),
    ),
    (
        "4 Threats to Validity",
        (
            "The baseline is drawn from records that were kept for administrative "
            "rather than research purposes, and their completeness varies by "
            "office and by year. Where a review is recorded without a date, the "
            "submission is excluded from the timing analysis but retained in the "
            "count of reviews, which biases the timing results toward submissions "
            "that were handled carefully enough to be documented carefully.",
            "The deployment was not randomised and could not have been. Every "
            "submission after the cutover used the new system and every submission "
            "before it used the old one, so any change in institutional practice "
            "over the same period is confounded with the intervention. The study "
            "reports what changed and is explicit that it cannot attribute all of "
            "the change to the system.",
            "Finally, the author population is small.",
        ),
    ),
    (
        "5 Results",
        (
            "Across the two years following deployment, approved submissions "
            "required a mean of four point one reviews each, against six point "
            "eight in the three years preceding it. The reduction is concentrated "
            "entirely in submissions that went through at least one round of "
            "revision, as the model predicts: submissions approved on first "
            "review are unaffected by the change and show no difference between "
            "the periods, which is a useful negative control because any "
            "difference there would indicate a confound rather than an effect.",
            "The effect is larger for disclosures than for protocol amendments, "
            "which is consistent with disclosures requiring more clearances and "
            "therefore having more redundant reviews available to eliminate. "
            "Protocol amendments, which typically require a single clearance, show "
            "a reduction that is small and not distinguishable from noise at this "
            "sample size.",
            "Median time to approval fell by a smaller proportion than review "
            "count did. This was expected. Eliminating a redundant review removes "
            "the reviewer's time but not the queueing delay in front of it, and in "
            "an institution where each office reviews on a weekly cycle the "
            "queueing delay dominates. The result suggests that the remaining "
            "delay is a scheduling problem rather than a workload problem, and "
            "that further improvement would come from changing when offices review "
            "rather than from removing more reviews.",
        ),
    ),
    (
        "6 Conclusion",
        (
            "Clearance-aware resubmission is a small change to how review state is "
            "represented and a large change to how much work a review process "
            "repeats. Representing the state of a multi-office review as a set of "
            "independent decisions rather than as a single status costs very "
            "little to implement and removes a class of redundant work that no "
            "amount of additional staffing would have removed, because the "
            "redundancy was in the representation rather than in the workload. "
            "Institutions with similar review structures should expect similar "
            "results, with the caveat that the benefit scales with the number of "
            "offices involved and is negligible where only one office reviews.",
        ),
    ),
)


def prose_document() -> NormalizedDocument:
    """The fixture, as a normalized document the chunker can consume."""
    elements: list[DocumentElement] = []
    for heading, paragraphs in _SECTIONS:
        elements.append(DocumentElement(kind=HEADING, text=heading, level=1))
        for paragraph in paragraphs:
            elements.append(DocumentElement(kind=PARAGRAPH, text=paragraph))
    return NormalizedDocument(title=TITLE, elements=tuple(elements))
