from __future__ import annotations

from typing import Any

import pytest

from lazylens.indexers.confluence import ConfluenceError, html_to_text, iter_confluence_items
from lazylens.models import SourceConfig


def test_iter_confluence_items_resolves_space_and_maps_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "base_url": "https://example.atlassian.net/wiki",
            "email": "rich@example.com",
            "api_token_env": "CONF_TOKEN",
            "space_keys": ["ARCH"],
        },
    )
    monkeypatch.setenv("CONF_TOKEN", "secret")
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
                        "body": {"storage": {"value": "<h1>API Decision</h1><p>Use a managed gateway.</p>"}},
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
    assert items[0].snippet == "API Decision Use a managed gateway."


def test_iter_confluence_items_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "base_url": "https://example.atlassian.net/wiki",
            "email": "rich@example.com",
            "api_token_env": "CONF_TOKEN",
            "space_keys": ["ARCH"],
        },
    )
    monkeypatch.delenv("CONF_TOKEN", raising=False)

    with pytest.raises(ConfluenceError, match="CONF_TOKEN"):
        iter_confluence_items(source, fetch_json=lambda *_args: {})


def test_html_to_text_compacts_storage_html() -> None:
    assert html_to_text("<h1>Title</h1><p> Useful <strong>context</strong>.</p>") == "Title Useful context ."
