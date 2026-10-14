"""Conversation evidence is a pointer, never a second copy of Passage text."""
import copy
import hashlib
import re

from apps.ai.models import DocumentChunk


def comparison_pointers(comparison):
    if not comparison:
        return {}
    stored = copy.deepcopy(comparison)
    ids = {citation["chunk_id"] for row in stored["rows"] for cell in row["cells"]
           for value in cell["values"] for citation in value["citations"]}
    chunks = DocumentChunk.objects.in_bulk(ids)
    for row in stored["rows"]:
        for cell in row["cells"]:
            for value in cell["values"]:
                for citation in value["citations"]:
                    quote = citation.pop("quote")
                    chunk = chunks[citation["chunk_id"]]
                    pattern = r"\s+".join(re.escape(word) for word in quote.split())
                    match = re.search(pattern, chunk.text)
                    if match is None:
                        raise ValueError("comparison_quote_changed")
                    citation["span"] = [match.start(), match.end()]
                    citation["quote_hash"] = hashlib.sha256(match.group().encode()).hexdigest()
    return stored


def resolved_quote(citation, chunk):
    if "quote" in citation:
        return citation["quote"]
    span = citation.get("span", [])
    if len(span) != 2 or any(type(index) is not int for index in span):
        return None
    start, end = span
    if not 0 <= start < end <= len(chunk.text):
        return None
    quote = chunk.text[start:end]
    if hashlib.sha256(quote.encode()).hexdigest() != citation.get("quote_hash"):
        return None
    return quote
