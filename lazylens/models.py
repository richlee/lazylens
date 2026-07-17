from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass(frozen=True)
class SourceConfig:
    key: str
    name: str
    type: str
    root: Path | None = None
    url_prefix: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UiConfig:
    icon_style: str = "ascii"


@dataclass(frozen=True)
class SourceSummary:
    key: str
    name: str
    type: str
    count: int


@dataclass(frozen=True)
class CategorySummary:
    key: str
    name: str
    count: int
    kind: str = "folder"
    item_id: int | None = None


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
    category: str
    container: str
    snippet: str
    links: tuple[str, ...] = field(default_factory=tuple)
    parent_key: str = ""
    structure_type: str = "page"


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
    category: str
    container: str
    snippet: str
    rank: float
    parent_key: str = ""
    structure_type: str = "page"


@dataclass(frozen=True)
class RelatedItem:
    item_id: int | None
    direction: str
    title: str
    url: str
