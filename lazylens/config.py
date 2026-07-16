from __future__ import annotations

import tomllib
from pathlib import Path

from lazylens.models import SourceConfig
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
        sources.append(
            SourceConfig(
                key=str(key),
                name=str(values.get("name", str(key).replace("-", " ").title())),
                type=source_type,
                root=expand_path(str(root_value)) if root_value else None,
                url_prefix=str(values["url_prefix"]) if "url_prefix" in values else None,
            )
        )
    return sources


def configured_db_path(config_path: str | Path | None = None) -> Path:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if not path.exists():
        return default_db_path()
    data = tomllib.loads(path.read_text())
    return expand_path(str(data.get("database", default_db_path())))

