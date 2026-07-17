from __future__ import annotations

from typing import Any

import pytest

from lazylens.indexers.jira import JiraError, adf_links, adf_text, iter_jira_items, iter_jira_refresh, jira_jql
from lazylens.models import SearchResult, SourceConfig


def test_iter_jira_items_maps_issues_and_links(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="jira",
        name="Jira",
        type="jira",
        settings={"project_keys": ["LAZY"]},
    )
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "rich@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "secret")
    calls: list[dict[str, Any]] = []

    def fetch_json(_base_url: str, request: dict[str, Any], _headers: dict[str, str]) -> dict[str, Any]:
        calls.append(request)
        assert request["path"] == "/rest/api/3/search/jql"
        assert request["method"] == "POST"
        assert request["body"]["jql"] == 'project in ("LAZY") ORDER BY updated DESC'
        return {
            "issues": [
                {
                    "key": "LAZY-1",
                    "fields": {
                        "summary": "Build document graph",
                        "updated": "2026-07-17T10:00:00.000+0000",
                        "project": {"key": "LAZY", "name": "LazyLens"},
                        "issuetype": {"name": "Epic"},
                        "status": {"name": "In Progress"},
                        "assignee": {"displayName": "Rich Lee"},
                        "description": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": (
                                                "Connect Confluence design pages to Jira epics and implementation "
                                                "tickets so architecture context remains navigable from the terminal."
                                            ),
                                            "marks": [
                                                {
                                                    "type": "link",
                                                    "attrs": {
                                                        "href": (
                                                            "https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD"
                                                        )
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                        "issuelinks": [
                            {
                                "outwardIssue": {
                                    "key": "LAZY-2",
                                    "fields": {"summary": "Implement indexer"},
                                }
                            }
                        ],
                    },
                },
                {
                    "key": "LAZY-2",
                    "fields": {
                        "summary": "Implement indexer",
                        "updated": "2026-07-17T11:00:00.000+0000",
                        "project": {"key": "LAZY", "name": "LazyLens"},
                        "issuetype": {"name": "Story"},
                        "status": {"name": "To Do"},
                        "parent": {"key": "LAZY-1"},
                    },
                },
            ]
        }

    items = iter_jira_items(source, fetch_json=fetch_json)

    assert len(calls) == 1
    assert len(items) == 2
    epic = items[0]
    story = items[1]
    assert epic.item_key == "LAZY-1"
    assert epic.title == "LAZY-1 - Build document graph"
    assert epic.url == "https://example.atlassian.net/browse/LAZY-1"
    assert epic.category == "LazyLens"
    assert epic.container == "LAZY"
    assert epic.content_type == "application/vnd.atlassian.jira.issue"
    assert epic.owner == "Rich Lee"
    assert epic.snippet.startswith("Epic | In Progress | Connect Confluence design pages")
    assert epic.links == (
        "https://example.atlassian.net/browse/LAZY-2",
        "https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD",
    )
    assert story.parent_key == "LAZY-1"
    assert story.links == ("https://example.atlassian.net/browse/LAZY-1",)


def test_iter_jira_refresh_reports_unchanged_items(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="jira",
        name="Jira",
        type="jira",
        settings={"jql": "project = LAZY"},
    )
    existing = SearchResult(
        id=1,
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Build document graph",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T10:00:00.000+0000",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic | In Progress",
        rank=0.0,
        parent_key="",
        structure_type="page",
    )
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "rich@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "secret")

    def fetch_json(_base_url: str, _request: dict[str, Any], _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "issues": [
                {
                    "key": "LAZY-1",
                    "fields": {
                        "summary": "Build document graph",
                        "updated": "2026-07-17T10:00:00.000+0000",
                        "project": {"key": "LAZY", "name": "LazyLens"},
                        "issuetype": {"name": "Epic"},
                        "status": {"name": "In Progress"},
                    },
                }
            ]
        }

    items, seen_item_keys, unchanged, complete = iter_jira_refresh(
        source,
        existing_items={"LAZY-1": existing},
        fetch_json=fetch_json,
    )

    assert items == []
    assert seen_item_keys == {"LAZY-1"}
    assert unchanged == 1
    assert complete is True


def test_iter_jira_items_requires_default_token(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceConfig(
        key="jira",
        name="Jira",
        type="jira",
        settings={"project_keys": ["LAZY"]},
    )
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "rich@example.com")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    with pytest.raises(JiraError, match="JIRA_API_TOKEN"):
        iter_jira_items(source, fetch_json=lambda *_args: {})


def test_jira_jql_requires_jql_or_project_keys() -> None:
    source = SourceConfig(key="jira", name="Jira", type="jira")

    with pytest.raises(JiraError, match="jql or project_keys"):
        jira_jql(source)


def test_adf_text_and_links_extract_nested_content() -> None:
    value = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "See "},
                    {
                        "type": "text",
                        "text": "architecture",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.test/doc"}}],
                    },
                ],
            }
        ],
    }

    assert adf_text(value) == "See architecture"
    assert adf_links(value) == ["https://example.test/doc"]
