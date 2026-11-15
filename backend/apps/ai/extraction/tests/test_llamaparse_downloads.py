"""
LlamaParse's presigned result URLs are checked before anything is fetched
(IR-929, ASVS 5.2.6).

The URLs arrive inside the vendor's response, so a compromised vendor or
response could otherwise point the extraction worker at any address it can
reach. Only https on the default port to Amazon S3 is fetched, plus any exact
host in LLAMAPARSE_DOWNLOAD_HOSTS. A refusal is `ExtractorUnavailable` (the
document isn't at fault), sends no request to the refused address, and still
deletes the uploaded file.
"""

import pytest

from apps.ai.extraction import ExtractorUnavailable
from apps.ai.extraction.llamaparse_client import allowed_download

from . import llamaparse_vendor
from .llamaparse_vendor import Vendor
from .test_llamaparse_client import read

S3_URLS = [
    "https://s3.amazonaws.com/llamaparse-results/job/image_0.png?X-Amz-Signature=s",
    "https://llamaparse-results.s3.amazonaws.com/image_0.png?X-Amz-Signature=s",
    "https://llamaparse-results.s3.us-east-1.amazonaws.com/grounded.jsonl",
    "https://llamaparse-results.s3.eu-central-1.amazonaws.com/grounded.jsonl",
    "https://llamaparse-results.s3-us-west-2.amazonaws.com/grounded.jsonl",
    "https://llamaparse-results.s3.dualstack.us-east-1.amazonaws.com/x",
    "https://S3.AMAZONAWS.COM/bucket/x",
    "https://s3.amazonaws.com:443/bucket/x",
]

REFUSED_URLS = [
    "http://llamaparse-results.s3.amazonaws.com/x",              # not https
    "https://llamaparse-results.s3.amazonaws.com:8443/x",        # another port
    "https://169.254.169.254/latest/meta-data/",                  # instance metadata
    "https://backend:8000/api/v1/records/",                       # a service inside
    "https://localhost/x",
    "https://bucket.test/x",
    "https://amazonaws.com.evil.example/x",
    "https://s3.amazonaws.com.evil.example/x",
    "https://abc123.execute-api.us-east-1.amazonaws.com/x",      # another AWS service
    "https://s3-1234567890.us-west-2.elb.amazonaws.com/x",       # a load balancer named s3
    "https://user:pass@s3.amazonaws.com/x",                       # credentials in the URL
    "file:///etc/passwd",
    "https://[::1]/x",
    "not a url",
    "",
]


@pytest.mark.parametrize("url", S3_URLS)
def test_amazon_s3_over_https_is_fetched(url):
    assert allowed_download(url)


@pytest.mark.parametrize("url", REFUSED_URLS)
def test_anything_else_is_refused(url):
    assert not allowed_download(url)


def test_a_listed_host_is_fetched_and_only_exactly():
    listed = frozenset({"results.llamaindex.example"})
    assert allowed_download("https://results.llamaindex.example/x", listed)
    assert not allowed_download("https://evil.results.llamaindex.example/x", listed)
    assert not allowed_download("http://results.llamaindex.example/x", listed)


def test_a_result_pointing_elsewhere_is_unavailable_and_nothing_is_fetched(monkeypatch):
    monkeypatch.setattr(llamaparse_vendor, "DOWNLOADS", "https://169.254.169.254/latest")
    vendor = Vendor("figures")

    with pytest.raises(ExtractorUnavailable, match="169.254.169.254 is not an allowed result host") as refused:
        read(vendor, "figures")

    assert "X-Amz" not in str(refused.value)
    assert not [r for r in vendor.requests if r.url.host == "169.254.169.254"]
    # The uploaded file is still deleted (ADR-056 decision 7).
    assert (vendor.requests[-1].method, vendor.requests[-1].url.host) == ("DELETE", "api.vendor.test")


def test_the_setting_lets_a_new_host_through(monkeypatch):
    monkeypatch.setattr(llamaparse_vendor, "DOWNLOADS", "https://results.llamaindex.example")
    monkeypatch.setattr(llamaparse_vendor, "DOWNLOAD_HOST", "results.llamaindex.example")
    vendor = Vendor("figures")

    extracted = read(vendor, "figures", download_hosts=("Results.LlamaIndex.example",))

    fetched = [r.url.path for r in vendor.requests if r.url.host == "results.llamaindex.example"]
    assert fetched == ["/grounded_items.jsonl"]
    assert extracted.raw["grounded_items"]
