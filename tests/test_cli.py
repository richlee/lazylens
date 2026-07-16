from __future__ import annotations

from pathlib import Path

from lazylens.cli import main


def test_cli_indexes_and_searches_local_source(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.md").write_text("# Notes\n\nConfluence SharePoint local context.")
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    config.write_text(
        f"""
database = "{db}"

[sources.local]
name = "Local"
type = "local"
root = "{root}"
"""
    )

    assert main(["--config", str(config), "index"]) == 0
    assert main(["--config", str(config), "search", "Confluence"]) == 0

    output = capsys.readouterr().out
    assert "Indexed 1 items" in output
    assert "Notes | local" in output

