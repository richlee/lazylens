from __future__ import annotations

from pathlib import Path

from lazylens.config import configured_db_path, load_sources


def test_load_sources_from_config(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
database = "{tmp_path / "index.sqlite3"}"

[sources.notes]
name = "Notes"
type = "local"
root = "{root}"
"""
    )

    sources = load_sources(config)

    assert configured_db_path(config) == tmp_path / "index.sqlite3"
    assert len(sources) == 1
    assert sources[0].key == "notes"
    assert sources[0].name == "Notes"
    assert sources[0].type == "local"
    assert sources[0].root == root

