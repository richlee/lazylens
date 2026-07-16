from __future__ import annotations

import os
import ssl
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import certifi
import httpx

from lazylens.extract import compact_text
from lazylens.models import IndexedItem, SourceConfig


class ConfluenceError(RuntimeError):
    pass


class AtlassianClient:
    def __init__(self, *, base_url: str, email: str, api_token: str, timeout: float = 30.0) -> None:
        self.base_url = normalise_base_url(base_url)
        ssl_context = ssl.create_default_context(cafile=os.getenv("LAZYLENS_CA_BUNDLE") or certifi.where())
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(email, api_token),
            timeout=timeout,
            headers={"Accept": "application/json"},
            verify=ssl_context,
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(path, params={key: value for key, value in (params or {}).items() if value})
        except httpx.RequestError as exc:
            raise ConfluenceError(f"Atlassian request failed before receiving a response: {exc}") from exc
        if response.status_code in {401, 403}:
            raise ConfluenceError(
                f"Atlassian request failed: {response.status_code} {response.reason_phrase}. "
                "Check ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN and confirm access."
            )
        if response.status_code >= 400:
            raise ConfluenceError(f"Atlassian request failed: {response.status_code} {response.reason_phrase}.")
        return response.json()


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)

    def text(self) -> str:
        return compact_text(" ".join(self.parts))


def iter_confluence_items(source: SourceConfig, *, client: AtlassianClient | None = None) -> list[IndexedItem]:
    base_url = required_setting(source, "base_url")
    email = str(source.settings.get("email") or os.environ.get("ATLASSIAN_EMAIL") or "")
    if not email:
        raise ConfluenceError(f"{source.key}: missing email or ATLASSIAN_EMAIL")
    api_token_env = str(source.settings.get("api_token_env", "ATLASSIAN_API_TOKEN"))
    api_token = os.environ.get(api_token_env)
    if not api_token:
        raise ConfluenceError(f"{source.key}: set {api_token_env} with a Confluence API token")

    own_client = client is None
    atlassian = client or AtlassianClient(base_url=base_url, email=email, api_token=api_token)
    try:
        return [
            confluence_page_to_item(source, atlassian.base_url, page)
            for page in iter_confluence_pages(source, atlassian)
        ]
    finally:
        if own_client:
            atlassian.close()


def iter_confluence_pages(source: SourceConfig, client: AtlassianClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page_size = int(source.settings.get("page_limit", 25))
    max_results = int(source.settings.get("max_results", source.settings.get("page_limit", 100)))
    expand = str(source.settings.get("expand", "body.storage,space,version,history"))
    for cql in confluence_cql_queries(source):
        start = 0
        while len(results) < max_results:
            batch_limit = min(page_size, max_results - len(results))
            payload = client.get(
                "/wiki/rest/api/content/search",
                params={"cql": cql, "limit": batch_limit, "start": start, "expand": expand},
            )
            batch = [item for item in payload.get("results", []) if isinstance(item, dict)]
            results.extend(batch)
            if len(batch) < batch_limit:
                break
            start += len(batch)
    return results[:max_results]


def confluence_cql_queries(source: SourceConfig) -> list[str]:
    if source.settings.get("cql"):
        return [str(source.settings["cql"])]
    content_type = str(source.settings.get("content_type", "page"))
    queries = string_list(source.settings.get("space_keys"))
    if not queries:
        raise ConfluenceError(f"{source.key}: configure cql or space_keys")
    return [build_cql(space=space, content_type=content_type) for space in queries]


def build_cql(*, space: str, content_type: str) -> str:
    return f"space = {quote_cql_value(space)} AND type = {content_type} ORDER BY lastmodified DESC"


def quote_cql_value(value: str) -> str:
    if value.replace("_", "").isalnum():
        return value
    return '"' + value.replace('"', r"\"") + '"'


def confluence_page_to_item(source: SourceConfig, base_url: str, page: dict[str, Any]) -> IndexedItem:
    page_id = str(page.get("id", ""))
    title = str(page.get("title", page_id or "Untitled"))
    links = page.get("_links", {}) if isinstance(page.get("_links"), dict) else {}
    webui = str(links.get("webui", ""))
    url = urljoin(base_url.rstrip("/") + "/", webui.lstrip("/")) if webui else base_url
    storage = page.get("body", {}).get("storage", {}) if isinstance(page.get("body"), dict) else {}
    storage_value = str(storage.get("value", "")) if isinstance(storage, dict) else ""
    text = html_to_text(storage_value)
    space = page.get("space", {}) if isinstance(page.get("space"), dict) else {}
    version = page.get("version", {}) if isinstance(page.get("version"), dict) else {}
    history = page.get("history", {}) if isinstance(page.get("history"), dict) else {}
    owner = version_user(version) or history_user(history)
    category = str(space.get("key") or "Confluence")
    container = str(space.get("name") or category)
    return IndexedItem(
        source_key=source.key,
        item_key=page_id,
        title=title,
        url=url,
        path=f"{category}/{title}",
        content_type="text/html",
        modified_at=str(version.get("when") or page.get("createdAt") or ""),
        owner=owner,
        category=category,
        container=container,
        snippet=text[:500],
    )


def version_user(version: dict[str, Any]) -> str:
    by = version.get("by")
    if isinstance(by, dict):
        return str(by.get("displayName") or by.get("accountId") or "")
    return ""


def history_user(history: dict[str, Any]) -> str:
    by = history.get("createdBy")
    if isinstance(by, dict):
        return str(by.get("displayName") or by.get("accountId") or "")
    return ""


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return parser.text()


def required_setting(source: SourceConfig, name: str) -> str:
    value = source.settings.get(name) or (os.environ.get("ATLASSIAN_BASE_URL") if name == "base_url" else None)
    if not value:
        raise ConfluenceError(f"{source.key}: missing {name}")
    return str(value)


def normalise_base_url(value: str) -> str:
    url = value.rstrip("/")
    return url.removesuffix("/wiki")


def string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
