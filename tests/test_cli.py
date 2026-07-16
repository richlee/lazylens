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


def test_cli_init_writes_starter_config(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"

    assert main(["--config", str(config), "init", "--root", str(root), "--database", str(db)]) == 0

    output = capsys.readouterr().out
    text = config.read_text()
    assert "Wrote config" in output
    assert f'database = "{db}"' in text
    assert f'root = "{root}"' in text


def test_cli_demo_creates_searchable_demo_source(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    demo_root = tmp_path / "demo-docs"

    assert main(["--config", str(config), "demo", "--root", str(demo_root), "--database", str(db)]) == 0
    assert main(["--config", str(config), "search", "SharePoint"]) == 0

    output = capsys.readouterr().out
    assert "Indexed 4 demo items" in output
    assert "Platform Overview | demo | Architecture" in output
    assert config.read_text().count('[sources."demo"]') == 1

    assert main(["--config", str(config), "demo", "--root", str(demo_root), "--database", str(db)]) == 0

    assert config.read_text().count('[sources."demo"]') == 1


def test_cli_demo_uses_existing_config_database(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "custom.sqlite3"
    demo_root = tmp_path / "demo-docs"
    config.write_text(f'database = "{db}"\n')

    assert main(["--config", str(config), "demo", "--root", str(demo_root)]) == 0
    assert main(["--config", str(config), "search", "gateway"]) == 0

    output = capsys.readouterr().out
    assert f"Indexed 4 demo items into {db}" in output
    assert "API Gateway Decision | demo | Architecture" in output
