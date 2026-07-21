from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

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
    parent_key TEXT NOT NULL DEFAULT '',
    structure_type TEXT NOT NULL DEFAULT 'page',
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
                    owner, category, container, snippet, parent_key, structure_type, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                    parent_key = excluded.parent_key,
                    structure_type = excluded.structure_type,
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
                    item.parent_key,
                    item.structure_type,
                ),
            )
            item_id = int(cursor.fetchone()["id"])
            self.connection.execute("DELETE FROM item_fts WHERE item_id = ?", (item_id,))
            if item.structure_type == "page":
                self.connection.execute(
                    "INSERT INTO item_fts (title, snippet, category, path, item_id) VALUES (?, ?, ?, ?, ?)",
                    (item.title, item.snippet, item.category, item.path, item_id),
                )
            self.connection.execute(
                "DELETE FROM item_links WHERE source_key = ? AND from_item_key = ?",
                (item.source_key, item.item_key),
            )
            if item.structure_type == "page":
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

    def items_by_source(self, source_key: str) -> dict[str, SearchResult]:
        rows = self.connection.execute(
            """
            SELECT items.*, 0.0 AS rank
            FROM items
            WHERE source_key = ?
            """,
            (source_key,),
        ).fetchall()
        return {str(row["item_key"]): search_result_from_row(row) for row in rows}

    def delete_source_items(self, source_key: str, item_keys: Iterable[str]) -> int:
        keys = sorted(set(item_keys))
        if not keys:
            return 0

        total = 0
        for index in range(0, len(keys), 400):
            total += self._delete_source_items_batch(source_key, keys[index:index + 400])
        return total

    def _delete_source_items_batch(self, source_key: str, keys: list[str]) -> int:
        if not keys:
            return 0

        placeholders = ", ".join("?" for _key in keys)
        rows = self.connection.execute(
            f"""
            SELECT id, item_key
            FROM items
            WHERE source_key = ?
              AND item_key IN ({placeholders})
            """,
            (source_key, *keys),
        ).fetchall()
        if not rows:
            return 0

        item_ids = [int(row["id"]) for row in rows]
        existing_keys = [str(row["item_key"]) for row in rows]
        id_placeholders = ", ".join("?" for _item_id in item_ids)
        key_placeholders = ", ".join("?" for _key in existing_keys)

        self.connection.execute(f"DELETE FROM item_fts WHERE item_id IN ({id_placeholders})", item_ids)
        self.connection.execute(
            f"""
            DELETE FROM item_links
            WHERE source_key = ?
              AND from_item_key IN ({key_placeholders})
            """,
            (source_key, *existing_keys),
        )
        self.connection.execute(
            f"""
            DELETE FROM items
            WHERE source_key = ?
              AND item_key IN ({key_placeholders})
            """,
            (source_key, *existing_keys),
        )
        self.connection.commit()
        return len(existing_keys)

    def delete_source_items_not_seen(self, source_key: str, seen_item_keys: Iterable[str]) -> int:
        existing = set(self.items_by_source(source_key))
        seen = set(seen_item_keys)
        return self.delete_source_items(source_key, existing - seen)

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        source_key: str | None = None,
        source_keys: Iterable[str] | None = None,
        category: str | None = None,
    ) -> list[SearchResult]:
        filters = []
        params: list[object] = []
        if source_key:
            filters.append("items.source_key = ?")
            params.append(source_key)
        project_source_keys = sorted(set(source_keys or []))
        if project_source_keys:
            placeholders = ", ".join("?" for _source_key in project_source_keys)
            filters.append(f"items.source_key IN ({placeholders})")
            params.extend(project_source_keys)
        if category:
            filters.append("items.category = ?")
            params.append(category)
        filters.append("items.structure_type = 'page'")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        fts_query = prefix_fts_query(query)
        if not query.strip():
            rows = self.connection.execute(
                f"""
                SELECT items.*, 0.0 AS rank
                FROM items
                JOIN sources ON sources.key = items.source_key
                {where}
                ORDER BY
                    CASE sources.type
                        WHEN 'confluence' THEN 0
                        WHEN 'local' THEN 1
                        WHEN 'jira' THEN 2
                        ELSE 3
                    END,
                    modified_at DESC,
                    title COLLATE NOCASE
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
                JOIN sources ON sources.key = items.source_key
                WHERE {' AND '.join(search_filters)}
                ORDER BY
                    rank,
                    CASE sources.type
                        WHEN 'confluence' THEN 0
                        WHEN 'local' THEN 1
                        WHEN 'jira' THEN 2
                        ELSE 3
                    END
                LIMIT ?
                """,
                (fts_query, *params, limit),
            ).fetchall()
        return [
            search_result_from_row(row)
            for row in rows
        ]

    def project_overview(
        self,
        *,
        source_keys: Iterable[str],
        limit: int = 200,
    ) -> list[SearchResult]:
        project_source_keys = sorted(set(source_keys))
        if not project_source_keys:
            return []
        placeholders = ", ".join("?" for _source_key in project_source_keys)
        rows = self.connection.execute(
            f"""
            SELECT items.*, 0.0 AS rank
            FROM items
            JOIN sources ON sources.key = items.source_key
            WHERE items.source_key IN ({placeholders})
              AND items.structure_type = 'page'
              AND (
                    sources.type != 'jira'
                 OR EXISTS (
                        SELECT 1
                        FROM items AS epic
                        WHERE epic.source_key = items.source_key
                          AND epic.item_key = items.parent_key
                          AND epic.structure_type = 'page'
                          AND LOWER(epic.snippet) LIKE 'epic%'
                    )
              )
            ORDER BY
                CASE sources.type
                    WHEN 'confluence' THEN 0
                    WHEN 'local' THEN 1
                    WHEN 'jira' THEN 2
                    ELSE 3
                END,
                modified_at DESC,
                title COLLATE NOCASE
            LIMIT ?
            """,
            (*project_source_keys, limit),
        ).fetchall()
        return [search_result_from_row(row) for row in rows]

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
                           AND items.structure_type = 'page'
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

    def categories(
        self,
        *,
        source_key: str | None = None,
        source_keys: Iterable[str] | None = None,
    ) -> list[CategorySummary]:
        project_source_keys = sorted(set(source_keys or []))
        if source_key:
            rows = self.connection.execute(
                """
                SELECT grouped.source_key,
                       grouped.category,
                       grouped.count,
                       top_level.id AS item_id,
                       CASE
                         WHEN top_level.id IS NULL THEN 'folder'
                         WHEN top_level.structure_type = 'folder' THEN 'folder'
                         WHEN EXISTS (
                           SELECT 1
                           FROM items AS child
                           WHERE child.source_key = top_level.source_key
                             AND child.parent_key = top_level.item_key
                         ) THEN 'parent-page'
                         ELSE top_level.structure_type
                       END AS kind
                FROM (
                    SELECT source_key, category, COUNT(*) AS count
                    FROM items
                    WHERE source_key = ?
                      AND structure_type = 'page'
                    GROUP BY source_key, category
                ) AS grouped
                LEFT JOIN items AS top_level
                  ON top_level.source_key = grouped.source_key
                 AND top_level.title = grouped.category
                 AND top_level.structure_type IN ('page', 'folder')
                ORDER BY grouped.category COLLATE NOCASE
                """,
                (source_key,),
            ).fetchall()
        elif project_source_keys:
            placeholders = ", ".join("?" for _source_key in project_source_keys)
            rows = self.connection.execute(
                f"""
                SELECT grouped.source_key,
                       grouped.category,
                       grouped.count,
                       top_level.id AS item_id,
                       CASE
                         WHEN top_level.id IS NULL THEN 'folder'
                         WHEN top_level.structure_type = 'folder' THEN 'folder'
                         WHEN EXISTS (
                           SELECT 1
                           FROM items AS child
                           WHERE child.source_key = top_level.source_key
                             AND child.parent_key = top_level.item_key
                         ) THEN 'parent-page'
                         ELSE top_level.structure_type
                       END AS kind
                FROM (
                    SELECT source_key, category, COUNT(*) AS count
                    FROM items
                    WHERE source_key IN ({placeholders})
                      AND structure_type = 'page'
                    GROUP BY source_key, category
                ) AS grouped
                LEFT JOIN items AS top_level
                  ON top_level.source_key = grouped.source_key
                 AND top_level.title = grouped.category
                 AND top_level.structure_type IN ('page', 'folder')
                ORDER BY grouped.category COLLATE NOCASE
                """,
                tuple(project_source_keys),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT grouped.source_key,
                       grouped.category,
                       grouped.count,
                       top_level.id AS item_id,
                       CASE
                         WHEN top_level.id IS NULL THEN 'folder'
                         WHEN top_level.structure_type = 'folder' THEN 'folder'
                         WHEN EXISTS (
                           SELECT 1
                           FROM items AS child
                           WHERE child.source_key = top_level.source_key
                             AND child.parent_key = top_level.item_key
                         ) THEN 'parent-page'
                         ELSE top_level.structure_type
                       END AS kind
                FROM (
                    SELECT source_key, category, COUNT(*) AS count
                    FROM items
                    WHERE structure_type = 'page'
                    GROUP BY source_key, category
                ) AS grouped
                LEFT JOIN items AS top_level
                  ON top_level.source_key = grouped.source_key
                 AND top_level.title = grouped.category
                 AND top_level.structure_type IN ('page', 'folder')
                ORDER BY grouped.category COLLATE NOCASE
                """
            ).fetchall()
        return [
            CategorySummary(
                key=str(row["category"]),
                name=str(row["category"]) or "Uncategorised",
                count=int(row["count"]),
                source_key=str(row["source_key"]),
                kind=str(row["kind"]),
                item_id=int(row["item_id"]) if row["item_id"] is not None else None,
            )
            for row in rows
        ]

    def jira_structure(self, *, source_key: str) -> list[CategorySummary]:
        source = self.connection.execute(
            """
            SELECT sources.name,
                   COUNT(items.id) AS count,
                   GROUP_CONCAT(DISTINCT NULLIF(items.container, '')) AS containers
            FROM sources
            LEFT JOIN items ON items.source_key = sources.key
                           AND items.structure_type = 'page'
            WHERE sources.key = ?
            GROUP BY sources.key, sources.name
            """,
            (source_key,),
        ).fetchone()
        if source is None:
            return []

        containers = [
            container
            for container in str(source["containers"] or "").split(",")
            if container
        ]
        root_name = containers[0] if len(containers) == 1 else str(source["name"])
        root = CategorySummary(
            key=f"{source_key}:jira-root",
            name=root_name,
            count=int(source["count"]),
            source_key=source_key,
            kind="jira-project",
        )
        rows = self.connection.execute(
            """
            SELECT epic.id,
                   epic.item_key,
                   epic.title,
                   COUNT(child.id) AS child_count
            FROM items AS epic
            LEFT JOIN items AS child
              ON child.source_key = epic.source_key
             AND child.parent_key = epic.item_key
             AND child.structure_type = 'page'
            WHERE epic.source_key = ?
              AND epic.structure_type = 'page'
              AND LOWER(epic.snippet) LIKE 'epic%'
            GROUP BY epic.id, epic.item_key, epic.title
            ORDER BY epic.title COLLATE NOCASE
            """,
            (source_key,),
        ).fetchall()
        epics = [
            CategorySummary(
                key=str(row["item_key"]),
                name=str(row["title"]),
                count=int(row["child_count"]),
                source_key=source_key,
                kind="epic",
                item_id=int(row["id"]),
            )
            for row in rows
        ]
        unparented = self.jira_unparented_structure(source_keys=[source_key])
        return [root, *epics, *unparented]

    def jira_epic_structure(self, *, source_keys: Iterable[str]) -> list[CategorySummary]:
        project_source_keys = sorted(set(source_keys))
        if not project_source_keys:
            return []
        placeholders = ", ".join("?" for _source_key in project_source_keys)
        rows = self.connection.execute(
            f"""
            SELECT epic.id,
                   epic.item_key,
                   epic.title,
                   epic.source_key,
                   COUNT(child.id) AS child_count
            FROM items AS epic
            JOIN sources ON sources.key = epic.source_key
            LEFT JOIN items AS child
              ON child.source_key = epic.source_key
             AND child.parent_key = epic.item_key
             AND child.structure_type = 'page'
            WHERE epic.source_key IN ({placeholders})
              AND sources.type = 'jira'
              AND epic.structure_type = 'page'
              AND LOWER(epic.snippet) LIKE 'epic%'
            GROUP BY epic.id, epic.item_key, epic.title, epic.source_key
            ORDER BY epic.title COLLATE NOCASE
            """,
            tuple(project_source_keys),
        ).fetchall()
        return [
            CategorySummary(
                key=f"{row['source_key']}:{row['item_key']}",
                name=str(row["title"]),
                count=int(row["child_count"]),
                source_key=str(row["source_key"]),
                kind="epic",
                item_id=int(row["id"]),
            )
            for row in rows
        ]

    def jira_unparented_structure(self, *, source_keys: Iterable[str]) -> list[CategorySummary]:
        project_source_keys = sorted(set(source_keys))
        if not project_source_keys:
            return []
        placeholders = ", ".join("?" for _source_key in project_source_keys)
        rows = self.connection.execute(
            f"""
            SELECT items.source_key,
                   sources.name,
                   COUNT(items.id) AS count
            FROM items
            JOIN sources ON sources.key = items.source_key
            WHERE items.source_key IN ({placeholders})
              AND sources.type = 'jira'
              AND items.structure_type = 'page'
              AND LOWER(items.snippet) NOT LIKE 'epic%'
              AND (
                    items.parent_key = ''
                 OR NOT EXISTS (
                        SELECT 1
                        FROM items AS epic
                        WHERE epic.source_key = items.source_key
                          AND epic.item_key = items.parent_key
                          AND epic.structure_type = 'page'
                          AND LOWER(epic.snippet) LIKE 'epic%'
                    )
              )
            GROUP BY items.source_key, sources.name
            ORDER BY sources.name COLLATE NOCASE
            """,
            tuple(project_source_keys),
        ).fetchall()
        return [
            CategorySummary(
                key=f"{row['source_key']}:unparented",
                name="Unparented" if len(rows) == 1 else f"Unparented - {row['name']}",
                count=int(row["count"]),
                source_key=str(row["source_key"]),
                kind="unparented",
            )
            for row in rows
        ]

    def jira_epic_children(self, *, source_key: str) -> list[SearchResult]:
        rows = self.connection.execute(
            """
            SELECT child.*, 0.0 AS rank
            FROM items AS child
            JOIN items AS epic
              ON epic.source_key = child.source_key
             AND epic.item_key = child.parent_key
             AND epic.structure_type = 'page'
             AND LOWER(epic.snippet) LIKE 'epic%'
            WHERE child.source_key = ?
              AND child.structure_type = 'page'
            ORDER BY child.modified_at DESC, child.title COLLATE NOCASE
            """,
            (source_key,),
        ).fetchall()
        return [search_result_from_row(row) for row in rows]

    def jira_unparented_items(self, *, source_key: str) -> list[SearchResult]:
        rows = self.connection.execute(
            """
            SELECT items.*, 0.0 AS rank
            FROM items
            JOIN sources ON sources.key = items.source_key
            WHERE items.source_key = ?
              AND sources.type = 'jira'
              AND items.structure_type = 'page'
              AND LOWER(items.snippet) NOT LIKE 'epic%'
              AND (
                    items.parent_key = ''
                 OR NOT EXISTS (
                        SELECT 1
                        FROM items AS epic
                        WHERE epic.source_key = items.source_key
                          AND epic.item_key = items.parent_key
                          AND epic.structure_type = 'page'
                          AND LOWER(epic.snippet) LIKE 'epic%'
                    )
              )
            ORDER BY items.modified_at DESC, items.title COLLATE NOCASE
            """,
            (source_key,),
        ).fetchall()
        return [search_result_from_row(row) for row in rows]

    def children(self, *, source_key: str, parent_key: str) -> list[SearchResult]:
        rows = self.connection.execute(
            """
            SELECT items.*, 0.0 AS rank
            FROM items
            JOIN sources ON sources.key = items.source_key
            WHERE source_key = ?
              AND parent_key = ?
            ORDER BY
                CASE
                    WHEN sources.type != 'jira' AND structure_type = 'folder' THEN 0
                    WHEN sources.type != 'jira' THEN 1
                    ELSE 0
                END,
                CASE WHEN sources.type = 'jira' THEN items.modified_at END DESC,
                title COLLATE NOCASE
            """,
            (source_key, parent_key),
        ).fetchall()
        return [search_result_from_row(row) for row in rows]

    def related_items(
        self,
        item_id: int,
        *,
        limit: int = 12,
        source_keys: Iterable[str] | None = None,
    ) -> list[RelatedItem]:
        return [
            *self.outgoing_links(item_id, limit=limit, source_keys=source_keys),
            *self.incoming_links(item_id, limit=limit, source_keys=source_keys),
        ][:limit]

    def outgoing_links(
        self,
        item_id: int,
        *,
        limit: int = 50,
        source_keys: Iterable[str] | None = None,
    ) -> list[RelatedItem]:
        item = self.connection.execute(
            "SELECT source_key, item_key FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            return []
        link_rows = self.connection.execute(
            """
            SELECT target_url
            FROM item_links
            WHERE item_links.source_key = ?
              AND item_links.from_item_key = ?
            ORDER BY target_url COLLATE NOCASE
            LIMIT ?
            """,
            (str(item["source_key"]), str(item["item_key"]), limit),
        ).fetchall()
        target_lookup = self.item_lookup_for_sources(source_keys)
        return [
            related_item_from_target_url(str(row["target_url"]), "Links to", target_lookup)
            for row in link_rows
        ]

    def incoming_links(
        self,
        item_id: int,
        *,
        limit: int = 50,
        source_keys: Iterable[str] | None = None,
    ) -> list[RelatedItem]:
        item = self.connection.execute(
            "SELECT source_key, url FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            return []
        target_key = relationship_url_key(str(item["url"]))
        project_source_keys = sorted(set(source_keys or []))
        source_filter = ""
        params: list[object] = []
        if project_source_keys:
            placeholders = ", ".join("?" for _source_key in project_source_keys)
            source_filter = f"WHERE source_key IN ({placeholders})"
            params.extend(project_source_keys)
        link_rows = self.connection.execute(
            f"""
            SELECT source_key, from_item_key, target_url
            FROM item_links
            {source_filter}
            ORDER BY target_url COLLATE NOCASE
            """,
            params,
        ).fetchall()
        source_lookup = self.item_lookup_for_sources(source_keys)
        related = []
        for row in link_rows:
            if relationship_url_key(str(row["target_url"])) != target_key:
                continue
            source_item = source_lookup.by_source_item_key.get((str(row["source_key"]), str(row["from_item_key"])))
            if source_item is None:
                continue
            related.append(
                RelatedItem(
                    item_id=source_item.id,
                    direction="Linked from",
                    title=source_item.title,
                    url=source_item.url,
                )
            )
        return sorted(related, key=lambda item: item.title.lower())[:limit]

    def item_lookup_for_sources(self, source_keys: Iterable[str] | None = None) -> ItemLookup:
        project_source_keys = sorted(set(source_keys or []))
        if project_source_keys:
            return self.item_lookup(source_keys=project_source_keys)
        return self.item_lookup()

    def item_lookup(
        self,
        source_key: str | None = None,
        *,
        source_keys: Iterable[str] | None = None,
    ) -> ItemLookup:
        if source_key:
            rows = self.connection.execute(
                """
                SELECT items.*, 0.0 AS rank
                FROM items
                WHERE source_key = ?
                """,
                (source_key,),
            ).fetchall()
        elif source_keys:
            project_source_keys = sorted(set(source_keys))
            placeholders = ", ".join("?" for _source_key in project_source_keys)
            rows = self.connection.execute(
                f"""
                SELECT items.*, 0.0 AS rank
                FROM items
                WHERE source_key IN ({placeholders})
                """,
                project_source_keys,
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT items.*, 0.0 AS rank
                FROM items
                """
            ).fetchall()
        pairs = [(str(row["item_key"]), search_result_from_row(row)) for row in rows]
        return ItemLookup(
            by_item_key={item_key: item for item_key, item in pairs},
            by_source_item_key={(item.source_key, item_key): item for item_key, item in pairs},
            by_url={item.url: item for _item_key, item in pairs},
            by_relationship_key={relationship_url_key(item.url): item for _item_key, item in pairs},
        )

    def _migrate(self) -> None:
        columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(items)").fetchall()
        }
        if "category" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        if "container" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN container TEXT NOT NULL DEFAULT ''")
        if "parent_key" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN parent_key TEXT NOT NULL DEFAULT ''")
        if "structure_type" not in columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN structure_type TEXT NOT NULL DEFAULT 'page'")

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
        item_key=str(row["item_key"]),
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
        parent_key=str(row["parent_key"]),
        structure_type=str(row["structure_type"]),
    )


@dataclass(frozen=True)
class ItemLookup:
    by_item_key: dict[str, SearchResult]
    by_source_item_key: dict[tuple[str, str], SearchResult]
    by_url: dict[str, SearchResult]
    by_relationship_key: dict[str, SearchResult]


def related_item_from_target_url(target_url: str, direction: str, lookup: ItemLookup) -> RelatedItem:
    target = lookup.by_url.get(target_url) or lookup.by_relationship_key.get(relationship_url_key(target_url))
    return RelatedItem(
        item_id=target.id if target else None,
        direction=direction,
        title=target.title if target else target_url,
        url=target.url if target else target_url,
    )


def relationship_url_key(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    match = re.search(r"/spaces/([^/]+)/pages/(\d+)(?:/|$)", path)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/spaces/{match.group(1)}/pages/{match.group(2)}"
    match = re.search(r"/browse/([A-Z][A-Z0-9]+-\d+)(?:/|$)", path, flags=re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/browse/{match.group(1).upper()}"
    match = re.search(r"/issues/([A-Z][A-Z0-9]+-\d+)(?:/|$)", path, flags=re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/browse/{match.group(1).upper()}"
    return unquote(url)
