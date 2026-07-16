from __future__ import annotations

from collections.abc import Iterable

from lazylens.indexers.confluence import iter_confluence_items
from lazylens.indexers.local import iter_local_items
from lazylens.models import IndexedItem, SourceConfig


class IndexingError(RuntimeError):
    pass


SUPPORTED_SOURCE_TYPES = {"confluence", "local"}


def iter_source_items(source: SourceConfig) -> Iterable[IndexedItem]:
    if source.type == "local":
        return iter_local_items(source)
    if source.type == "confluence":
        return iter_confluence_items(source)
    raise IndexingError(f"{source.type} sources are not implemented yet")
