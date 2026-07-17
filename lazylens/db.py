from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from lazylens.models import CategorySummary, IndexedItem, RelatedItem, SearchResult, SourceConfig, SourceSummary
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

CREATE TABLE IF NOT EXISTS item_links (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL,
    from_item_key TEXT NOT NULL,
    target_url TEXT NOT NULL,
    UNIQUE(source_key, from_item_key, target_url)
);
"""


def prefix_fts_query(query: str) -> str:
    terms = re.findall(r"\w+", query)
    return " ".join(f"{term}*" for term in terms)


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
            self.connection.execute(
                "DELETE FROM item_links WHERE source_key = ? AND from_item_key = ?",
                (item.source_key, item.item_key),
            )
            self.connection.executemany(
                """
                INSERT INTO item_links (source_key, from_item_key, target_url)
                VALUES (?, ?, ?)
                ON CONFLICT(source_key, from_item_key, target_url) DO NOTHING
                """,
                [(item.source_key, item.item_key, link) for link in item.links if link],
            )
            count += 1
        self.connection.commit()
        return count

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        source_key: str | None = None,
        category: str | None = None,
    ) -> list[SearchResult]:
        filters = []
        params: list[object] = []
        if source_key:
            filters.append("items.source_key = ?")
            params.append(source_key)
        if category:
            filters.append("items.category = ?")
            params.append(category)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        fts_query = prefix_fts_query(query)
        if not query.strip():
            rows = self.connection.execute(
                f"""
                SELECT items.*, 0.0 AS rank
                FROM items
                {where}
                ORDER BY modified_at DESC, title COLLATE NOCASE
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        elif not fts_query:
            rows = []
        else:
            search_filters = ["item_fts MATCH ?", *filters]
            rows = self.connection.execute(
                f"""
                SELECT items.*, bm25(item_fts) AS rank
                FROM item_fts
                JOIN items ON items.id = item_fts.item_id
                WHERE {' AND '.join(search_filters)}
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, *params, limit),
            ).fetchall()
        return [
            search_result_from_row(row)
            for row in rows
        ]

    def item_by_id(self, item_id: int) -> SearchResult | None:
        row = self.connection.execute(
            """
            SELECT items.*, 0.0 AS rank
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        return search_result_from_row(row) if row else None

    def item_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()
        return int(row["count"])

    def sources(self) -> list[SourceSummary]:
        rows = self.connection.execute(
            """
            SELECT sources.key, sources.name, sources.type, COUNT(items.id) AS count
            FROM sources
            LEFT JOIN items ON items.source_key = sources.key
            GROUP BY sources.key, sources.name, sources.type
            ORDER BY sources.name COLLATE NOCASE
            """
        ).fetchall()
        return [
            SourceSummary(
                key=str(row["key"]),
                name=str(row["name"]),
                type=str(row["type"]),
                count=int(row["count"]),
            )
            for row in rows
        ]

    def categories(self, *, source_key: str | None = None) -> list[CategorySummary]:
        if source_key:
            rows = self.connection.execute(
                """
                SELECT category, COUNT(*) AS count
                FROM items
                WHERE source_key = ?
                GROUP BY category
                ORDER BY category COLLATE NOCASE
                """,
                (source_key,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT category, COUNT(*) AS count
                FROM items
                GROUP BY category
                ORDER BY category COLLATE NOCASE
                """
            ).fetchall()
        return [
            CategorySummary(
                key=str(row["category"]),
                name=str(row["category"]) or "Uncategorised",
                count=int(row["count"]),
            )
            for row in rows
        ]

    def related_items(self, item_id: int, *, limit: int = 12) -> list[RelatedItem]:
        item = self.connection.execute(
            "SELECT source_key, item_key, url FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            return []
        rows = self.connection.execute(
            """
            SELECT 'Links to' AS direction,
                   target.id AS item_id,
                   COALESCE(target.title, item_links.target_url) AS title,
                   item_links.target_url AS url,
                   0 AS sort_order
            FROM item_links
            LEFT JOIN items AS target
              ON target.source_key = item_links.source_key
             AND target.url = item_links.target_url
            WHERE item_links.source_key = ?
              AND item_links.from_item_key = ?

            UNION ALL

            SELECT 'Linked from' AS direction,
                   source.id AS item_id,
                   source.title AS title,
                   source.url AS url,
                   1 AS sort_order
            FROM item_links
            JOIN items AS source
              ON source.source_key = item_links.source_key
             AND source.item_key = item_links.from_item_key
            WHERE item_links.source_key = ?
              AND item_links.target_url = ?

            ORDER BY sort_order, title COLLATE NOCASE
            LIMIT ?
            """,
            (
                str(item["source_key"]),
                str(item["item_key"]),
                str(item["source_key"]),
                str(item["url"]),
                limit,
            ),
        ).fetchall()
        return [
            RelatedItem(
                item_id=int(row["item_id"]) if row["item_id"] is not None else None,
                direction=str(row["direction"]),
                title=str(row["title"]),
                url=str(row["url"]),
            )
            for row in rows
        ]

    def outgoing_links(self, item_id: int, *, limit: int = 50) -> list[RelatedItem]:
        item = self.connection.execute(
            "SELECT source_key, item_key FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            return []
        rows = self.connection.execute(
            """
            SELECT target.id AS item_id,
                   COALESCE(target.title, item_links.target_url) AS title,
                   item_links.target_url AS url
            FROM item_links
            LEFT JOIN items AS target
              ON target.source_key = item_links.source_key
             AND target.url = item_links.target_url
            WHERE item_links.source_key = ?
              AND item_links.from_item_key = ?
            ORDER BY title COLLATE NOCASE
            LIMIT ?
            """,
            (str(item["source_key"]), str(item["item_key"]), limit),
        ).fetchall()
        return [
            RelatedItem(
                item_id=int(row["item_id"]) if row["item_id"] is not None else None,
                direction="Links to",
                title=str(row["title"]),
                url=str(row["url"]),
            )
            for row in rows
        ]

    def incoming_links(self, item_id: int, *, limit: int = 50) -> list[RelatedItem]:
        item = self.connection.execute(
            "SELECT source_key, url FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            return []
        rows = self.connection.execute(
            """
            SELECT source.id AS item_id,
                   source.title AS title,
                   source.url AS url
            FROM item_links
            JOIN items AS source
              ON source.source_key = item_links.source_key
             AND source.item_key = item_links.from_item_key
            WHERE item_links.source_key = ?
              AND item_links.target_url = ?
            ORDER BY source.title COLLATE NOCASE
            LIMIT ?
            """,
            (str(item["source_key"]), str(item["url"]), limit),
        ).fetchall()
        return [
            RelatedItem(
                item_id=int(row["item_id"]),
                direction="Linked from",
                title=str(row["title"]),
                url=str(row["url"]),
            )
            for row in rows
        ]

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
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS item_links (
                id INTEGER PRIMARY KEY,
                source_key TEXT NOT NULL,
                from_item_key TEXT NOT NULL,
                target_url TEXT NOT NULL,
                UNIQUE(source_key, from_item_key, target_url)
            )
            """
        )
        self.connection.commit()


def search_result_from_row(row: sqlite3.Row) -> SearchResult:
    return SearchResult(
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
