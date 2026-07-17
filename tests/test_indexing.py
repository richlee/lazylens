from __future__ import annotations

from pathlib import Path

from lazylens.db import Index
from lazylens.indexing import refresh_source
from lazylens.models import SourceConfig


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
