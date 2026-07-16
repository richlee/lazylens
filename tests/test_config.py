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

[sources.work]
name = "Work Confluence"
type = "confluence"
base_url = "https://example.atlassian.net/wiki"
email = "rich@example.com"
api_token_env = "ATLASSIAN_API_TOKEN"
space_keys = ["ARCH"]
"""
    )

    sources = load_sources(config)

    assert configured_db_path(config) == tmp_path / "index.sqlite3"
    assert len(sources) == 2
    assert sources[0].key == "notes"
    assert sources[0].name == "Notes"
    assert sources[0].type == "local"
    assert sources[0].root == root
    assert sources[1].key == "work"
    assert sources[1].type == "confluence"
    assert sources[1].settings["space_keys"] == ["ARCH"]
