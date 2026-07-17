from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, ListView

from lazylens.db import Index
from lazylens.models import IndexedItem, SourceConfig
from lazylens.tui import LazylensApp


def test_tui_loads_indexed_results(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    item = IndexedItem(
        source_key="local",
        item_key="architecture.md",
        title="Architecture Notes",
        url="file:///architecture.md",
        path="/tmp/architecture.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="Useful context about SharePoint and Confluence indexing.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([item])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.sources[0].name == "Local"
            assert app.results[0].title == "Architecture Notes"

    asyncio.run(run_app())


def test_tui_tabs_between_panes_and_skips_search(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    item = IndexedItem(
        source_key="local",
        item_key="architecture.md",
        title="Architecture Notes",
        url="file:///architecture.md",
        path="/tmp/architecture.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="Useful context about SharePoint and Confluence indexing.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([item])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)
            results = app.query_one("#results", ListView)
            search = app.query_one("#search", Input)

            assert app.focused is results
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is categories
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is results

            await pilot.press("/")
            await pilot.pause()
            assert app.focused is search
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is categories

    asyncio.run(run_app())
