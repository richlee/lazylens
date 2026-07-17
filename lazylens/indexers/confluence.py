from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from lazylens.extract import compact_text, useful_snippet
from lazylens.models import IndexedItem, SourceConfig
from lazylens.paths import default_confluence_env_path


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


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self.links.append(href)


class BlockExtractor(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)

    def text(self) -> str:
        raw = " ".join(self.parts)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def iter_confluence_items(source: SourceConfig, *, fetch_json: JsonFetcher | None = None) -> list[IndexedItem]:
    base_url = confluence_base_url(confluence_setting(source, "base_url", "CONFLUENCE_BASE_URL"))
    email = confluence_setting(source, "email", "CONFLUENCE_EMAIL")
    api_token_env = str(source.settings.get("api_token_env", "CONFLUENCE_API_TOKEN"))
    api_token = os.environ.get(api_token_env)
    if not api_token:
        raise ConfluenceError(f"{source.key}: missing {api_token_env}. {confluence_env_hint()}")

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
                "homepageId": str(result.get("homepageId", "")),
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
    pages: list[dict[str, Any]] = []

    while path and fetched_pages < max_pages:
        payload = fetch_json(base_url, {"path": path, "params": params}, headers)
        fetched_pages += 1
        for page in payload.get("results", []):
            if isinstance(page, dict):
                pages.append(page)

        next_path = payload.get("_links", {}).get("next") if isinstance(payload.get("_links"), dict) else None
        path = str(next_path) if next_path else ""
        params = {}

    structure_nodes = confluence_structure_nodes(base_url, headers, fetch_json, pages)
    hierarchy = confluence_hierarchy(pages, str(space.get("homepageId", "")), structure_nodes)
    for node in structure_nodes.values():
        if node.get("type") == "folder":
            yield confluence_folder_to_item(source, base_url, node, space, hierarchy)
    for page in pages:
        yield confluence_page_to_item(source, base_url, page, space, hierarchy)


def confluence_page_to_item(
    source: SourceConfig,
    base_url: str,
    page: dict[str, Any],
    space: dict[str, str],
    hierarchy: dict[str, dict[str, str]] | None = None,
) -> IndexedItem:
    page_id = str(page.get("id", ""))
    title = str(page.get("title", page_id or "Untitled"))
    links = page.get("_links", {}) if isinstance(page.get("_links"), dict) else {}
    webui = str(links.get("webui", ""))
    url = confluence_web_url(base_url, webui) if webui else base_url
    storage = page.get("body", {}).get("storage", {}) if isinstance(page.get("body"), dict) else {}
    storage_value = str(storage.get("value", "")) if isinstance(storage, dict) else ""
    text = html_to_text(storage_value)
    snippet = html_snippet(storage_value)
    page_links = html_links(storage_value, base_url)
    version = page.get("version", {}) if isinstance(page.get("version"), dict) else {}
    modified_at = str(version.get("createdAt") or page.get("createdAt") or datetime.now(timezone.utc).isoformat())
    structure = hierarchy.get(page_id, {}) if hierarchy else {}
    category = structure.get("top_title") or space.get("key") or space.get("name") or "Confluence"
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
        snippet=snippet,
        links=tuple(page_links),
        parent_key=str(page.get("parentId") or ""),
        structure_type=str(page.get("type") or "page"),
    )


def confluence_folder_to_item(
    source: SourceConfig,
    base_url: str,
    folder: dict[str, Any],
    space: dict[str, str],
    hierarchy: dict[str, dict[str, str]],
) -> IndexedItem:
    folder_id = str(folder.get("id", ""))
    title = str(folder.get("title", folder_id or "Untitled folder"))
    structure = hierarchy.get(folder_id, {})
    category = structure.get("top_title") or space.get("key") or space.get("name") or "Confluence"
    version = folder.get("version", {}) if isinstance(folder.get("version"), dict) else {}
    modified_at = str(version.get("createdAt") or folder.get("createdAt") or datetime.now(timezone.utc).isoformat())
    return IndexedItem(
        source_key=source.key,
        item_key=folder_id,
        title=title,
        url=confluence_web_url(base_url, str(folder.get("_links", {}).get("base", ""))) if isinstance(folder.get("_links"), dict) else base_url,
        path=f"{space.get('key') or space.get('id')}/{title}",
        content_type="application/vnd.atlassian.confluence.folder",
        modified_at=modified_at,
        owner=str(folder.get("ownerId") or folder.get("authorId") or ""),
        category=category,
        container=space.get("name", category),
        snippet="",
        parent_key=str(folder.get("parentId") or ""),
        structure_type="folder",
    )


