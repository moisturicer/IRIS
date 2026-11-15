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
from apps.ai.extraction.llamaparse_client import _download, allowed_download

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
    "https://llamaparse-results.s3-fips.us-east-1.amazonaws.com/x",
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
    "https://s3-control.us-east-1.amazonaws.com/x",              # other S3-named services
    "https://x.s3-object-lambda.us-east-1.amazonaws.com/x",
    "https://x.s3-website-us-east-1.amazonaws.com/x",
    "https://x.s3-anything.amazonaws.com/x",
    "https://evil\n.s3.amazonaws.com/x",                         # a newline httpx won't accept
    "https://[s3.amazonaws.com]/x",
    "https://[::1/x",
    "file:///etc/passwd",
    "https://[::1]/x",
    "not a url",
    "",
    None,
    42,
]


@pytest.mark.parametrize("url", S3_URLS)
def test_amazon_s3_over_https_is_fetched(url):
    assert allowed_download(url)


@pytest.mark.parametrize("url", REFUSED_URLS)
def test_anything_else_is_refused(url):
    assert not allowed_download(url)


@pytest.mark.parametrize("url", REFUSED_URLS)
def test_every_refusal_is_unavailable_and_sends_nothing(url):
    class NeverCalled:
        def request(self, *args, **kwargs):
            raise AssertionError("a refused URL was requested")

    with pytest.raises(ExtractorUnavailable, match="is not an allowed result host"):
        _download(NeverCalled(), url)


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


def test_a_figure_pointing_elsewhere_is_unavailable_too(monkeypatch):
    """The grounded items pass; the figure crop's URL does not."""
    from .test_llamaparse_client import recording

    result = recording("figures")
    result["items"]["pages"][0]["items"].append(
        {"type": "image", "url": "image_0.png", "caption": "Figure 1.", "bbox": [{"x": 1, "y": 1, "w": 2, "h": 2}]})
    result["images_content_metadata"] = {"total_count": 1, "images": [
        {"index": 0, "filename": "image_0.png", "category": "layout", "content_type": "image/png",
         "bbox": {"x": 1, "y": 1, "w": 2, "h": 2}},
    ]}

    class ElsewhereVendor(Vendor):
        def _result(self):
            response = super()._result()
            body = response.json()
            body["images_content_metadata"]["images"][0]["presigned_url"] = "https://10.0.0.5/image_0.png"
            import httpx
            return httpx.Response(200, json=body)

    vendor = ElsewhereVendor("figures", result=result, images={"image_0.png": b"PNG crop"})

    with pytest.raises(ExtractorUnavailable, match="10.0.0.5 is not an allowed result host"):
        read(vendor, "figures")

    assert not [r for r in vendor.requests if r.url.host == "10.0.0.5"]
    assert [r.url.path for r in vendor.requests if r.url.host == llamaparse_vendor.DOWNLOAD_HOST] == [
        "/grounded_items.jsonl"]
