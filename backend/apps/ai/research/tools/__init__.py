from .aggregate import AGGREGATE_RECORDS
from .aggregates import CORPUS_FACETS, COUNT_RECORDS
from .extract import EXTRACT_EVIDENCE
from .passages import SEARCH_PASSAGES
from .read import READ_PAPERS
from .records import FIND_RECORDS
from .resolve import RESOLVE_PAPERS
from .search import SEARCH_RESEARCH
from .sections import READ_RECORD_SECTIONS
from .screening import SCREEN_RECORDS

TOOLS = (SEARCH_PASSAGES, FIND_RECORDS, READ_RECORD_SECTIONS, COUNT_RECORDS, CORPUS_FACETS, SCREEN_RECORDS)
#: The general-tools contract (IR-591); the six above stay for the legacy lane.
GENERAL_TOOLS = (RESOLVE_PAPERS, SEARCH_RESEARCH, READ_PAPERS, AGGREGATE_RECORDS, EXTRACT_EVIDENCE)
