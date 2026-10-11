"""Possible duplicates, reported as flags; distinct records are never merged."""

from collections import defaultdict
from itertools import combinations
import re
import unicodedata

from django.conf import settings
from pgvector.django import CosineDistance

from apps.ai.models.embedding import RecordEmbedding

from .tools.common import disclosable


def possible_duplicates(run, evidence):
    handles = {e.record_id: e.handle for e in evidence}
    allowed = disclosable(run.ctx, handles)
    reasons = defaultdict(set)
    by_title = defaultdict(list)
    for pk, record in allowed.items():
        normalized = " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", record.title).casefold()))
        if normalized:
            by_title[normalized].append(pk)
    for ids in by_title.values():
        for a, b in combinations(sorted(ids), 2):
            reasons[(a, b)].add("normalized_title")

    vectors = RecordEmbedding.objects.filter(record_id__in=allowed)
    maximum_distance = 1 - settings.AI_SCREEN_DUPLICATE_MIN_SIMILARITY
    for seed in vectors.order_by("record_id"):
        close = (vectors.filter(model_name=seed.model_name, record_id__gt=seed.record_id)
                 .annotate(distance=CosineDistance("embedding", seed.embedding))
                 .filter(distance__lte=maximum_distance).order_by()
                 .values_list("record_id", flat=True))
        for pk in close:
            reasons[(seed.record_id, pk)].add("record_embedding")
    return [{"records": [handles[a], handles[b]], "reasons": sorted(codes)}
            for (a, b), codes in sorted(reasons.items())]
