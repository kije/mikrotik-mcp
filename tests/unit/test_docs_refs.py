"""Unit tests for the documentation-reference registry and resources."""

import json
import os
import urllib.request

import pytest

from mcp_mikrotik.docs_refs import SCOPE_DOCS, doc_for, doc_url


def test_every_scope_doc_has_valid_url():
    for scope, doc in SCOPE_DOCS.items():
        assert doc.path.startswith("/docs/") and not doc.path.endswith("/"), scope
        # Without the trailing slash the site redirects to plain http://.
        assert doc.url == f"https://manual.mikrotik.com{doc.path}/"
        assert doc.markdown_url.startswith(doc.url.rstrip("/"))
        assert doc.markdown_url.endswith(".md")
        assert doc.title


def test_markdown_url_of_leaf_and_section_pages():
    assert doc_for("ip_address").markdown_url == (
        "https://manual.mikrotik.com/docs/cli-reference/ip/address.md"
    )
    assert doc_for("ip_pool").markdown_url == (
        "https://manual.mikrotik.com/docs/cli-reference/ip/pool/pool.md"
    )


@pytest.mark.skipif(
    not os.environ.get("MIKROTIK_CHECK_DOC_URLS"),
    reason="network check; set MIKROTIK_CHECK_DOC_URLS=1 to run",
)
@pytest.mark.parametrize("scope", sorted(SCOPE_DOCS))
def test_doc_urls_resolve(scope):
    doc = SCOPE_DOCS[scope]
    for url in (doc.url, doc.markdown_url):
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
            assert r.status == 200, url
            assert r.geturl() == url, f"{url} redirected to {r.geturl()}"


def test_doc_for_accepts_bare_and_dotted():
    assert doc_for("ip_address") is not None
    assert doc_for("mcp_mikrotik.scope.ip_address") is doc_for("ip_address")


def test_doc_for_unknown_returns_none():
    assert doc_for("does_not_exist") is None
    assert doc_url("does_not_exist") is None


def test_doc_url_ip_address():
    assert doc_url("ip_address") == "https://manual.mikrotik.com/docs/cli-reference/ip/address/"


def test_docs_index_resource():
    from mcp_mikrotik import resources

    payload = json.loads(resources.docs_index())
    assert "introduction" in payload
    scopes = {o["scope"] for o in payload["objects"]}
    assert "ip_address" in scopes
    assert all("markdown_url" in o for o in payload["objects"])


def test_docs_for_scope_resource_known_and_unknown():
    from mcp_mikrotik import resources

    known = json.loads(resources.docs_for_scope("ip_address"))
    assert known["scope"] == "ip_address"
    assert known["url"].startswith("https://manual.mikrotik.com")

    unknown = json.loads(resources.docs_for_scope("nope"))
    assert "error" in unknown
    assert "ip_address" in unknown["known_scopes"]
