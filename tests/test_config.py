from __future__ import annotations

import json
from pathlib import Path

import pytest

from lazylens.config import ConfigError, configured_db_path, load_projects, load_sources, load_ui_config


def toml_string(value: Path | str) -> str:
    return json.dumps(str(value))


def test_load_sources_from_config(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
database = {toml_string(tmp_path / "index.sqlite3")}

[sources.notes]
name = "Notes"
type = "local"
root = {toml_string(root)}

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


def test_load_projects_from_config_with_different_source_keys(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
[sources."dsp-beta"]
name = "DSP Beta Confluence"
type = "confluence"
space_keys = ["dsp-beta"]

[sources."DSPBeta"]
name = "DSP Beta Jira"
type = "jira"
project_keys = ["DSPBeta"]

[sources.notes]
name = "Notes"
type = "local"
root = {toml_string(root)}

[projects.dsp]
name = "DSP"
sources = ["dsp-beta", "DSPBeta"]
"""
    )

    sources = load_sources(config)
    projects = load_projects(config, sources=sources)

    assert len(projects) == 1
    assert projects[0].key == "dsp"
    assert projects[0].name == "DSP"
    assert projects[0].source_keys == ("dsp-beta", "DSPBeta")


def test_load_projects_defaults_to_all_sources(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[sources.a]
name = "A"
type = "local"

[sources.b]
name = "B"
type = "jira"
"""
    )

    projects = load_projects(config)

    assert len(projects) == 1
    assert projects[0].name == "All Sources"
    assert projects[0].source_keys == ("a", "b")


def test_load_projects_rejects_non_list_sources(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[sources.a]
name = "A"
type = "local"

[projects.bad]
sources = "a"
"""
    )

    with pytest.raises(ConfigError, match="sources"):
        load_projects(config)


def test_load_ui_config_defaults_to_ascii(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("")

    ui_config = load_ui_config(config)

    assert ui_config.icon_style == "ascii"


def test_load_ui_config_accepts_nerd_icons(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[ui]
icon_style = "nerd"
"""
    )

    ui_config = load_ui_config(config)

    assert ui_config.icon_style == "nerd"


def test_load_ui_config_rejects_unknown_icon_style(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[ui]
icon_style = "emoji"
"""
    )

    with pytest.raises(ConfigError, match="icon_style"):
        load_ui_config(config)
