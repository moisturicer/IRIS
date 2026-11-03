"""An Extractor that answers from memory (IR-838).

Returns a given document or raises a given error, so a test exercises the
task and the contract suite with no container. A callable result decides per
call, for a test whose answer depends on the bytes it was given.

``leaves_campus=True`` stands in for an off-campus vendor (IR-850): it is then
gated and admitted, and reports ``usage``.
"""

from typing import Callable, Optional, Union

from apps.ai.chunking.document import NormalizedDocument

from .ports import EmptyExtraction, ExtractedDocument, Provenance, Usage

Answer = Union[NormalizedDocument, BaseException]
Answers = Union[Answer, Callable[[bytes, str], Answer]]

PROVENANCE = Provenance(name="memory", version="1")


class InMemoryExtractor:
    model = "memory"

    def __init__(
        self,
        result: Answers,
        *,
        provenance: Provenance = PROVENANCE,
        timeout_seconds: float = 60,
        failed_pages: tuple[int, ...] = (),
        leaves_campus: bool = False,
        usage: Optional[Usage] = None,
        account: str = "memory-account",
    ):
        self._result = result
        self._provenance = provenance
        self._failed_pages = failed_pages
        self.leaves_campus = leaves_campus
        self._usage = usage
        self.account = account
        self.timeout_seconds = timeout_seconds
        self.calls: list[tuple[bytes, str]] = []

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument:
        self.calls.append((pdf_bytes, filename))
        outcome = self._result(pdf_bytes, filename) if callable(self._result) else self._result
        if isinstance(outcome, BaseException):
            raise outcome
        if not outcome.elements:
            raise EmptyExtraction(f"no extractable content for {filename!r}")
        return ExtractedDocument(document=outcome, provenance=self._provenance,
                                 failed_pages=self._failed_pages, usage=self._usage)
