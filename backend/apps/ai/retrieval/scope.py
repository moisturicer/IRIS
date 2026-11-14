"""Which chunk set retrieval reads (IR-1051).

The active set, always, except in an evaluation run that names a trial
variant. Only `CompositionRoot.for_trial` passes one, and only
`eval_retrieval` calls that.
"""

from typing import Optional

from django.db.models import Q


def chunk_set_scope(prefix: str = "", trial_variant: Optional[str] = None) -> Q:
    """The chunk-set filter, with ``prefix`` naming the path to ``chunk_set``."""
    if trial_variant is None:
        return Q(**{f"{prefix}chunk_set__is_active": True})
    return Q(**{f"{prefix}chunk_set__trial_variant": trial_variant})
