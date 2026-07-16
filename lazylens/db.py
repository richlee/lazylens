from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from lazylens.models import IndexedItem, SearchResult, SourceConfig
from lazylens.paths import default_db_path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    root TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES sources(key) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_key, item_key)
);

CREATE VIRTUAL TABLE IF NOT EXISTS item_fts USING fts5(
    title,
    snippet,
    category,
    path,
    item_id UNINDEXED
);
"""


class Index:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Index:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def upsert_source(self, source: SourceConfig) -> None:
        self.connection.execute(
            """
            INSERT INTO sources (key, name, type, root, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                root = excluded.root,
                updated_at = CURRENT_TIMESTAMP
            """,
            (source.key, source.name, source.type, str(source.root) if source.root else None),
        )

    def upsert_items(self, items: Iterable[IndexedItem]) -> int:
        count = 0
        for item in items:
            cursor = self.connection.execute(
                """
                INSERT INTO items (
                    source_key, item_key, title, url, path, content_type, modified_at,
                    owner, category, container, snippet, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_key, item_key) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    path = excluded.path,
                    content_type = excluded.content_type,
                    modified_at = excluded.modified_at,
                    owner = excluded.owner,
                    category = excluded.category,
                    container = excluded.container,
                    snippet = excluded.snippet,
                    indexed_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (
                    item.source_key,
                    item.item_key,
                    item.title,
                    item.url,
                    item.path,
                    item.content_type,
                    item.modified_at,
                    item.owner,
                    item.category,
                    item.container,
                    item.snippet,
                ),
            )
            item_id = int(cursor.fetchone()["id"])
            self.connection.execute("DELETE FROM item_fts WHERE item_id = ?", (item_id,))
            self.connection.execute(
                "INSERT INTO item_fts (title, snippet, category, path, item_id) VALUES (?, ?, ?, ?, ?)",
                (item.title, item.snippet, item.category, item.path, item_id),
            )
            count += 1
        self.connection.commit()
        return count

    def search(self, query: str, *, limit: int = 20) -> list[SearchResult]:
        if not query.strip():
            rows = self.connection.execute(
                """
                SELECT items.*, 0.0 AS rank
                FROM items
                ORDER BY modified_at DESC, title COLLATE NOCASE
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT items.*, bm25(item_fts) AS rank
                FROM item_fts
                JOIN items ON items.id = item_fts.item_id
                WHERE item_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [
            SearchResult(
                id=int(row["id"]),
                source_key=str(row["source_key"]),
                title=str(row["title"]),
                url=str(row["url"]),
                path=str(row["path"]),
                content_type=str(row["content_type"]),
                modified_at=str(row["modified_at"]),
                owner=str(row["owner"]),
                category=str(row["category"]),
                container=str(row["container"]),
                snippet=str(row["snippet"]),
                rank=float(row["rank"]),
            )
            for row in rows
        ]

    def item_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()
        return int(row["count"])

    def _migrate(self) -> None:
        columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(items)").fetchall()
        }
        if "category" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        if "container" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN container TEXT NOT NULL DEFAULT ''")

        fts_columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(item_fts)").fetchall()
        }
        if "category" not in fts_columns:
            self.connection.execute("DROP TABLE item_fts")
            self.connection.execute(
                """
                CREATE VIRTUAL TABLE item_fts USING fts5(
                    title,
                    snippet,
                    category,
                    path,
                    item_id UNINDEXED
                )
                """
            )
            self.connection.execute(
                """
                INSERT INTO item_fts (title, snippet, category, path, item_id)
                SELECT title, snippet, category, path, id FROM items
                """
            )
        self.connection.commit()
