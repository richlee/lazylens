from __future__ import annotations

import sqlite3
from pathlib import Path

from lazylens.db import Index
from lazylens.models import IndexedItem, SourceConfig


def test_index_searches_items_with_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="local", name="Local", type="local", root=tmp_path)
    target = IndexedItem(
        source_key="local",
        item_key="hld.md",
        title="HLD",
        url="file:///hld.md",
        path="/tmp/hld.md",
        content_type="text/markdown",
        modified_at="2026-07-16T13:00:00+00:00",
        owner="",
        category="Architecture Notes",
        container="architecture",
        snippet="High level design.",
        parent_key="architecture.md",
    )
    decision = IndexedItem(
        source_key="local",
        item_key="655361",
        title="KDD-002 - API Refresh, Local Search",
        url="https://example.atlassian.net/wiki/spaces/ARCH/pages/655361/KDD-002+-+API+Refresh+Local+Search",
        path="ARCH/KDD-002",
        content_type="text/html",
        modified_at="2026-07-16T13:30:00+00:00",
        owner="",
        category="Architecture Notes",
        container="architecture",
        snippet="API refresh should update the local index.",
    )
    folder = IndexedItem(
        source_key="local",
        item_key="design-folder",
        title="Folderonly",
        url="file:///design-folder",
        path="/tmp/design-folder",
        content_type="application/vnd.lazylens.folder",
        modified_at="2026-07-16T13:15:00+00:00",
        owner="",
        category="Architecture Notes",
        container="architecture",
        snippet="",
        parent_key="architecture.md",
        structure_type="folder",
    )
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
        links=(
            "file:///hld.md",
            "https://example.atlassian.net/wiki/spaces/ARCH/pages/655361/KDD-002+-+API+Refresh%2C+Local+Search",
        ),
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        assert index.upsert_items([target, decision, folder, item]) == 4
        results = index.search("SharePoint")
        folder_results = index.search("Folderonly")
        prefix_results = index.search("Arch")
        multi_prefix_results = index.search("Share Conf")
        punctuation_results = index.search("SharePoint?")
        related = index.related_items(results[0].id)
        hld = index.search("HLD")[0]
        decision_result = index.search("Refresh")[0]
        inbound = index.related_items(hld.id)
        outgoing = index.outgoing_links(results[0].id)
        incoming = index.incoming_links(hld.id)
        fetched = index.item_by_id(hld.id)
        children = index.children(source_key="local", parent_key="architecture.md")

    assert len(results) == 1
    assert folder_results == []
    assert results[0].title == "Architecture Notes"
    assert results[0].source_key == "local"
    assert results[0].category == "Architecture"
    assert results[0].container == "architecture"
    assert prefix_results[0].title == "Architecture Notes"
    assert multi_prefix_results[0].title == "Architecture Notes"
    assert punctuation_results[0].title == "Architecture Notes"
    assert related[0].direction == "Links to"
    assert related[0].item_id == hld.id
    assert related[0].title == "HLD"
    assert inbound[0].direction == "Linked from"
    assert inbound[0].title == "Architecture Notes"
    assert outgoing[0].title == "HLD"
    assert outgoing[1].title == "KDD-002 - API Refresh, Local Search"
    assert outgoing[1].item_id == decision_result.id
    assert incoming[0].title == "Architecture Notes"
    assert fetched is not None
    assert fetched.title == "HLD"
    assert [child.title for child in children] == ["Folderonly", "HLD"]

    with Index(db_path) as index:
        sources = index.sources()
        categories = index.categories(source_key="local")

    assert sources[0].name == "Local"
    assert sources[0].count == 3
    assert categories[0].name == "Architecture"
    assert categories[0].count == 1
    assert categories[0].kind == "folder"
    assert categories[1].name == "Architecture Notes"
    assert categories[1].count == 2
    assert categories[1].kind == "parent-page"


