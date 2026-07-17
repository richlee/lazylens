from __future__ import annotations

import sqlite3
from pathlib import Path

from lazylens.db import Index
from lazylens.models import IndexedItem, SourceConfig


def test_index_searches_items_with_fts(tmp_path: Path) -> None:
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
        assert index.upsert_items([item]) == 1
        results = index.search("SharePoint")
        prefix_results = index.search("Arch")
        multi_prefix_results = index.search("Share Conf")
        punctuation_results = index.search("SharePoint?")

    assert len(results) == 1
    assert results[0].title == "Architecture Notes"
    assert results[0].source_key == "local"
    assert results[0].category == "Architecture"
    assert results[0].container == "architecture"
    assert prefix_results[0].title == "Architecture Notes"
    assert multi_prefix_results[0].title == "Architecture Notes"
    assert punctuation_results[0].title == "Architecture Notes"

    with Index(db_path) as index:
        sources = index.sources()
        categories = index.categories(source_key="local")

    assert sources[0].name == "Local"
    assert sources[0].count == 1
    assert categories[0].name == "Architecture"
    assert categories[0].count == 1


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
