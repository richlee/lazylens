from __future__ import annotations

from typing import Any

import pytest

from lazylens.indexers.confluence import (
    ConfluenceError,
    confluence_base_url,
    html_links,
    html_snippet,
    html_to_text,
    iter_confluence_items,
)
from lazylens.models import SourceConfig


def test_iter_confluence_items_resolves_space_and_maps_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "space_keys": ["ARCH"],
        },
    )
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://example.atlassian.net/wiki")
    monkeypatch.setenv("CONFLUENCE_EMAIL", "rich@example.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "secret")
    calls: list[dict[str, Any]] = []

    def fetch_json(_base_url: str, request: dict[str, Any], _headers: dict[str, str]) -> dict[str, Any]:
        calls.append(request)
        if request["path"] == "/api/v2/spaces":
            return {"results": [{"id": "123", "key": "ARCH", "name": "Architecture"}]}
        if request["path"] == "/api/v2/pages":
            return {
                "results": [
                    {
                        "id": "456",
                        "title": "API Decision",
                        "_links": {"webui": "/spaces/ARCH/pages/456/API+Decision"},
                        "body": {
                            "storage": {
                                "value": (
                                    "<p>Document type</p><p>Decision record</p><p>Status</p><p>Candidate</p>"
                                    "<p>Use a managed gateway because the team needs consistent authentication, "
                                    "routing, and observability before service ownership becomes more distributed.</p>"
                                    '<p><a href="/wiki/spaces/ARCH/pages/789/HLD">HLD</a></p>'
                                )
                            }
                        },
                        "version": {"createdAt": "2026-07-16T12:00:00.000Z"},
                        "ownerId": "abc",
                    }
                ],
                "_links": {},
            }
        raise AssertionError(request)

    items = iter_confluence_items(source, fetch_json=fetch_json)

    assert calls[0]["params"]["keys"] == ["ARCH"]
    assert calls[1]["params"]["space-id"] == ["123"]
    assert len(items) == 1
    assert items[0].source_key == "work"
    assert items[0].item_key == "456"
    assert items[0].title == "API Decision"
    assert items[0].url == "https://example.atlassian.net/wiki/spaces/ARCH/pages/456/API+Decision"
    assert items[0].category == "ARCH"
    assert items[0].container == "Architecture"
    assert items[0].snippet == (
        "Use a managed gateway because the team needs consistent authentication, routing, and observability before "
        "service ownership becomes more distributed."
    )
    assert items[0].links == ("https://example.atlassian.net/wiki/spaces/ARCH/pages/789/HLD",)


def test_iter_confluence_items_requires_default_token(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "space_keys": ["ARCH"],
        },
    )
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://example.atlassian.net/wiki")
    monkeypatch.setenv("CONFLUENCE_EMAIL", "rich@example.com")
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)

    with pytest.raises(ConfluenceError, match="CONFLUENCE_API_TOKEN"):
        iter_confluence_items(source, fetch_json=lambda *_args: {})


def test_iter_confluence_items_supports_custom_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "base_url": "https://example.atlassian.net/wiki",
            "email": "rich@example.com",
            "api_token_env": "CUSTOM_CONFLUENCE_TOKEN",
            "space_ids": ["123"],
        },
    )
    monkeypatch.setenv("CUSTOM_CONFLUENCE_TOKEN", "secret")

    def fetch_json(_base_url: str, request: dict[str, Any], _headers: dict[str, str]) -> dict[str, Any]:
        assert request["path"] == "/api/v2/pages"
        return {"results": []}

    assert iter_confluence_items(source, fetch_json=fetch_json) == []


def test_html_to_text_compacts_storage_html() -> None:
    assert html_to_text("<h1>Title</h1><p> Useful <strong>context</strong>.</p>") == "Title Useful context ."


def test_html_links_normalises_confluence_urls() -> None:
    links = html_links(
        '<a href="/wiki/spaces/ARCH/pages/123/HLD">HLD</a>'
        '<a href="/spaces/ARCH/pages/456/LLD">LLD</a>'
        '<a href="/wiki/spaces/ARCH/pages/123/HLD">HLD again</a>',
        "https://example.atlassian.net/wiki",
    )

    assert links == [
        "https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD",
        "https://example.atlassian.net/wiki/spaces/ARCH/pages/456/LLD",
    ]


def test_html_snippet_selects_useful_paragraph() -> None:
    html = (
        "<p>Document type</p><p>Product page</p><p>Status</p><p>Candidate</p>"
        "<h1>Product page</h1>"
        "<p>lazylens is a local-first document landscape explorer for work knowledge across Confluence, SharePoint, "
        "and local folders.</p>"
    )

    assert html_snippet(html) == (
        "lazylens is a local-first document landscape explorer for work knowledge across Confluence, SharePoint, "
        "and local folders."
    )


def test_confluence_base_url_accepts_site_root_or_wiki_url() -> None:
    assert confluence_base_url("https://example.atlassian.net") == "https://example.atlassian.net/wiki"
    assert confluence_base_url("https://example.atlassian.net/wiki") == "https://example.atlassian.net/wiki"
