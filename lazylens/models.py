from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceConfig:
    key: str
    name: str
    type: str
    root: Path | None = None
    url_prefix: str | None = None


@dataclass(frozen=True)
class IndexedItem:
    source_key: str
    item_key: str
    title: str
    url: str
    path: str
    content_type: str
    modified_at: str
    owner: str
    snippet: str


@dataclass(frozen=True)
class SearchResult:
    id: int
    source_key: str
    title: str
    url: str
    path: str
    content_type: str
    modified_at: str
    owner: str
    snippet: str
    rank: float

