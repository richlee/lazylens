from __future__ import annotations

from pathlib import Path

from lazylens.indexers.local import iter_local_items
from lazylens.models import SourceConfig


def test_iter_local_items_indexes_text_documents(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "decision.md").write_text("# Decision Record\n\nUse boring storage first.")
    (root / "diagram.pdf").write_bytes(b"%PDF-1.7")

    items = iter_local_items(SourceConfig(key="local", name="Local", type="local", root=root))

    assert [item.item_key for item in items] == ["decision.md", "diagram.pdf"]
    assert items[0].title == "Decision Record"
    assert items[0].snippet == "Use boring storage first."
    assert items[0].url.startswith("file:")
    assert items[1].title == "diagram"
    assert items[1].snippet == ""