def confluence_structure_nodes(
    base_url: str,
    headers: dict[str, str],
    fetch_json: JsonFetcher,
    pages: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    nodes = {str(page.get("id", "")): page for page in pages if page.get("id")}
    for page in pages:
        page_id = str(page.get("id", ""))
        if not page_id:
            continue
        for child in confluence_direct_children(base_url, headers, fetch_json, page_id):
            child_id = str(child.get("id", ""))
            if not child_id or child_id in nodes:
                continue
            if not child.get("parentId"):
                child = {**child, "parentId": page_id}
            nodes[child_id] = child
    return nodes


def confluence_direct_children(
    base_url: str,
    headers: dict[str, str],
    fetch_json: JsonFetcher,
    page_id: str,
) -> list[dict[str, Any]]:
    try:
        payload = fetch_json(
            base_url,
            {"path": f"/api/v2/pages/{page_id}/direct-children", "params": {"limit": 250}},
            headers,
        )
    except ConfluenceError:
        return []
    return [child for child in payload.get("results", []) if isinstance(child, dict)]


def confluence_hierarchy(
    pages: list[dict[str, Any]],
    homepage_id: str,
    structure_nodes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, str]]:
    node_by_id = structure_nodes or {str(page.get("id", "")): page for page in pages}
    hierarchy = {}
    for node in node_by_id.values():
        node_id = str(node.get("id", ""))
        top = top_level_node(node, node_by_id, homepage_id)
        hierarchy[node_id] = {
            "top_id": str(top.get("id", "")) if top else node_id,
            "top_title": str(top.get("title", "")) if top else str(node.get("title", "")),
        }
    return hierarchy


def top_level_node(
    page: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
    homepage_id: str,
) -> dict[str, Any] | None:
    current = page
    seen = set()
    while current:
        current_id = str(current.get("id", ""))
        parent_id = str(current.get("parentId") or "")
        if not parent_id or parent_id == homepage_id or parent_id not in node_by_id:
            return current
        if current_id in seen:
            return current
        seen.add(current_id)
        current = node_by_id[parent_id]
    return None


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
        raise ConfluenceError(f"Confluence returned HTTP {exc.code} for {url}. {confluence_http_hint(exc.code)}") from exc
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


def confluence_web_url(base_url: str, path: str) -> str:
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


def html_snippet(value: str, *, limit: int = 1_200) -> str:
    parser = BlockExtractor()
    parser.feed(value)
    return useful_snippet(parser.text(), limit=limit)


def html_links(value: str, base_url: str) -> list[str]:
    parser = LinkExtractor()
    parser.feed(value)
    seen = set()
    links = []
    for link in parser.links:
        absolute_url = confluence_web_url(base_url, link)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        links.append(absolute_url)
    return links


def confluence_setting(source: SourceConfig, name: str, env_name: str) -> str:
    value = source.settings.get(name) or os.environ.get(env_name)
    if not value:
        raise ConfluenceError(f"{source.key}: missing {name} or {env_name}. {confluence_env_hint()}")
    return str(value)


def confluence_env_hint() -> str:
    env_file = default_confluence_env_path()
    if env_file.exists():
        return f"Set Confluence env vars in this shell, for example: source {env_file}"
    return f"Set Confluence env vars, or create and source {env_file}"


def confluence_http_hint(status_code: int) -> str:
    if status_code in {401, 403}:
        return f"Check CONFLUENCE_EMAIL and API token, then source {default_confluence_env_path()}."
    if status_code == 404:
        return (
            "Check CONFLUENCE_BASE_URL, space visibility, and that this shell has loaded the intended env vars. "
            f"For zsh/bash: source {default_confluence_env_path()}."
        )
    return f"Check the Confluence configuration and env vars. For zsh/bash: source {default_confluence_env_path()}."


def string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
