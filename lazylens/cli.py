from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from lazylens.config import configured_db_path, load_sources
from lazylens.db import Index
from lazylens.indexers.adapters import IndexingError
from lazylens.indexing import IndexReport, refresh_source
from lazylens.models import SourceConfig
from lazylens.paths import data_home, default_config_path, default_confluence_env_path, default_db_path


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


def render_index_report(report: IndexReport) -> str:
    prune_status = f"{report.removed} removed" if report.pruned else "prune skipped"
    return f"{report.changed} items ({report.unchanged} unchanged, {prune_status})"


def render_config(*, database: Path, key: str, name: str, root: Path) -> str:
    return f"""database = {json.dumps(str(database))}

[sources.{json.dumps(key)}]
name = {json.dumps(name)}
type = "local"
root = {json.dumps(str(root))}
"""


def render_confluence_source_config(
    *,
    key: str,
    name: str,
    space_keys: list[str],
    page_limit: int,
    max_pages: int,
    api_token_env: str,
) -> str:
    lines = [
        f"[sources.{json.dumps(key)}]",
        f"name = {json.dumps(name)}",
        'type = "confluence"',
        f"space_keys = {json.dumps(space_keys)}",
        f"page_limit = {page_limit}",
        f"max_pages = {max_pages}",
    ]
    if api_token_env != "CONFLUENCE_API_TOKEN":
        lines.append(f"api_token_env = {json.dumps(api_token_env)}")
    return "\n".join(lines) + "\n"


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


def config_contains_source(text: str, key: str) -> bool:
    return f"[sources.{key}]" in text or f"[sources.{json.dumps(key)}]" in text


def append_confluence_source(
    path: Path,
    *,
    database: Path,
    key: str,
    name: str,
    space_keys: list[str],
    page_limit: int,
    max_pages: int,
    api_token_env: str,
    force: bool = False,
) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_text = render_confluence_source_config(
        key=key,
        name=name,
        space_keys=space_keys,
        page_limit=page_limit,
        max_pages=max_pages,
        api_token_env=api_token_env,
    )
    if not path.exists() or force:
        path.write_text(f"database = {json.dumps(str(database))}\n\n{source_text}", encoding="utf-8")
        return True
    text = path.read_text(encoding="utf-8")
    if config_contains_source(text, key):
        return False
    path.write_text(text.rstrip() + "\n\n" + source_text, encoding="utf-8")
    return True


def write_confluence_env_skeleton(
    path: Path,
    *,
    base_url: str,
    email: str,
    api_token_env: str,
    force: bool = False,
) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# lazylens Confluence Cloud API settings.",
                "# Keep this file out of source control.",
                f"export CONFLUENCE_BASE_URL={json.dumps(base_url)}",
                f"export CONFLUENCE_EMAIL={json.dumps(email)}",
                f"export {api_token_env}=\"\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return True


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
        failed = False
        for source in selected:
            try:
                report = refresh_source(index, source)
            except (IndexingError, RuntimeError, OSError) as exc:
                failed = True
                print(f"Index failed for {source.name}: {exc}", file=sys.stderr)
                continue
            print(f"Indexed {render_index_report(report)} from {source.name} into {index.path}")
    return 1 if failed else 0


def command_init(args: argparse.Namespace) -> int:
    if args.kind == "confluence":
        return command_init_confluence(args)

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


