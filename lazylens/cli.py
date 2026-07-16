from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lazylens.config import configured_db_path, load_sources
from lazylens.db import Index
from lazylens.indexers.local import iter_local_items
from lazylens.models import SourceConfig
from lazylens.paths import data_home, default_config_path, default_db_path


DEMO_FILES = {
    "architecture/platform-overview.md": """# Platform Overview

The customer portal uses SharePoint for formal documents and Confluence for working notes.
The first lazylens phase keeps a local SQLite index with titles, source metadata, and short preview text.
""",
    "architecture/api-decision.md": """# API Gateway Decision

Use a managed API gateway for the first release. Revisit service mesh options when traffic patterns and team ownership are clearer.
""",
    "delivery/release-plan.md": """# Release Plan

The first milestone is a searchable local work index. The second milestone adds Confluence and SharePoint connectors.
""",
    "runbooks/search-refresh.md": """# Search Refresh Runbook

Run lazylens index after changing configured local folders. Later versions should support scheduled refreshes for remote sources.
""",
}


def index_source(index: Index, source: SourceConfig) -> int:
    if source.type != "local":
        raise NotImplementedError(f"{source.type} sources are not implemented yet")
    index.upsert_source(source)
    return index.upsert_items(iter_local_items(source))


def render_config(*, database: Path, key: str, name: str, root: Path) -> str:
    return f"""database = {json.dumps(str(database))}

[sources.{json.dumps(key)}]
name = {json.dumps(name)}
type = "local"
root = {json.dumps(str(root))}
"""


def write_starter_config(path: Path, *, source: SourceConfig, database: Path, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if source.root is None:
        raise ValueError("local source root is required")
    path.write_text(
        render_config(database=database, key=source.key, name=source.name, root=source.root.expanduser()),
        encoding="utf-8",
    )


def append_demo_source(path: Path, *, source: SourceConfig, database: Path, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or force:
        write_starter_config(path, source=source, database=database, force=True)
        return
    text = path.read_text(encoding="utf-8")
    if "[sources.demo]" in text or '[sources."demo"]' in text:
        return
    if source.root is None:
        raise ValueError("demo source root is required")
    addition = f"""

[sources.{json.dumps(source.key)}]
name = {json.dumps(source.name)}
type = "local"
root = {json.dumps(str(source.root.expanduser()))}
"""
    path.write_text(text.rstrip() + addition, encoding="utf-8")


def create_demo_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in DEMO_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def command_index(args: argparse.Namespace) -> int:
    sources = load_sources(args.config)
    if not sources:
        print(f"No sources configured. Create {default_config_path()}.", file=sys.stderr)
        return 1
    db_path = configured_db_path(args.config) if args.db is None else Path(args.db).expanduser()
    selected = [source for source in sources if args.source in (None, source.key)]
    if not selected:
        print(f"Unknown source: {args.source}", file=sys.stderr)
        return 1
    with Index(db_path) as index:
        for source in selected:
            count = index_source(index, source)
            print(f"Indexed {count} items from {source.name} into {index.path}")
    return 0


def command_init(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    database = Path(args.database).expanduser() if args.database else default_db_path()
    root = Path(args.root).expanduser() if args.root else Path.cwd()
    source = SourceConfig(
        key=args.key,
        name=args.name,
        type="local",
        root=root,
    )
    try:
        write_starter_config(config_path, source=source, database=database, force=args.force)
    except FileExistsError:
        print(f"Config already exists: {config_path}", file=sys.stderr)
        print("Use --force to replace it, or edit it manually.", file=sys.stderr)
        return 1
    print(f"Wrote config: {config_path}")
    print(f"Local source: {root}")
    print("Run: lazylens index")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    database = Path(args.database).expanduser() if args.database else configured_db_path(config_path)
    demo_root = Path(args.root).expanduser() if args.root else data_home() / "demo-docs"
    create_demo_files(demo_root)
    source = SourceConfig(key="demo", name="Demo Project", type="local", root=demo_root)
    append_demo_source(config_path, source=source, database=database, force=args.force_config)
    with Index(database) as index:
        index.upsert_source(source)
        count = index.upsert_items(iter_local_items(source))
    print(f"Demo documents: {demo_root}")
    print(f"Config: {config_path}")
    print(f"Indexed {count} demo items into {database}")
    print("Run: lazylens")
    return 0


def command_search(args: argparse.Namespace) -> int:
    db_path = configured_db_path(args.config) if args.db is None else Path(args.db).expanduser()
    with Index(db_path) as index:
        results = index.search(args.query, limit=args.limit)
    for result in results:
        meta = " | ".join(part for part in [result.source_key, result.category, result.modified_at] if part)
        print(f"{result.title} | {meta} | {result.url}")
        if result.snippet:
            print(f"  {result.snippet}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    db_path = configured_db_path(config_path) if config_path.exists() else default_db_path()
    print(f"Config: {config_path}")
    print(f"Database: {db_path}")
    sources = load_sources(config_path)
    print(f"Sources: {len(sources)} configured")
    for source in sources:
        root = source.root if source.root else "(none)"
        status = "OK" if source.root and source.root.exists() else "missing"
        print(f"  {source.key}: {source.type} | {root} | {status}")
    if db_path.exists():
        with Index(db_path) as index:
            print(f"Items: {index.item_count()}")
    return 0


def command_tui(args: argparse.Namespace) -> int:
    from lazylens.tui import run_tui

    db_path = configured_db_path(args.config) if args.db is None else Path(args.db).expanduser()
    return run_tui(config_path=args.config, db_path=db_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A fast TUI lens over work knowledge.")
    parser.add_argument("--config", help="Path to config.toml. Defaults to LAZYLENS_CONFIG or the platform config path.")
    parser.add_argument("--db", help="Path to index.sqlite3. Defaults to config database or the platform data path.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create a starter local-source config.")
    init_parser.add_argument("--root", help="Local folder to index. Defaults to the current directory.")
    init_parser.add_argument("--key", default="local", help="Source key. Defaults to local.")
    init_parser.add_argument("--name", default="Local", help="Source display name. Defaults to Local.")
    init_parser.add_argument("--database", help="Database path. Defaults to the platform data path.")
    init_parser.add_argument("--force", action="store_true", help="Replace an existing config.")
    init_parser.set_defaults(func=command_init)

    demo_parser = subparsers.add_parser("demo", help="Create and index a small local demo source.")
    demo_parser.add_argument("--root", help="Demo document folder. Defaults to the platform data path.")
    demo_parser.add_argument("--database", help="Database path. Defaults to the platform data path.")
    demo_parser.add_argument("--force-config", action="store_true", help="Replace the config with the demo config.")
    demo_parser.set_defaults(func=command_demo)

    index_parser = subparsers.add_parser("index", help="Index configured sources.")
    index_parser.add_argument("source", nargs="?", help="Optional source key to index.")
    index_parser.set_defaults(func=command_index)

    search_parser = subparsers.add_parser("search", help="Search the local index.")
    search_parser.add_argument("query", help="FTS query to search for.")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.set_defaults(func=command_search)

    doctor_parser = subparsers.add_parser("doctor", help="Check config and local index state.")
    doctor_parser.set_defaults(func=command_doctor)

    tui_parser = subparsers.add_parser("tui", help="Open the terminal UI.")
    tui_parser.set_defaults(func=command_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        return command_tui(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
