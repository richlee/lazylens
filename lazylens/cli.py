from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lazylens.config import configured_db_path, load_sources
from lazylens.db import Index
from lazylens.indexers.local import iter_local_items
from lazylens.models import SourceConfig
from lazylens.paths import default_config_path, default_db_path


def index_source(index: Index, source: SourceConfig) -> int:
    if source.type != "local":
        raise NotImplementedError(f"{source.type} sources are not implemented yet")
    index.upsert_source(source)
    return index.upsert_items(iter_local_items(source))


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


def command_search(args: argparse.Namespace) -> int:
    db_path = configured_db_path(args.config) if args.db is None else Path(args.db).expanduser()
    with Index(db_path) as index:
        results = index.search(args.query, limit=args.limit)
    for result in results:
        print(f"{result.title} | {result.source_key} | {result.url}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A fast TUI lens over work knowledge.")
    parser.add_argument("--config", help="Path to config.toml. Defaults to LAZYLENS_CONFIG or the platform config path.")
    parser.add_argument("--db", help="Path to index.sqlite3. Defaults to config database or the platform data path.")
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser("index", help="Index configured sources.")
    index_parser.add_argument("source", nargs="?", help="Optional source key to index.")
    index_parser.set_defaults(func=command_index)

    search_parser = subparsers.add_parser("search", help="Search the local index.")
    search_parser.add_argument("query", help="FTS query to search for.")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.set_defaults(func=command_search)

    doctor_parser = subparsers.add_parser("doctor", help="Check config and local index state.")
    doctor_parser.set_defaults(func=command_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

