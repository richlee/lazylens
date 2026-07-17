from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from lazylens.extract import read_text_preview
from lazylens.models import IndexedItem, SearchResult, SourceConfig


SKIP_PARTS = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules"}


def iter_local_items(source: SourceConfig) -> list[IndexedItem]:
    items, _seen_item_keys, _unchanged = iter_local_refresh(source)
    return items


def iter_local_refresh(
    source: SourceConfig,
    *,
    existing_items: Mapping[str, SearchResult] | None = None,
) -> tuple[list[IndexedItem], set[str], int]:
    if source.root is None:
        raise ValueError(f"{source.key} has no root configured")
    root = source.root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)

    items: list[IndexedItem] = []
    seen_keys: set[str] = set()
    unchanged = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        seen_keys.add(relative)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        url = local_url(source, path, relative)
        category = local_category(relative)
        container = local_container(relative)
        existing = existing_items.get(relative) if existing_items else None
        if (
            existing
            and existing.modified_at == modified_at
            and existing.path == str(path)
            and existing.url == url
            and existing.content_type == content_type
            and existing.category == category
            and existing.container == container
        ):
            unchanged += 1
            continue
        title, snippet = read_text_preview(path)
        items.append(
            IndexedItem(
                source_key=source.key,
                item_key=relative,
                title=title,
                url=url,
                path=str(path),
                content_type=content_type,
                modified_at=modified_at,
                owner="",
                category=category,
                container=container,
                snippet=snippet,
            )
        )
    return items, seen_keys, unchanged


def local_url(source: SourceConfig, path: Path, relative: str) -> str:
    if source.url_prefix:
        return source.url_prefix.rstrip("/") + "/" + relative
    return path.resolve().as_uri()


def local_category(relative: str) -> str:
    parts = PurePosixPath(relative).parts
    if len(parts) < 2:
        return "Uncategorised"
    return parts[0].replace("-", " ").replace("_", " ").title()


def local_container(relative: str) -> str:
    parent = PurePosixPath(relative).parent.as_posix()
    return "" if parent == "." else parent
