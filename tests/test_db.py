from __future__ import annotations

from pathlib import Path

from lazylens.db import Index
from lazylens.models import IndexedItem, SourceConfig


def test_index_searches_items_with_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    item = IndexedItem(
        source_key="local",
        item_key="architecture.md",
        title="Architecture Notes",
        url="file:///architecture.md",
        path="/tmp/architecture.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        snippet="Useful context about SharePoint and Confluence indexing.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        assert index.upsert_items([item]) == 1
        results = index.search("SharePoint")

    assert len(results) == 1
    assert results[0].title == "Architecture Notes"
    assert results[0].source_key == "local"

