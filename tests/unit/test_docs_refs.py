"""Unit tests for the documentation-reference registry and resources."""

import asyncio
import json

from mcp_mikrotik.docs_refs import SCOPE_DOCS, doc_for, doc_url


def test_every_scope_doc_has_valid_url():
    for scope, doc in SCOPE_DOCS.items():
        assert doc.path.startswith("/docs/"), scope
        assert doc.url == f"https://manual.mikrotik.com{doc.path}"
        assert doc.markdown_url == f"{doc.url}.md"
        assert doc.title


def test_doc_for_accepts_bare_and_dotted():
    assert doc_for("ip_address") is not None
    assert doc_for("mcp_mikrotik.scope.ip_address") is doc_for("ip_address")


def test_doc_for_unknown_returns_none():
    assert doc_for("does_not_exist") is None
    assert doc_url("does_not_exist") is None


def test_doc_url_ip_address():
    assert doc_url("ip_address") == "https://manual.mikrotik.com/docs/cli-reference/ip/address"


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
