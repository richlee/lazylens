from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from lazylens.extract import compact_text, useful_snippet
from lazylens.indexers.confluence import auth_headers
from lazylens.models import IndexedItem, SearchResult, SourceConfig
from lazylens.paths import default_confluence_env_path


JsonFetcher = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class JiraError(RuntimeError):
    pass


JIRA_FIELDS = [
    "summary",
    "description",
    "status",
    "issuetype",
    "project",
    "parent",
    "assignee",
    "updated",
    "created",
    "issuelinks",
]


def iter_jira_items(source: SourceConfig, *, fetch_json: JsonFetcher | None = None) -> list[IndexedItem]:
    items, _seen_item_keys, _unchanged, _complete = iter_jira_refresh(source, fetch_json=fetch_json)
    return items


def iter_jira_refresh(
    source: SourceConfig,
    *,
    existing_items: Mapping[str, SearchResult] | None = None,
    fetch_json: JsonFetcher | None = None,
) -> tuple[list[IndexedItem], set[str], int, bool]:
    base_url = jira_base_url(jira_setting(source, "base_url", "JIRA_BASE_URL"))
    email = jira_setting(source, "email", "JIRA_EMAIL")
    api_token_env = str(source.settings.get("api_token_env", "JIRA_API_TOKEN"))
    api_token = os.environ.get(api_token_env)
    if not api_token:
        raise JiraError(f"{source.key}: missing {api_token_env}. {jira_env_hint()}")

    headers = auth_headers(email, api_token)
    fetcher = fetch_json or fetch_jira_json
    jql = jira_jql(source)
    max_results = int(source.settings.get("issue_limit", 100))
    max_pages = int(source.settings.get("max_pages", 10))
    next_page_token = ""
    fetched_pages = 0
    items: list[IndexedItem] = []
    seen_item_keys: set[str] = set()
    unchanged = 0

    while fetched_pages < max_pages:
        request: dict[str, Any] = {
            "path": "/rest/api/3/search/jql",
            "method": "POST",
            "body": {
                "jql": jql,
                "fields": JIRA_FIELDS,
                "maxResults": max_results,
            },
        }
        if next_page_token:
            request["body"]["nextPageToken"] = next_page_token
        payload = fetcher(base_url, request, headers)
        fetched_pages += 1
        for issue in payload.get("issues", []):
            if not isinstance(issue, dict):
                continue
            item = jira_issue_to_item(source, base_url, issue)
            seen_item_keys.add(item.item_key)
            existing = existing_items.get(item.item_key) if existing_items else None
            if existing and jira_metadata_matches(existing, item):
                unchanged += 1
            else:
                items.append(item)
        next_page_token = str(payload.get("nextPageToken") or "")
        if not next_page_token:
            return items, seen_item_keys, unchanged, True

    return items, seen_item_keys, unchanged, False


def jira_issue_to_item(source: SourceConfig, base_url: str, issue: dict[str, Any]) -> IndexedItem:
    fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
    key = str(issue.get("key", ""))
    title = str(fields.get("summary") or key or "Untitled Jira issue")
    project = fields.get("project", {}) if isinstance(fields.get("project"), dict) else {}
    issue_type = fields.get("issuetype", {}) if isinstance(fields.get("issuetype"), dict) else {}
    status = fields.get("status", {}) if isinstance(fields.get("status"), dict) else {}
    assignee = fields.get("assignee", {}) if isinstance(fields.get("assignee"), dict) else {}
    parent = fields.get("parent", {}) if isinstance(fields.get("parent"), dict) else {}
    description = adf_text(fields.get("description"))
    status_name = str(status.get("name", ""))
    issue_type_name = str(issue_type.get("name", "Issue"))
    project_key = str(project.get("key", "Jira"))
    project_name = str(project.get("name", project_key))
    snippet = jira_snippet(issue_type_name=issue_type_name, status_name=status_name, description=description)
    links = jira_issue_links(fields, base_url)
    description_links = adf_links(fields.get("description"))
    if description_links:
        links.extend(description_links)
    if parent.get("key"):
        links.append(jira_issue_url(base_url, str(parent["key"])))
    return IndexedItem(
        source_key=source.key,
        item_key=key,
        title=f"{key} - {title}" if key and not title.startswith(key) else title,
        url=jira_issue_url(base_url, key) if key else base_url,
        path=f"{project_key}/{key}",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at=str(fields.get("updated") or fields.get("created") or datetime.now(timezone.utc).isoformat()),
        owner=str(assignee.get("displayName") or ""),
        category=project_name or project_key,
        container=project_key,
        snippet=snippet,
        links=tuple(deduplicate_links(links)),
        parent_key=str(parent.get("key") or ""),
        structure_type="page",
    )


