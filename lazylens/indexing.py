from __future__ import annotations

from dataclasses import dataclass

from lazylens.db import Index
from lazylens.indexers.adapters import iter_source_refresh
from lazylens.models import SourceConfig


@dataclass(frozen=True)
class IndexReport:
    changed: int
    unchanged: int
    removed: int
    pruned: bool = True

    @property
    def total_seen(self) -> int:
        return self.changed + self.unchanged


def refresh_source(index: Index, source: SourceConfig) -> IndexReport:
    index.upsert_source(source)
    existing_items = index.items_by_source(source.key)
    refresh = iter_source_refresh(source, existing_items=existing_items)
    changed = index.upsert_items(refresh.items)
    removed = index.delete_source_items_not_seen(source.key, refresh.seen_item_keys) if refresh.complete else 0
    return IndexReport(changed=changed, unchanged=refresh.unchanged, removed=removed, pruned=refresh.complete)
