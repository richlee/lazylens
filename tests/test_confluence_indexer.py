from __future__ import annotations

from typing import Any

import pytest

from lazylens.indexers.confluence import (
    ConfluenceError,
    build_cql,
    html_to_text,
    iter_confluence_items,
    quote_cql_value,
)
from lazylens.models import SourceConfig


class FakeAtlassianClient:
    def __init__(self) -> None:
        self.base_url = "https://example.atlassian.net"
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((path, params))
        return {
            "results": [
                {
                    "id": "456",
                    "title": "API Decision",
                    "_links": {"webui": "/wiki/spaces/ARCH/pages/456/API+Decision"},
                    "space": {"key": "ARCH", "name": "Architecture"},
                    "body": {"storage": {"value": "<h1>API Decision</h1><p>Use a managed gateway.</p>"}},
                    "version": {
                        "when": "2026-07-16T12:00:00.000Z",
                        "by": {"displayName": "Rich Lee"},
                    },
                }
            ]
        }


def test_iter_confluence_items_searches_cql_and_maps_pages(monkeypatch: pytest.MonkeyPatch) -> None:
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
    client = FakeAtlassianClient()

    items = iter_confluence_items(source, client=client)  # type: ignore[arg-type]

    assert client.calls == [
        (
            "/wiki/rest/api/content/search",
            {
                "cql": "space = ARCH AND type = page ORDER BY lastmodified DESC",
                "limit": 25,
                "start": 0,
                "expand": "body.storage,space,version,history",
            },
        )
    ]
    assert len(items) == 1
    assert items[0].source_key == "work"
    assert items[0].item_key == "456"
    assert items[0].title == "API Decision"
    assert items[0].url == "https://example.atlassian.net/wiki/spaces/ARCH/pages/456/API+Decision"
    assert items[0].category == "ARCH"
    assert items[0].container == "Architecture"
    assert items[0].owner == "Rich Lee"
    assert items[0].snippet == "API Decision Use a managed gateway."


def test_iter_confluence_items_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="work",
        name="Work Confluence",
        type="confluence",
        settings={
            "base_url": "https://example.atlassian.net",
            "email": "rich@example.com",
            "api_token_env": "CONF_TOKEN",
            "space_keys": ["ARCH"],
        },
    )
    monkeypatch.delenv("CONF_TOKEN", raising=False)

    with pytest.raises(ConfluenceError, match="CONF_TOKEN"):
        iter_confluence_items(source, client=FakeAtlassianClient())  # type: ignore[arg-type]


def test_build_cql_quotes_non_simple_space_keys() -> None:
    assert build_cql(space="ARCH", content_type="page") == "space = ARCH AND type = page ORDER BY lastmodified DESC"
    assert quote_cql_value("DSP Beta") == '"DSP Beta"'


def test_html_to_text_compacts_storage_html() -> None:
    assert html_to_text("<h1>Title</h1><p> Useful <strong>context</strong>.</p>") == "Title Useful context ."
