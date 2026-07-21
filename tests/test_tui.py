from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, ListView, Static

import lazylens.tui as tui
from lazylens.db import Index
from lazylens.models import CategorySummary, IndexedItem, RelatedItem, SearchResult, SourceConfig
from lazylens.tui import (
    LazylensApp,
    MessageModal,
    app_version,
    category_label,
    icon_set,
    item_type_icon,
    preview_text,
    relation_label,
)


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


def test_tui_command_bar_is_concise_and_shows_version(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            commands = app.query_one("#commands", Static).render().plain
            version = app.query_one("#version", Static).render().plain

            assert commands.startswith("Commands:")
            assert "Project: 1-9" not in commands
            assert "Structure Source" not in commands
            assert "About: ?" in commands
            assert version == f"v{app_version()}"

    asyncio.run(run_app())


def test_tui_about_key_opens_about_modal(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()

            assert isinstance(app.screen, MessageModal)
            assert app.screen.title == "lazylens"
            assert any(line.startswith("Version:") for line in app.screen.lines)

    asyncio.run(run_app())


def test_preview_text_formats_metadata_and_highlights_query() -> None:
    result = SearchResult(
        id=1,
        source_key="local",
        item_key="architecture.md",
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
    assert ascii_icons.structure("unparented") == ""
    assert ascii_icons.project == ""
    assert ascii_icons.page == ""
    assert ascii_icons.source_for("confluence") == "[C]"
    assert ascii_icons.source_for("jira") == "[Ji]"
    assert nerd_icons.project == ""
    assert nerd_icons.structure("parent-page") == "\uf07c"
    assert nerd_icons.source_for("confluence") == "\uf0ac"
    assert nerd_icons.source_for("jira") == "\uf0ae"


def test_category_label_prefixes_structure_rows_with_source_icons() -> None:
    confluence = CategorySummary(
        key="Architecture",
        name="Architecture",
        count=3,
        source_key="conf",
        kind="folder",
    )
    unparented = CategorySummary(
        key="jira:unparented",
        name="Unparented",
        count=2,
        source_key="jira",
        kind="unparented",
    )
    jira_root = CategorySummary(
        key="jira:jira-root",
        name="LAZY",
        count=8,
        source_key="jira",
        kind="jira-project",
    )

    assert category_label(None, icon_set("ascii"), "confluence") == "[C] All"
    assert category_label(confluence, icon_set("ascii"), "confluence") == "[C] [F] Architecture (3)"
    assert category_label(jira_root, icon_set("ascii"), "jira") == "[Ji] LAZY (8)"
    assert category_label(unparented, icon_set("ascii"), "jira") == "[Ji] Unparented (2)"


def test_relation_label_keeps_clear_space_after_link_icons() -> None:
    internal = RelatedItem(
        item_id=1,
        direction="Links to",
        title="HLD - Architecture",
        url="https://example.test/hld",
    )
    external = RelatedItem(
        item_id=None,
        direction="Links to",
        title="https://example.test/external",
        url="https://example.test/external",
    )

    assert relation_label(internal, icon_set("nerd")) == "\uf0c1  HLD - Architecture"
    assert relation_label(external, icon_set("ascii")) == "[ext]  https://example.test/external (external)"


def test_jira_bug_uses_bug_icon_in_nerd_font() -> None:
    bug = SearchResult(
        id=1,
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Bug",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T10:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Bug | To Do | Fix broken icon.",
        rank=0.0,
    )

    assert item_type_icon(bug, icon_set("ascii")) == "[B]"
    assert item_type_icon(bug, icon_set("nerd")) == "\uf188"


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
        parent_key="product.md",
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
            assert [result.title for result in app.results] == ["HLD"]

    asyncio.run(run_app())


def test_tui_enter_drills_into_folder_result_and_back_restores_parent(tmp_path: Path) -> None:
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
    folder = IndexedItem(
        source_key="local",
        item_key="folder-1",
        title="Design Notes",
        url="file:///folder-1",
        path="/tmp/folder-1",
        content_type="application/vnd.lazylens.folder",
        modified_at="2026-07-16T13:01:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="",
        parent_key="product.md",
        structure_type="folder",
    )
    child = IndexedItem(
        source_key="local",
        item_key="decision.md",
        title="Decision Note",
        url="file:///decision.md",
        path="/tmp/decision.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:02:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="Decision context.",
        parent_key="folder-1",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([product, folder, child])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)
            results = app.query_one("#results", ListView)

            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()
            assert [result.title for result in app.results] == ["Design Notes"]

            await pilot.press("enter")
            await pilot.pause()
            assert [result.title for result in app.results] == ["Decision Note"]

            await pilot.press("left")
            await pilot.pause()
            assert [result.title for result in app.results] == ["Design Notes"]
            assert app.focused is results

    asyncio.run(run_app())


def test_tui_structure_enter_on_folder_root_shows_folder_and_page_children(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="conf", name="Confluence", type="confluence")
    root_folder = IndexedItem(
        source_key="conf",
        item_key="folder-1",
        title="Architecture Folder",
        url="https://example.atlassian.net/wiki/folder-1",
        path="ARCH/Architecture Folder",
        content_type="application/vnd.atlassian.confluence.folder",
        modified_at="2026-07-21T09:00:00+00:00",
        owner="",
        category="Architecture Folder",
        container="Architecture",
        snippet="",
        structure_type="folder",
    )
    child_folder = IndexedItem(
        source_key="conf",
        item_key="folder-2",
        title="Decisions",
        url="https://example.atlassian.net/wiki/folder-2",
        path="ARCH/Decisions",
        content_type="application/vnd.atlassian.confluence.folder",
        modified_at="2026-07-21T10:00:00+00:00",
        owner="",
        category="Architecture Folder",
        container="Architecture",
        snippet="",
        parent_key="folder-1",
        structure_type="folder",
    )
    child_page = IndexedItem(
        source_key="conf",
        item_key="page-1",
        title="Decision Record",
        url="https://example.atlassian.net/wiki/page-1",
        path="ARCH/Decision Record",
        content_type="text/html",
        modified_at="2026-07-21T11:00:00+00:00",
        owner="",
        category="Architecture Folder",
        container="Architecture",
        snippet="Decision context.",
        parent_key="folder-1",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([root_folder, child_folder, child_page])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)

            assert [getattr(item, "kind", "") for item in categories.children] == ["space", "folder"]
            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()

            assert [result.title for result in app.results] == ["Decisions", "Decision Record"]

    asyncio.run(run_app())


def test_tui_right_drills_into_page_children_when_no_links_exist(tmp_path: Path, monkeypatch) -> None:
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
    research = IndexedItem(
        source_key="local",
        item_key="research.md",
        title="Research Sandbox",
        url="file:///research.md",
        path="/tmp/research.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:01:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="Research context.",
        parent_key="product.md",
    )
    folder = IndexedItem(
        source_key="local",
        item_key="field-notes",
        title="Field Notes",
        url="file:///field-notes",
        path="/tmp/field-notes",
        content_type="application/vnd.lazylens.folder",
        modified_at="2026-07-16T13:02:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="",
        parent_key="research.md",
        structure_type="folder",
    )
    note = IndexedItem(
        source_key="local",
        item_key="note.md",
        title="SharePoint Field Note",
        url="file:///note.md",
        path="/tmp/note.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:03:00+00:00",
        owner="",
        category="Product Overview",
        container="product",
        snippet="SharePoint context.",
        parent_key="field-notes",
    )
    opened: list[str] = []
    monkeypatch.setattr(tui, "open_url", opened.append)

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([product, research, folder, note])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)

            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()
            assert [result.title for result in app.results] == ["Research Sandbox"]

            await pilot.press("enter")
            await pilot.pause()
            assert opened == ["file:///research.md"]
            assert [result.title for result in app.results] == ["Research Sandbox"]

            await pilot.press("right")
            await pilot.pause()
            assert [result.title for result in app.results] == ["Field Notes"]

            await pilot.press("enter")
            await pilot.pause()
            assert [result.title for result in app.results] == ["SharePoint Field Note"]

    asyncio.run(run_app())


def test_tui_right_from_pages_focuses_outgoing_links_before_children(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    hld = IndexedItem(
        source_key="local",
        item_key="hld.md",
        title="HLD",
        url="file:///hld.md",
        path="/tmp/hld.md",
        content_type="text/markdown",
        modified_at="2026-07-16T14:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="High level design.",
        links=("file:///decision.md",),
    )
    child = IndexedItem(
        source_key="local",
        item_key="lld.md",
        title="LLD",
        url="file:///lld.md",
        path="/tmp/lld.md",
        content_type="text/markdown",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="Low level design.",
        parent_key="hld.md",
    )
    decision = IndexedItem(
        source_key="local",
        item_key="decision.md",
        title="Decision",
        url="file:///decision.md",
        path="/tmp/decision.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="Architecture",
        container="architecture",
        snippet="Decision context.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([hld, child, decision])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            results = app.query_one("#results", ListView)
            outgoing = app.query_one("#outgoing", ListView)

            assert app.focused is results
            assert app.results[0].title == "HLD"
            await pilot.press("right")
            await pilot.pause()

            assert app.focused is outgoing
            assert [result.title for result in app.results] == ["HLD", "Decision", "LLD"]
            highlighted = outgoing.highlighted_child
            assert highlighted is not None
            assert getattr(highlighted, "related_item").title == "Decision"

    asyncio.run(run_app())


def test_tui_right_from_pages_focuses_incoming_when_no_outgoing_links(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="jira", name="Jira", type="jira")
    epic = IndexedItem(
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Epic",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-16T14:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic.",
    )
    story = IndexedItem(
        source_key="jira",
        item_key="LAZY-2",
        title="LAZY-2 - Story",
        url="https://example.atlassian.net/browse/LAZY-2",
        path="LAZY/LAZY-2",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Story.",
        links=("https://example.atlassian.net/browse/LAZY-1",),
        parent_key="LAZY-1",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([epic, story])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            results = app.query_one("#results", ListView)
            incoming = app.query_one("#incoming", ListView)

            assert app.focused is results
            await app.apply_search("Epic")
            await pilot.pause()

            assert app.results[0].title == "LAZY-1 - Epic"
            await pilot.press("right")
            await pilot.pause()

            assert app.focused is incoming
            highlighted = incoming.highlighted_child
            assert highlighted is not None
            assert getattr(highlighted, "related_item").title == "LAZY-2 - Story"

    asyncio.run(run_app())


def test_tui_jira_structure_shows_epics_and_drills_to_children(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="jira", name="Jira", type="jira")
    epic = IndexedItem(
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Epic",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-16T14:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic | In Progress | Build the document graph.",
    )
    story = IndexedItem(
        source_key="jira",
        item_key="LAZY-2",
        title="LAZY-2 - Story",
        url="https://example.atlassian.net/browse/LAZY-2",
        path="LAZY/LAZY-2",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Story | To Do | Implement child navigation.",
        parent_key="LAZY-1",
    )
    bug = IndexedItem(
        source_key="jira",
        item_key="LAZY-3",
        title="LAZY-3 - Bug",
        url="https://example.atlassian.net/browse/LAZY-3",
        path="LAZY/LAZY-3",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-16T12:00:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Bug | To Do | Unparented bug.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([epic, story, bug])

    async def run_app() -> None:
        app = LazylensApp(db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)

            assert [getattr(item, "kind", "") for item in categories.children] == [
                "space",
                "jira-project",
                "epic",
                "unparented",
            ]
            assert [result.title for result in app.results] == ["LAZY-2 - Story"]

            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()

            assert [result.title for result in app.results] == ["LAZY-2 - Story"]

            categories.focus()
            categories.index = 3
            await pilot.press("enter")
            await pilot.pause()

            assert [result.title for result in app.results] == ["LAZY-3 - Bug"]

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


def test_tui_project_scopes_results_and_source_scopes_structure(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
database = "{db_path.as_posix()}"

[sources."dsp-beta"]
name = "DSP Beta Confluence"
type = "confluence"
space_keys = ["dsp-beta"]

[sources."DSPBeta"]
name = "DSP Beta Jira"
type = "jira"
project_keys = ["DSPBeta"]

[sources.other]
name = "Other"
type = "local"

[projects.dsp]
name = "DSP"
sources = ["dsp-beta", "DSPBeta"]
"""
    )
    confluence_source = SourceConfig(key="dsp-beta", name="DSP Beta Confluence", type="confluence")
    jira_source = SourceConfig(key="DSPBeta", name="DSP Beta Jira", type="jira")
    other_source = SourceConfig(key="other", name="Other", type="local")
    lld = IndexedItem(
        source_key="dsp-beta",
        item_key="lld",
        title="DSP LLD",
        url="https://example.atlassian.net/wiki/spaces/dsp-beta/pages/1/DSP+LLD",
        path="dsp-beta/DSP LLD",
        content_type="text/html",
        modified_at="2026-07-17T10:00:00+00:00",
        owner="",
        category="Product",
        container="dsp-beta",
        snippet="DSP architecture design.",
    )
    epic = IndexedItem(
        source_key="DSPBeta",
        item_key="DSPBeta-100",
        title="DSPBeta-100 - Relationship navigation",
        url="https://example.atlassian.net/browse/DSPBeta-100",
        path="DSPBeta/DSPBeta-100",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T12:00:00+00:00",
        owner="",
        category="DSP Beta",
        container="DSPBeta",
        snippet="Epic | In Progress | Relationship navigation.",
    )
    story = IndexedItem(
        source_key="DSPBeta",
        item_key="DSPBeta-1",
        title="DSPBeta-1 - Build relationship view",
        url="https://example.atlassian.net/browse/DSPBeta-1",
        path="DSPBeta/DSPBeta-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T11:00:00+00:00",
        owner="",
        category="DSP Beta",
        container="DSPBeta",
        snippet="Story | To Do | Build a relationship view for the DSP project.",
        parent_key="DSPBeta-100",
    )
    bug = IndexedItem(
        source_key="DSPBeta",
        item_key="DSPBeta-2",
        title="DSPBeta-2 - Fix orphaned ticket",
        url="https://example.atlassian.net/browse/DSPBeta-2",
        path="DSPBeta/DSPBeta-2",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T12:30:00+00:00",
        owner="",
        category="DSP Beta",
        container="DSPBeta",
        snippet="Bug | To Do | Fix orphaned ticket.",
    )
    outside = IndexedItem(
        source_key="other",
        item_key="other",
        title="Outside DSP Note",
        url="file:///outside",
        path="/tmp/outside",
        content_type="text/markdown",
        modified_at="2026-07-17T12:00:00+00:00",
        owner="",
        category="Other",
        container="Other",
        snippet="DSP text outside selected project.",
    )

    with Index(db_path) as index:
        index.upsert_source(confluence_source)
        index.upsert_source(jira_source)
        index.upsert_source(other_source)
        index.upsert_items([lld, epic, story, bug, outside])

    async def run_app() -> None:
        app = LazylensApp(config_path=config_path, db_path=db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            categories = app.query_one("#categories", ListView)

            assert app.projects[0].name == "DSP"
            assert [source.key for source in app.project_sources] == ["dsp-beta", "DSPBeta"]
            assert app.query_one("#sources", Static).render().plain.startswith("Sources:")
            assert [getattr(item, "kind", "") for item in categories.children] == [
                "space",
                "folder",
                "jira-project",
                "epic",
                "unparented",
            ]
            assert [result.title for result in app.results] == [
                "DSP LLD",
                "DSPBeta-1 - Build relationship view",
            ]
            assert all(result.source_key != "other" for result in app.results)

            await pilot.press("b")
            await pilot.pause()

            assert app.selected_source_key == "DSPBeta"
            assert [getattr(item, "kind", "") for item in categories.children] == [
                "space",
                "jira-project",
                "epic",
                "unparented",
            ]
            assert [result.title for result in app.results] == [
                "DSPBeta-1 - Build relationship view",
            ]

            categories = app.query_one("#categories", ListView)
            categories.focus()
            categories.index = 1
            await pilot.press("enter")
            await pilot.pause()

            assert [result.title for result in app.results] == ["DSPBeta-1 - Build relationship view"]

            await pilot.press("a")
            await pilot.pause()

            assert app.selected_source_key == "dsp-beta"
            assert [getattr(item, "kind", "") for item in categories.children] == [
                "space",
                "folder",
            ]
            assert [result.title for result in app.results] == ["DSP LLD"]

            await pilot.press("b")
            await pilot.pause()

            categories.focus()
            categories.index = 3
            await pilot.press("enter")
            await pilot.pause()

            assert [result.title for result in app.results] == ["DSPBeta-2 - Fix orphaned ticket"]

            await pilot.press("1")
            await pilot.pause()

            assert app.source_results_active is False
            assert [getattr(item, "kind", "") for item in categories.children] == [
                "space",
                "folder",
                "jira-project",
                "epic",
                "unparented",
            ]
            assert [result.title for result in app.results] == [
                "DSP LLD",
                "DSPBeta-1 - Build relationship view",
            ]

    asyncio.run(run_app())
