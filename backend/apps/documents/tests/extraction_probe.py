"""An independent extraction worker (IR-850).

Run by `test_offcampus_workers.py` as ``python -m
apps.documents.tests.extraction_probe RECORD_ID START_AT``, with its limits in
the environment, against the test database. It shares nothing with the test
process or the other probes but Postgres. It runs the real extraction task
with the in-memory Extractor standing in for an off-campus vendor, and prints
one JSON line: how many reads it sent and where its Extraction ended.
"""

import json
import sys
import time
from decimal import Decimal


def main() -> None:
    import django

    django.setup()

    from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
    from apps.ai.extraction import InMemoryExtractor, Usage, use_extractor
    from apps.documents import tasks
    from apps.documents.models import PdfExtraction

    record_id, start_at = int(sys.argv[1]), float(sys.argv[2])
    document = NormalizedDocument(
        title="Probe",
        elements=(DocumentElement(kind=PARAGRAPH, text="One passage.", page=1),),
        page_sizes={1: (612.0, 792.0)},
    )
    credits = Decimal(sys.argv[3]) if len(sys.argv) > 3 else None
    extractor = InMemoryExtractor(document, leaves_campus=True, usage=Usage(pages=1, credits=credits))
    # Chunking is another worker's job; this one only reads.
    tasks._queue_chunk_extraction = lambda *args: None
    time.sleep(max(0.0, start_at - time.time()))  # start together
    with use_extractor(extractor):
        tasks.extract_manuscript_text.apply(args=[record_id, None])
    extraction = PdfExtraction.objects.get(record_id=record_id)
    print(json.dumps({"sent": len(extractor.calls), "status": extraction.status,
                      "phase": extraction.phase}), flush=True)


if __name__ == "__main__":
    main()
