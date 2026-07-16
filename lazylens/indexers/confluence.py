from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from lazylens.extract import compact_text
from lazylens.models import IndexedItem, SourceConfig


JsonFetcher = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class ConfluenceError(RuntimeError):
    pass


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


def iter_confluence_items(source: SourceConfig, *, fetch_json: JsonFetcher | None = None) -> list[IndexedItem]:
    base_url = confluence_base_url(confluence_setting(source, "base_url", "CONFLUENCE_BASE_URL"))
    email = confluence_setting(source, "email", "CONFLUENCE_EMAIL")
    api_token_env = str(source.settings.get("api_token_env", "CONFLUENCE_API_TOKEN"))
    api_token = os.environ.get(api_token_env)
    if not api_token:
        raise ConfluenceError(f"{source.key}: set {api_token_env} with a Confluence API token")

    headers = auth_headers(email, api_token)
    fetcher = fetch_json or fetch_confluence_json
    spaces = resolve_spaces(source, base_url, headers, fetcher)
    items: list[IndexedItem] = []
    for space in spaces:
        items.extend(iter_space_pages(source, base_url, headers, fetcher, space))
    return items


def resolve_spaces(
    source: SourceConfig,
    base_url: str,
    headers: dict[str, str],
    fetch_json: JsonFetcher,
) -> list[dict[str, str]]:
    space_ids = string_list(source.settings.get("space_ids"))
    space_keys = string_list(source.settings.get("space_keys"))
    if space_ids:
        return [{"id": space_id, "key": space_id, "name": space_id} for space_id in space_ids]
    if not space_keys:
        raise ConfluenceError(f"{source.key}: configure space_keys or space_ids")

    payload = fetch_json(
        base_url,
        {"path": "/api/v2/spaces", "params": {"keys": space_keys, "limit": 250}},
        headers,
    )
    spaces = []
    for result in payload.get("results", []):
        if not isinstance(result, dict):
            continue
        spaces.append(
            {
                "id": str(result.get("id", "")),
                "key": str(result.get("key", "")),
                "name": str(result.get("name", result.get("key", ""))),
            }
        )
    missing = sorted(set(space_keys) - {space["key"] for space in spaces})
    if missing:
        raise ConfluenceError(f"{source.key}: space key(s) not found: {', '.join(missing)}")
    return spaces


def iter_space_pages(
    source: SourceConfig,
    base_url: str,
    headers: dict[str, str],
    fetch_json: JsonFetcher,
    space: dict[str, str],
) -> Iterable[IndexedItem]:
    limit = int(source.settings.get("page_limit", 100))
    max_pages = int(source.settings.get("max_pages", 5))
    path = "/api/v2/pages"
    params: dict[str, Any] = {"space-id": [space["id"]], "body-format": "storage", "limit": limit}
    fetched_pages = 0

    while path and fetched_pages < max_pages:
        payload = fetch_json(base_url, {"path": path, "params": params}, headers)
        fetched_pages += 1
        for page in payload.get("results", []):
            if isinstance(page, dict):
                yield confluence_page_to_item(source, base_url, page, space)

        next_path = payload.get("_links", {}).get("next") if isinstance(payload.get("_links"), dict) else None
        path = str(next_path) if next_path else ""
        params = {}


def confluence_page_to_item(
    source: SourceConfig,
    base_url: str,
    page: dict[str, Any],
    space: dict[str, str],
) -> IndexedItem:
    page_id = str(page.get("id", ""))
    title = str(page.get("title", page_id or "Untitled"))
    links = page.get("_links", {}) if isinstance(page.get("_links"), dict) else {}
    webui = str(links.get("webui", ""))
    url = urljoin(base_url.rstrip("/") + "/", webui.lstrip("/")) if webui else base_url
    storage = page.get("body", {}).get("storage", {}) if isinstance(page.get("body"), dict) else {}
    storage_value = str(storage.get("value", "")) if isinstance(storage, dict) else ""
    text = html_to_text(storage_value)
    version = page.get("version", {}) if isinstance(page.get("version"), dict) else {}
    modified_at = str(version.get("createdAt") or page.get("createdAt") or datetime.now(timezone.utc).isoformat())
    category = space.get("key") or space.get("name") or "Confluence"
    return IndexedItem(
        source_key=source.key,
        item_key=page_id,
        title=title,
        url=url,
        path=f"{space.get('key') or space.get('id')}/{title}",
        content_type="text/html",
        modified_at=modified_at,
        owner=str(page.get("ownerId") or page.get("authorId") or ""),
        category=category,
        container=space.get("name", category),
        snippet=text[:500],
    )


def fetch_confluence_json(base_url: str, request: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    path = str(request["path"])
    params = request.get("params") or {}
    query = urlencode(params, doseq=True)
    url = api_url(base_url, path)
    if query:
        url = f"{url}?{query}"
    http_request = Request(url, headers=headers)
    try:
        with urlopen(http_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ConfluenceError(f"Confluence returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise ConfluenceError(f"Confluence request failed for {url}: {exc.reason}") from exc


def auth_headers(email: str, api_token: str) -> dict[str, str]:
    token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
    return {
        "Accept": "application/json",
        "Authorization": f"Basic {token}",
    }


def api_url(base_url: str, path: str) -> str:
    if base_url.rstrip("/").endswith("/wiki") and path.startswith("/wiki/"):
        path = path.removeprefix("/wiki")
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def confluence_base_url(value: str) -> str:
    url = value.rstrip("/")
    return url if url.endswith("/wiki") else f"{url}/wiki"


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return parser.text()


def confluence_setting(source: SourceConfig, name: str, env_name: str) -> str:
    value = source.settings.get(name) or os.environ.get(env_name)
    if not value:
        raise ConfluenceError(f"{source.key}: missing {name} or {env_name}")
    return str(value)


def string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
