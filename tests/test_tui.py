from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, ListView

import lazylens.tui as tui
from lazylens.db import Index
from lazylens.models import IndexedItem, SearchResult, SourceConfig
from lazylens.tui import LazylensApp, icon_set, preview_text


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


def test_icon_sets_keep_ascii_default_and_support_nerd_font() -> None:
    ascii_icons = icon_set("ascii")
    nerd_icons = icon_set("nerd")

    assert ascii_icons.structure("parent-page") == "[P+]"
    assert ascii_icons.page == ""
    assert ascii_icons.source_for("confluence") == ""
    assert nerd_icons.structure("parent-page") == "\uf07c"
    assert nerd_icons.source_for("confluence") == "\uf0ac"


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


def test_tui_enter_in_search_applies_query_without_opening(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    architecture = IndexedItem(
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
    release = IndexedItem(
        source_key="local",
        item_key="release.md",
        title="Release Plan",
        url="file:///release.md",
        path="/tmp/release.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Delivery",
        container="delivery",
        snippet="Milestones and release readiness.",
    )
    opened: list[str] = []
    monkeypatch.setattr(tui, "open_url", opened.append)

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([architecture, release])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            results = app.query_one("#results", ListView)
            search = app.query_one("#search", Input)

            assert app.focused is results
            await pilot.press("/")
            await pilot.pause()
            assert app.focused is search
            await pilot.press("r", "e", "l")
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is results
            assert [result.title for result in app.results] == ["Release Plan"]

    asyncio.run(run_app())

    assert opened == []


def test_tui_structure_selection_filters_only_on_enter(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    architecture = IndexedItem(
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
        snippet="Useful architecture context.",
    )
    delivery = IndexedItem(
        source_key="local",
        item_key="delivery.md",
        title="Delivery Plan",
        url="file:///delivery.md",
        path="/tmp/delivery.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="Delivery",
        container="delivery",
        snippet="Delivery milestones.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([architecture, delivery])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)
            results = app.query_one("#results", ListView)

            assert [result.title for result in app.results] == ["Delivery Plan", "Architecture Notes"]
            categories.focus()
            categories.index = 1
            await pilot.pause()
            assert app.pending_category_key == "Architecture"
            assert [result.title for result in app.results] == ["Delivery Plan", "Architecture Notes"]

            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is results
            assert [result.title for result in app.results] == ["Architecture Notes"]

    asyncio.run(run_app())


def test_tui_structure_enter_promotes_top_level_page(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    product = IndexedItem(
        source_key="local",
        item_key="product.md",
        title="Product Overview",
        url="file:///product.md",
        path="/tmp/product.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="Product context.",
    )
    child = IndexedItem(
        source_key="local",
        item_key="hld.md",
        title="HLD",
        url="file:///hld.md",
        path="/tmp/hld.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="High level design.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([product, child])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)
            results = app.query_one("#results", ListView)

            assert len(app.results) == 2
            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()

            assert app.focused is results
            assert [result.title for result in app.results] == ["Product Overview"]

    asyncio.run(run_app())


def test_tui_follows_relationships_into_center_context(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    target = IndexedItem(
        source_key="local",
        item_key="hld.md",
        title="HLD",
        url="file:///hld.md",
        path="/tmp/hld.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="High level design.",
    )
    product = IndexedItem(
        source_key="local",
        item_key="product.md",
        title="Product Overview",
        url="file:///product.md",
        path="/tmp/product.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="Product",
        container="product",
        snippet="Product context.",
        links=("file:///hld.md",),
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([target, product])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            outgoing = app.query_one("#outgoing", ListView)
            incoming = app.query_one("#incoming", ListView)
            results = app.query_one("#results", ListView)

            assert app.results[0].title == "Product Overview"
            assert outgoing.highlighted_child is not None
            outgoing.focus()
            await pilot.press("right")
            await pilot.pause()

            assert app.focused is results
            assert app.results[0].title == "HLD"
            assert incoming.highlighted_child is not None

            await pilot.press("left")
            await pilot.pause()
            highlighted = results.highlighted_child
            assert app.results[0].title == "Product Overview"
            assert len(app.results) == 2
            assert highlighted is not None
            assert getattr(highlighted, "result").title == "Product Overview"

    asyncio.run(run_app())
