import pytest

from apps.ai.chunking.tokens import get_tokenizer


@pytest.fixture(scope="session", autouse=True)
def _loaded_tokenizer():
    # IR-202: the first load takes ~250 ms, over Hypothesis's 200 ms deadline,
    # and the fast replay then reads as a flaky test. Load it before any example.
    get_tokenizer()