def jira_issue_links(fields: dict[str, Any], base_url: str) -> list[str]:
    links: list[str] = []
    raw_links = fields.get("issuelinks", [])
    if not isinstance(raw_links, list):
        return links
    for issue_link in raw_links:
        if not isinstance(issue_link, dict):
            continue
        outward = issue_link.get("outwardIssue")
        inward = issue_link.get("inwardIssue")
        for linked_issue in [outward, inward]:
            if isinstance(linked_issue, dict) and linked_issue.get("key"):
                links.append(jira_issue_url(base_url, str(linked_issue["key"])))
    return links


def jira_snippet(*, issue_type_name: str, status_name: str, description: str) -> str:
    description_snippet = useful_snippet(description, limit=850) if description else ""
    parts = [part for part in [issue_type_name, status_name, description_snippet] if part]
    return compact_text(" | ".join(parts))


def adf_text(value: Any) -> str:
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content", []) if isinstance(node.get("content"), list) else []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            parts.append(node)

    walk(value)
    return compact_text(" ".join(parts))


def adf_links(value: Any) -> list[str]:
    links: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            marks = node.get("marks", [])
            if isinstance(marks, list):
                for mark in marks:
                    attrs = mark.get("attrs", {}) if isinstance(mark, dict) else {}
                    href = attrs.get("href") if isinstance(attrs, dict) else None
                    if href:
                        links.append(str(href))
            for child in node.get("content", []) if isinstance(node.get("content"), list) else []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return deduplicate_links(links)


def deduplicate_links(links: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for link in links:
        if not link or link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped


def jira_metadata_matches(existing: SearchResult, item: IndexedItem) -> bool:
    return (
        existing.title == item.title
        and existing.url == item.url
        and existing.path == item.path
        and existing.content_type == item.content_type
        and existing.modified_at == item.modified_at
        and existing.owner == item.owner
        and existing.category == item.category
        and existing.container == item.container
        and existing.snippet == item.snippet
        and existing.parent_key == item.parent_key
        and existing.structure_type == item.structure_type
    )


def jira_jql(source: SourceConfig) -> str:
    configured = str(source.settings.get("jql", "")).strip()
    if configured:
        return configured
    project_keys = string_list(source.settings.get("project_keys"))
    if not project_keys:
        raise JiraError(f"{source.key}: configure jql or project_keys")
    projects = ", ".join(json.dumps(project) for project in project_keys)
    return f"project in ({projects}) ORDER BY updated DESC"


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def jira_base_url(value: str) -> str:
    stripped = value.rstrip("/")
    if not stripped:
        raise JiraError(f"missing base_url or JIRA_BASE_URL. {jira_env_hint()}")
    return stripped.removesuffix("/wiki")


def jira_issue_url(base_url: str, key: str) -> str:
    return f"{base_url.rstrip('/')}/browse/{key}"


def jira_setting(source: SourceConfig, setting_key: str, env_key: str) -> str:
    value = source.settings.get(setting_key) or os.environ.get(env_key)
    if not value:
        raise JiraError(f"{source.key}: missing {setting_key} or {env_key}. {jira_env_hint()}")
    return str(value)


def jira_env_hint() -> str:
    return f"For zsh/bash run: source {default_confluence_env_path()}"


def fetch_jira_json(base_url: str, request: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    path = str(request["path"])
    params = request.get("params", {})
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    method = str(request.get("method", "GET"))
    body = request.get("body")
    data = None
    request_headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    http_request = Request(url, headers=request_headers, data=data, method=method)
    try:
        with urlopen(http_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise JiraError(f"Jira returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise JiraError(f"Could not reach Jira at {url}: {exc.reason}") from exc
