from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lazylens.indexers.confluence import iter_confluence_items, iter_confluence_refresh
from lazylens.indexers.local import iter_local_items, iter_local_refresh
from lazylens.models import IndexedItem, SearchResult, SourceConfig


class IndexingError(RuntimeError):
    pass


SUPPORTED_SOURCE_TYPES = {"confluence", "local"}


@dataclass(frozen=True)
class SourceRefresh:
    items: list[IndexedItem]
    seen_item_keys: set[str]
    unchanged: int = 0


def iter_source_items(source: SourceConfig) -> Iterable[IndexedItem]:
    return iter_source_refresh(source).items


def iter_source_refresh(
    source: SourceConfig,
    *,
    existing_items: dict[str, SearchResult] | None = None,
) -> SourceRefresh:
    if source.type == "local":
        items, seen_item_keys, unchanged = iter_local_refresh(source, existing_items=existing_items)
        return SourceRefresh(items=items, seen_item_keys=seen_item_keys, unchanged=unchanged)
    if source.type == "confluence":
        items, seen_item_keys, unchanged = iter_confluence_refresh(source, existing_items=existing_items)
        return SourceRefresh(items=items, seen_item_keys=seen_item_keys, unchanged=unchanged)
    raise IndexingError(f"{source.type} sources are not implemented yet")
