"""Conversation evidence is a pointer, never a second copy of Passage text."""
import copy
import hashlib
import re

from apps.ai.models import ChunkSet, DocumentChunk
from apps.ai.grants.reads import research_records


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


def _normalized(text):
    return " ".join(text.split())


def reader_view(comparison, user):
    """Withhold all comparison content if one supplied paper is no longer safe."""
    if not isinstance(comparison, dict):
        return None
    comparison = copy.deepcopy(comparison)
    versions = comparison.get("source_versions")
    if not isinstance(versions, list):
        return None
    permitted = research_records(user).in_bulk(
        {v.get("record_id") for v in versions if isinstance(v, dict)}
    )
    gate = _composition_root().vendor_permits()
    for version in versions:
        if not isinstance(version, dict):
            return None
        record = permitted.get(version.get("record_id"))
        if record is None or not gate(record):
            return None
        if version.get("chunk_set_id") is not None:
            if not ChunkSet.objects.filter(pk=version.get("chunk_set_id"), record=record,
                content_hash=version.get("content_hash"), is_active=True).exists():
                return None
        elif ChunkSet.objects.filter(record=record, is_active=True).exists():
            return None
    if {item.get("record_id") for item in comparison.get("records", [])} != {
        version.get("record_id") for version in versions
    }:
        return None
    version_by_record = {v["record_id"]: v for v in versions}
    for row in comparison.get("rows", []):
        for cell in row.get("cells", []):
            version = version_by_record.get(cell.get("record_id"))
            if version is None:
                return None
            for value in cell.get("values", []):
                for citation in value.get("citations", []):
                    chunk = DocumentChunk.objects.filter(pk=citation.get("chunk_id"),
                        record_id=cell["record_id"], chunk_set_id=version["chunk_set_id"],
                        source_page=citation.get("page"), deleted_at__isnull=True).first()
                    quote = resolved_quote(citation, chunk) if chunk else None
                    if chunk is None or not isinstance(quote, str) or _normalized(quote) not in _normalized(chunk.text):
                        return None
                    citation["quote"] = quote
                    citation.pop("span", None)
                    citation.pop("quote_hash", None)
    comparison.pop("source_versions", None)
    return comparison


def _composition_root():
    from apps.ai.composition import composition_root

    return composition_root()
