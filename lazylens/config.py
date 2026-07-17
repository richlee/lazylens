from __future__ import annotations

import tomllib
from pathlib import Path

from lazylens.models import ProjectConfig, SourceConfig, UiConfig
from lazylens.paths import default_config_path, default_db_path


class ConfigError(ValueError):
    pass


def expand_path(value: str) -> Path:
    return Path(value).expanduser()


def load_sources(config_path: str | Path | None = None) -> list[SourceConfig]:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if not path.exists():
        return []

    data = tomllib.loads(path.read_text())
    sources_data = data.get("sources", {})
    if not isinstance(sources_data, dict):
        raise ConfigError("[sources] must be a TOML table")

    sources: list[SourceConfig] = []
    for key, values in sources_data.items():
        if not isinstance(values, dict):
            continue
        source_type = str(values.get("type", "local"))
        root_value = values.get("root")
        known_keys = {"name", "type", "root", "url_prefix"}
        sources.append(
            SourceConfig(
                key=str(key),
                name=str(values.get("name", str(key).replace("-", " ").title())),
                type=source_type,
                root=expand_path(str(root_value)) if root_value else None,
                url_prefix=str(values["url_prefix"]) if "url_prefix" in values else None,
                settings={str(option): value for option, value in values.items() if option not in known_keys},
            )
        )
    return sources


def load_projects(
    config_path: str | Path | None = None,
    *,
    sources: list[SourceConfig] | None = None,
) -> list[ProjectConfig]:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    source_configs = sources if sources is not None else load_sources(config_path)
    source_keys = tuple(source.key for source in source_configs)
    if not path.exists():
        return default_projects(source_keys)

    data = tomllib.loads(path.read_text())
    projects_data = data.get("projects", {})
    if not projects_data:
        return default_projects(source_keys)
    if not isinstance(projects_data, dict):
        raise ConfigError("[projects] must be a TOML table")

    projects: list[ProjectConfig] = []
    known_source_keys = set(source_keys)
    for key, values in projects_data.items():
        if not isinstance(values, dict):
            continue
        configured_sources = values.get("sources")
        if not isinstance(configured_sources, list):
            raise ConfigError(f"[projects.{key}].sources must be a list")
        project_source_keys = tuple(
            str(source_key)
            for source_key in configured_sources
            if str(source_key) in known_source_keys
        )
        if not project_source_keys:
            continue
        projects.append(
            ProjectConfig(
                key=str(key),
                name=str(values.get("name", str(key).replace("-", " ").title())),
                source_keys=project_source_keys,
            )
        )
    return projects


def default_projects(source_keys: tuple[str, ...]) -> list[ProjectConfig]:
    if not source_keys:
        return []
    return [ProjectConfig(key="all", name="All Sources", source_keys=source_keys)]


def load_ui_config(config_path: str | Path | None = None) -> UiConfig:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if not path.exists():
        return UiConfig()

    data = tomllib.loads(path.read_text())
    ui_data = data.get("ui", {})
    if not isinstance(ui_data, dict):
        raise ConfigError("[ui] must be a TOML table")

    icon_style = str(ui_data.get("icon_style", "ascii")).lower()
    if icon_style not in {"ascii", "unicode", "nerd"}:
        raise ConfigError('[ui].icon_style must be one of "ascii", "unicode", or "nerd"')
    return UiConfig(icon_style=icon_style)


def configured_db_path(config_path: str | Path | None = None) -> Path:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if not path.exists():
        return default_db_path()
    data = tomllib.loads(path.read_text())
    return expand_path(str(data.get("database", default_db_path())))
