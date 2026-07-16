from __future__ import annotations

import os
from pathlib import Path


def config_home() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "lazylens"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lazylens"


def data_home() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "lazylens"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lazylens"


def cache_home() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "lazylens" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "lazylens"


def default_config_path() -> Path:
    return Path(os.environ.get("LAZYLENS_CONFIG", str(config_home() / "config.toml"))).expanduser()


def default_db_path() -> Path:
    return Path(os.environ.get("LAZYLENS_DB", str(data_home() / "index.sqlite3"))).expanduser()


def default_cache_dir() -> Path:
    return Path(os.environ.get("LAZYLENS_CACHE", str(cache_home() / "files"))).expanduser()

