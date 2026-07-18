from __future__ import annotations

import json
import os
from pathlib import Path

from lazylens.cli import main


def toml_string(value: Path | str) -> str:
    return json.dumps(str(value))


def test_cli_indexes_and_searches_local_source(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.md").write_text("# Notes\n\nConfluence SharePoint local context.")
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    config.write_text(
        f"""
database = {toml_string(db)}

[sources.local]
name = "Local"
type = "local"
root = {toml_string(root)}
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
    assert f"database = {toml_string(db)}" in text
    assert f"root = {toml_string(root)}" in text


def test_cli_init_confluence_writes_config_and_env_skeleton(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    env_file = tmp_path / "atlassian.env"
    db = tmp_path / "index.sqlite3"

    assert (
        main(
            [
                "--config",
                str(config),
                "init",
                "confluence",
                "--database",
                str(db),
                "--env-file",
                str(env_file),
                "--base-url",
                "https://example.atlassian.net",
                "--email",
                "you@example.com",
                "--space-key",
                "ARCH",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    config_text = config.read_text()
    env_text = env_file.read_text()
    assert "Confluence source: personal-confluence (ARCH)" in output
    assert f"database = {toml_string(db)}" in config_text
    assert '[sources."personal-confluence"]' in config_text
    assert 'name = "Personal Confluence"' in config_text
    assert 'type = "confluence"' in config_text
    assert 'base_url = "https://example.atlassian.net"' in config_text
    assert 'email = "you@example.com"' in config_text
    assert 'space_keys = ["ARCH"]' in config_text
    assert '# https://example.atlassian.net (you@example.com)' in env_text
    assert 'export CONFLUENCE_API_TOKEN=""' in env_text
    if os.name != "nt":
        assert oct(env_file.stat().st_mode & 0o777) == "0o600"


def test_cli_init_jira_writes_config_and_appends_env_skeleton(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    env_file = tmp_path / "atlassian.env"
    db = tmp_path / "index.sqlite3"
    env_file.write_text(
        "\n".join(
            [
                'export CONFLUENCE_BASE_URL="https://example.atlassian.net/wiki"',
                'export CONFLUENCE_EMAIL="you@example.com"',
                'export CONFLUENCE_API_TOKEN="secret"',
                "",
            ]
        )
    )

    assert (
        main(
            [
                "--config",
                str(config),
                "init",
                "jira",
                "--database",
                str(db),
                "--env-file",
                str(env_file),
                "--base-url",
                "https://example.atlassian.net",
                "--email",
                "you@example.com",
                "--project-key",
                "LAZY",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    config_text = config.read_text()
    env_text = env_file.read_text()
    assert "Jira source: personal-jira (LAZY)" in output
    assert f"database = {toml_string(db)}" in config_text
    assert '[sources."personal-jira"]' in config_text
    assert 'name = "Personal Jira"' in config_text
    assert 'type = "jira"' in config_text
    assert 'base_url = "https://example.atlassian.net"' in config_text
    assert 'email = "you@example.com"' in config_text
    assert 'project_keys = ["LAZY"]' in config_text
    assert 'export CONFLUENCE_API_TOKEN="secret"' in env_text
    assert 'export JIRA_API_TOKEN=""' in env_text


def test_cli_demo_creates_searchable_demo_source(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    demo_root = tmp_path / "demo-docs"

    assert main(["--config", str(config), "demo", "--root", str(demo_root), "--database", str(db)]) == 0
    assert main(["--config", str(config), "search", "SharePoint"]) == 0

    output = capsys.readouterr().out
    assert "Indexed 4 items" in output
    assert "Platform Overview | demo | Architecture" in output
    assert config.read_text().count('[sources."demo"]') == 1

    assert main(["--config", str(config), "demo", "--root", str(demo_root), "--database", str(db)]) == 0

    assert config.read_text().count('[sources."demo"]') == 1


def test_cli_demo_uses_existing_config_database(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "custom.sqlite3"
    demo_root = tmp_path / "demo-docs"
    config.write_text(f"database = {toml_string(db)}\n")

    assert main(["--config", str(config), "demo", "--root", str(demo_root)]) == 0
    assert main(["--config", str(config), "search", "gateway"]) == 0

    output = capsys.readouterr().out
    assert f"Indexed 4 items (0 unchanged, 0 removed) into {db}" in output
    assert "API Gateway Decision | demo | Architecture" in output


def test_cli_demo_adds_project_when_config_has_explicit_projects(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    demo_root = tmp_path / "demo-docs"
    config.write_text(
        f"""
database = {toml_string(db)}

[sources.work]
name = "Work"
type = "local"
root = {toml_string(tmp_path)}

[projects.work]
name = "Work"
sources = ["work"]
"""
    )

    assert main(["--config", str(config), "demo", "--root", str(demo_root)]) == 0

    text = config.read_text()
    assert '[sources."demo"]' in text
    assert "[projects.demo]" in text
    assert 'sources = ["demo"]' in text


def test_cli_init_atlassian_sources_can_use_distinct_accounts(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    env_file = tmp_path / "atlassian.env"
    db = tmp_path / "index.sqlite3"

    assert (
        main(
            [
                "--config",
                str(config),
                "init",
                "confluence",
                "--database",
                str(db),
                "--env-file",
                str(env_file),
                "--key",
                "client-a-confluence",
                "--name",
                "Client A Confluence",
                "--base-url",
                "https://client-a.atlassian.net",
                "--email",
                "a@example.com",
                "--space-key",
                "ARCH",
                "--api-token-env",
                "CLIENT_A_CONFLUENCE_TOKEN",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "init",
                "jira",
                "--env-file",
                str(env_file),
                "--key",
                "client-b-jira",
                "--name",
                "Client B Jira",
                "--base-url",
                "https://client-b.atlassian.net",
                "--email",
                "b@example.com",
                "--project-key",
                "DEL",
                "--api-token-env",
                "CLIENT_B_JIRA_TOKEN",
            ]
        )
        == 0
    )

    config_text = config.read_text()
    env_text = env_file.read_text()
    assert '[sources."client-a-confluence"]' in config_text
    assert 'base_url = "https://client-a.atlassian.net"' in config_text
    assert 'email = "a@example.com"' in config_text
    assert 'api_token_env = "CLIENT_A_CONFLUENCE_TOKEN"' in config_text
    assert '[sources."client-b-jira"]' in config_text
    assert 'base_url = "https://client-b.atlassian.net"' in config_text
    assert 'email = "b@example.com"' in config_text
    assert 'api_token_env = "CLIENT_B_JIRA_TOKEN"' in config_text
    assert 'export CLIENT_A_CONFLUENCE_TOKEN=""' in env_text
    assert 'export CLIENT_B_JIRA_TOKEN=""' in env_text


def test_cli_doctor_hints_at_confluence_env_file(tmp_path: Path, capsys, monkeypatch) -> None:
    config_home = tmp_path / "config-home"
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    config.write_text(
        f"""
database = {toml_string(db)}

[sources.personal]
name = "Personal Confluence"
type = "confluence"
space_keys = ["LAZYLENS"]
"""
    )
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(config_home))
        env_file = config_home / "lazylens" / "atlassian.env"
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
        env_file = config_home / "lazylens" / "atlassian.env"
    monkeypatch.delenv("CONFLUENCE_BASE_URL", raising=False)
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)

    assert main(["--config", str(config), "doctor"]) == 0

    output = capsys.readouterr().out
    assert f"Confluence env: {env_file} (not found)" in output
    assert "missing: CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN" in output
    assert f"source {env_file}" in output


def test_cli_index_reports_missing_confluence_env_vars(tmp_path: Path, capsys, monkeypatch) -> None:
    config = tmp_path / "config.toml"
    db = tmp_path / "index.sqlite3"
    config.write_text(
        f"""
database = {toml_string(db)}

[sources.personal]
name = "Personal Confluence"
type = "confluence"
space_keys = ["LAZYLENS"]
"""
    )
    monkeypatch.delenv("CONFLUENCE_BASE_URL", raising=False)
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)

    assert main(["--config", str(config), "index", "personal"]) == 1

    error = capsys.readouterr().err
    assert "Index failed for Personal Confluence" in error
    assert "missing base_url or CONFLUENCE_BASE_URL" in error