def command_init_confluence(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    database = Path(args.database).expanduser() if args.database else default_db_path()
    env_path = Path(args.env_file).expanduser() if args.env_file else default_confluence_env_path()
    key = "personal-confluence" if args.key == "local" else args.key
    name = "Personal Confluence" if args.name == "Local" else args.name
    space_keys = args.space_key or ["LAZYLENS"]
    wrote_config = append_confluence_source(
        config_path,
        database=database,
        key=key,
        name=name,
        space_keys=space_keys,
        page_limit=args.page_limit,
        max_pages=args.max_pages,
        api_token_env=args.api_token_env,
        force=args.force,
    )
    wrote_env = write_confluence_env_skeleton(
        env_path,
        base_url=args.base_url or "https://example.atlassian.net",
        email=args.email or "you@example.com",
        api_token_env=args.api_token_env,
        force=args.force_env,
    )

    print(f"{'Wrote' if wrote_config else 'Config already contains source'}: {config_path}")
    print(f"{'Wrote' if wrote_env else 'Env file already exists'}: {env_path}")
    print(f"Confluence source: {key} ({', '.join(space_keys)})")
    print(f"Edit secrets, then run: source {env_path}")
    print(f"Then run: lazylens doctor && lazylens index {key}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    database = Path(args.database).expanduser() if args.database else configured_db_path(config_path)
    demo_root = Path(args.root).expanduser() if args.root else data_home() / "demo-docs"
    create_demo_files(demo_root)
    source = SourceConfig(key="demo", name="Demo Project", type="local", root=demo_root)
    append_demo_source(config_path, source=source, database=database, force=args.force_config)
    with Index(database) as index:
        report = refresh_source(index, source)
    print(f"Demo documents: {demo_root}")
    print(f"Config: {config_path}")
    print(f"Indexed {render_index_report(report)} into {database}")
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
    confluence_env_path = default_confluence_env_path()
    print(f"Config: {config_path}")
    print(f"Database: {db_path}")
    print(
        "Confluence env: "
        f"{confluence_env_path} ({'exists' if confluence_env_path.exists() else 'not found'})"
    )
    sources = load_sources(config_path)
    print(f"Sources: {len(sources)} configured")
    for source in sources:
        root = source.root if source.root else "(none)"
        if source.type == "local":
            status = "OK" if source.root and source.root.exists() else "missing"
        elif source.type == "confluence":
            token_env = str(source.settings.get("api_token_env", "CONFLUENCE_API_TOKEN"))
            base_url = source.settings.get("base_url") or os.environ.get("CONFLUENCE_BASE_URL")
            email = source.settings.get("email") or os.environ.get("CONFLUENCE_EMAIL")
            missing = []
            if not base_url:
                missing.append("CONFLUENCE_BASE_URL")
            if not email:
                missing.append("CONFLUENCE_EMAIL")
            if not os.environ.get(token_env):
                missing.append(token_env)
            status = "OK" if not missing else f"missing: {', '.join(missing)}"
            if missing:
                status = f"{status}; for zsh/bash run: source {confluence_env_path}"
        else:
            status = "unsupported"
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

    init_parser = subparsers.add_parser("init", help="Create a starter config.")
    init_parser.add_argument("kind", nargs="?", choices=["local", "confluence"], default="local")
    init_parser.add_argument("--root", help="Local folder to index. Defaults to the current directory.")
    init_parser.add_argument("--key", default="local", help="Source key. Defaults to local.")
    init_parser.add_argument("--name", default="Local", help="Source display name. Defaults to Local.")
    init_parser.add_argument("--database", help="Database path. Defaults to the platform data path.")
    init_parser.add_argument("--force", action="store_true", help="Replace an existing config.")
    init_parser.add_argument("--space-key", action="append", help="Confluence space key to index. May be repeated.")
    init_parser.add_argument("--base-url", help="Confluence site URL for generated env file.")
    init_parser.add_argument("--email", help="Confluence account email for generated env file.")
    init_parser.add_argument("--api-token-env", default="CONFLUENCE_API_TOKEN", help="API token environment variable.")
    init_parser.add_argument("--env-file", help="Path for generated Confluence env skeleton.")
    init_parser.add_argument("--force-env", action="store_true", help="Replace an existing Confluence env file.")
    init_parser.add_argument("--page-limit", type=int, default=100)
    init_parser.add_argument("--max-pages", type=int, default=5)
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
