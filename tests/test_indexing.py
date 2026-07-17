from __future__ import annotations

from pathlib import Path
from typing import Any

from lazylens.db import Index
from lazylens.indexing import refresh_source
from lazylens.models import IndexedItem, SourceConfig


def test_refresh_source_indexes_only_changed_local_files_and_removes_missing(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    keep = root / "keep.md"
    remove = root / "remove.md"
    keep.write_text("# Keep\n\nOriginal searchable context.")
    remove.write_text("# Remove\n\nTemporary context.")
    source = SourceConfig(key="local", name="Local", type="local", root=root)

    with Index(tmp_path / "index.sqlite3") as index:
        first = refresh_source(index, source)
        second = refresh_source(index, source)

        assert first.changed == 2
        assert first.unchanged == 0
        assert first.removed == 0
        assert second.changed == 0
        assert second.unchanged == 2
        assert second.removed == 0

        remove.unlink()
        added = root / "added.md"
        added.write_text("# Added\n\nFresh Confluence notes.")
        keep.write_text("# Keep\n\nUpdated SharePoint context.")

        third = refresh_source(index, source)
        titles = [item.title for item in index.search("", limit=10, source_key="local")]

    assert third.changed == 2
    assert third.unchanged == 0
    assert third.removed == 1
    assert sorted(titles) == ["Added", "Keep"]


def test_refresh_source_skips_pruning_when_confluence_scan_is_capped(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    existing = IndexedItem(
        source_key="work",
        item_key="old-page",
        title="Old Page",
        url="https://example.atlassian.net/wiki/spaces/ARCH/pages/old-page",
        path="ARCH/Old Page",
        content_type="text/html",
        modified_at="2026-07-16T12:00:00.000Z",
        owner="",
        category="ARCH",
        container="Architecture",
        snippet="Old context that was indexed earlier.",
    )
    source = SourceConfig(key="work", name="Work", type="confluence")

    def incomplete_refresh(_source: SourceConfig, *, existing_items: dict | None = None) -> Any:
        assert existing_items and "old-page" in existing_items
        from lazylens.indexers.adapters import SourceRefresh

        return SourceRefresh(items=[], seen_item_keys=set(), unchanged=0, complete=False)

    monkeypatch.setattr("lazylens.indexing.iter_source_refresh", incomplete_refresh)

    with Index(tmp_path / "index.sqlite3") as index:
        index.upsert_source(source)
        index.upsert_items([existing])
        report = refresh_source(index, source)
        results = index.search("Old", source_key="work")

    assert report.removed == 0
    assert report.pruned is False
    assert results[0].title == "Old Page"