def test_categories_resolve_folder_roots(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="conf", name="Confluence", type="confluence")
    folder = IndexedItem(
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
        index.upsert_items([folder, child_folder, child_page])
        categories = index.categories(source_key="conf")
        children = index.children(source_key="conf", parent_key="folder-1")

    assert len(categories) == 1
    assert categories[0].name == "Architecture Folder"
    assert categories[0].kind == "folder"
    assert categories[0].item_id is not None
    assert categories[0].count == 1
    assert [child.title for child in children] == ["Decisions", "Decision Record"]


def test_index_migrates_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE sources (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            root TEXT,
            updated_at TEXT
        );
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            source_key TEXT NOT NULL REFERENCES sources(key) ON DELETE CASCADE,
            item_key TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            path TEXT NOT NULL,
            content_type TEXT NOT NULL,
            modified_at TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT '',
            snippet TEXT NOT NULL DEFAULT '',
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_key, item_key)
        );
        CREATE VIRTUAL TABLE item_fts USING fts5(
            title,
            snippet,
            path,
            item_id UNINDEXED
        );
        INSERT INTO sources (key, name, type) VALUES ('local', 'Local', 'local');
        INSERT INTO items (
            source_key, item_key, title, url, path, content_type, modified_at
        )
        VALUES ('local', 'notes.md', 'Notes', 'file:///notes.md', '/tmp/notes.md', 'text/markdown', '');
        """
    )
    connection.close()

    with Index(db_path) as index:
        results = index.search("", limit=1)

    assert results[0].category == ""
    assert results[0].container == ""


def test_index_resolves_links_across_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    confluence_source = SourceConfig(key="conf", name="Confluence", type="confluence")
    jira_source = SourceConfig(key="jira", name="Jira", type="jira")
    other_source = SourceConfig(key="other", name="Other", type="local")
    hld = IndexedItem(
        source_key="conf",
        item_key="123",
        title="HLD",
        url="https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD",
        path="ARCH/HLD",
        content_type="text/html",
        modified_at="2026-07-17T10:00:00+00:00",
        owner="",
        category="Architecture",
        container="ARCH",
        snippet="High level design.",
        links=("https://example.atlassian.net/browse/LAZY-1",),
    )
    epic = IndexedItem(
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Build document graph",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T10:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic.",
        links=("https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD",),
    )
    colliding_key = IndexedItem(
        source_key="other",
        item_key="LAZY-1",
        title="Wrong duplicate key",
        url="file:///wrong-duplicate-key",
        path="/tmp/wrong-duplicate-key",
        content_type="text/markdown",
        modified_at="2026-07-17T10:45:00+00:00",
        owner="",
        category="Other",
        container="Other",
        snippet="This item has the same item key as the Jira issue but is from another source.",
    )

    with Index(db_path) as index:
        index.upsert_source(confluence_source)
        index.upsert_source(jira_source)
        index.upsert_source(other_source)
        index.upsert_items([hld, epic, colliding_key])
        hld_result = index.search("HLD")[0]
        epic_result = index.search("LAZY")[0]
        hld_outgoing = index.outgoing_links(hld_result.id)
        epic_incoming = index.incoming_links(epic_result.id)
        epic_outgoing = index.outgoing_links(epic_result.id)
        hld_incoming = index.incoming_links(hld_result.id)

    assert hld_outgoing[0].title == "LAZY-1 - Build document graph"
    assert hld_outgoing[0].item_id == epic_result.id
    assert epic_incoming[0].title == "HLD"
    assert epic_outgoing[0].title == "HLD"
    assert hld_incoming[0].title == "LAZY-1 - Build document graph"


def test_index_exposes_jira_project_root_and_epics(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    source = SourceConfig(key="jira", name="Personal Jira", type="jira")
    epic = IndexedItem(
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Build document graph",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T10:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic | In Progress | Build the relationship view.",
    )
    story = IndexedItem(
        source_key="jira",
        item_key="LAZY-2",
        title="LAZY-2 - Add source selector",
        url="https://example.atlassian.net/browse/LAZY-2",
        path="LAZY/LAZY-2",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T11:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Story | To Do | Add source selector.",
        parent_key="LAZY-1",
    )
    old_story = IndexedItem(
        source_key="jira",
        item_key="LAZY-0",
        title="LAZY-0 - Earlier child ticket",
        url="https://example.atlassian.net/browse/LAZY-0",
        path="LAZY/LAZY-0",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T09:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Story | To Do | Older child ticket.",
        parent_key="LAZY-1",
    )
    bug = IndexedItem(
        source_key="jira",
        item_key="LAZY-3",
        title="LAZY-3 - Fix stray notification",
        url="https://example.atlassian.net/browse/LAZY-3",
        path="LAZY/LAZY-3",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T12:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Bug | To Do | Fix notification.",
    )
    old_bug = IndexedItem(
        source_key="jira",
        item_key="LAZY-00",
        title="LAZY-00 - Earlier unparented bug",
        url="https://example.atlassian.net/browse/LAZY-00",
        path="LAZY/LAZY-00",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T08:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Bug | To Do | Older notification.",
    )

    with Index(db_path) as index:
        index.upsert_source(source)
        index.upsert_items([epic, story, old_story, bug, old_bug])
        structure = index.jira_structure(source_key="jira")
        project_epics = index.jira_epic_structure(source_keys=["jira"])
        unparented = index.jira_unparented_structure(source_keys=["jira"])
        epic_children = index.jira_epic_children(source_key="jira")
        unparented_items = index.jira_unparented_items(source_key="jira")
        overview = index.project_overview(source_keys=["jira"])
        children = index.children(source_key="jira", parent_key="LAZY-1")

    assert [node.kind for node in structure] == ["jira-project", "epic", "unparented"]
    assert structure[0].name == "LAZY"
    assert structure[0].count == 5
    assert structure[1].name == "LAZY-1 - Build document graph"
    assert structure[1].count == 2
    assert structure[2].name == "Unparented"
    assert structure[2].count == 2
    assert [node.name for node in project_epics] == ["LAZY-1 - Build document graph"]
    assert [node.name for node in unparented] == ["Unparented"]
    assert [item.title for item in epic_children] == [
        "LAZY-2 - Add source selector",
        "LAZY-0 - Earlier child ticket",
    ]
    assert [item.title for item in unparented_items] == [
        "LAZY-3 - Fix stray notification",
        "LAZY-00 - Earlier unparented bug",
    ]
    assert [item.title for item in overview] == [
        "LAZY-2 - Add source selector",
        "LAZY-0 - Earlier child ticket",
    ]
    assert [item.title for item in children] == [
        "LAZY-2 - Add source selector",
        "LAZY-0 - Earlier child ticket",
    ]


def test_index_scopes_search_and_relationships_to_project_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite3"
    confluence_source = SourceConfig(key="conf", name="Confluence", type="confluence")
    jira_source = SourceConfig(key="jira", name="Jira", type="jira")
    other_source = SourceConfig(key="other", name="Other", type="local")
    hld = IndexedItem(
        source_key="conf",
        item_key="123",
        title="HLD",
        url="https://example.atlassian.net/wiki/spaces/ARCH/pages/123/HLD",
        path="ARCH/HLD",
        content_type="text/html",
        modified_at="2026-07-17T10:00:00+00:00",
        owner="",
        category="Architecture",
        container="ARCH",
        snippet="High level design.",
        links=("https://example.atlassian.net/browse/LAZY-1",),
    )
    epic = IndexedItem(
        source_key="jira",
        item_key="LAZY-1",
        title="LAZY-1 - Build document graph",
        url="https://example.atlassian.net/browse/LAZY-1",
        path="LAZY/LAZY-1",
        content_type="application/vnd.atlassian.jira.issue",
        modified_at="2026-07-17T10:30:00+00:00",
        owner="",
        category="LazyLens",
        container="LAZY",
        snippet="Epic.",
    )
    outside = IndexedItem(
        source_key="other",
        item_key="outside.md",
        title="Outside HLD Reference",
        url="file:///outside.md",
        path="/tmp/outside.md",
        content_type="text/markdown",
        modified_at="2026-07-17T10:45:00+00:00",
        owner="",
        category="Other",
        container="Other",
        snippet="High level design outside the project.",
        links=("https://example.atlassian.net/browse/LAZY-1",),
    )

    with Index(db_path) as index:
        index.upsert_source(confluence_source)
        index.upsert_source(jira_source)
        index.upsert_source(other_source)
        index.upsert_items([hld, epic, outside])
        project_results = index.search("HLD", source_keys=["conf", "jira"])
        epic_result = index.search("LAZY", source_keys=["conf", "jira"])[0]
        incoming = index.incoming_links(epic_result.id, source_keys=["conf", "jira"])

    assert [result.title for result in project_results] == ["HLD"]
    assert [item.title for item in incoming] == ["HLD"]
