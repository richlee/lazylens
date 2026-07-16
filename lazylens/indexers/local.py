from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from lazylens.extract import read_text_preview
from lazylens.models import IndexedItem, SourceConfig


SKIP_PARTS = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules"}


def iter_local_items(source: SourceConfig) -> list[IndexedItem]:
    if source.root is None:
        raise ValueError(f"{source.key} has no root configured")
    root = source.root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)

    items: list[IndexedItem] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        title, snippet = read_text_preview(path)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        url = local_url(source, path, relative)
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
                category=local_category(relative),
                container=local_container(relative),
                snippet=snippet,
            )
        )
    return items


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
