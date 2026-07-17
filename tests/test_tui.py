from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, ListView

import lazylens.tui as tui
from lazylens.db import Index
from lazylens.models import IndexedItem, SearchResult, SourceConfig
from lazylens.tui import LazylensApp, preview_text


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


def test_preview_text_formats_metadata_and_highlights_query() -> None:
    result = SearchResult(
        id=1,
        source_key="local",
        title="Architecture Notes",
        url="file:///architecture.md",
        path="/tmp/architecture.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:34:56+00:00",
        owner="rich",
        category="Architecture",
        container="architecture",
        snippet="Useful context about SharePoint and Confluence indexing.",
        rank=0.0,
    )

    text = preview_text(result, "share")

    assert text.plain == (
        "Architecture Notes\n"
        "Modified: 2026-07-16 12:34\n"
        "URL: file:///architecture.md\n"
        "\n"
        "Useful context about SharePoint and Confluence indexing."
    )
    assert "local |" not in text.plain
    assert "Owner:" not in text.plain
    assert any(text.plain[span.start : span.end] == "Share" for span in text.spans)


def test_tui_enter_opens_selected_result(tmp_path: Path, monkeypatch) -> None:
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
    opened: list[str] = []

    def fake_open_url(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(tui, "open_url", fake_open_url)

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([item])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(run_app())

    assert opened == ["file:///architecture.md"]


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
