"""An Extractor that answers from memory (IR-838).

Returns a given document or raises a given error, so a test exercises the
task and the contract suite with no container. A callable result decides per
call, for a test whose answer depends on the bytes it was given.
"""

from typing import Callable, Union

from apps.ai.chunking.document import NormalizedDocument

from .ports import EmptyExtraction, ExtractedDocument, Provenance

Answer = Union[NormalizedDocument, BaseException]
Answers = Union[Answer, Callable[[bytes, str], Answer]]

PROVENANCE = Provenance(name="memory", version="1")


class InMemoryExtractor:
    def __init__(self, result: Answers, *, provenance: Provenance = PROVENANCE,
                 timeout_seconds: float = 60, failed_pages: tuple[int, ...] = ()):
        self._result = result
        self._provenance = provenance
        self._failed_pages = failed_pages
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
                                 failed_pages=self._failed_pages)
