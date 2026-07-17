from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Input, Label, ListItem, ListView, Static

from lazylens.config import configured_db_path, load_projects, load_sources, load_ui_config
from lazylens.db import Index
from lazylens.indexers.adapters import IndexingError
from lazylens.indexing import refresh_source
from lazylens.models import (
    CategorySummary,
    ProjectConfig,
    RelatedItem,
    SearchResult,
    SourceConfig,
    SourceSummary,
    UiConfig,
)
from lazylens.paths import default_config_path


@dataclass(frozen=True)
class IconSet:
    project: str
    space: str
    parent_page: str
    page: str
    folder: str
    link: str
    external_link: str
    source: str
    local_source: str
    confluence_source: str
    jira_source: str

    def structure(self, kind: str) -> str:
        if kind == "unparented":
            return ""
        if kind == "jira-project":
            return self.jira_source
        if kind == "epic":
            return "[E]" if self is ICON_SETS["ascii"] else "\u2b22"
        if kind == "space":
            return self.space
        if kind == "parent-page":
            return self.parent_page
        if kind == "page":
            return self.page
        return self.folder

    def source_for(self, source_type: str) -> str:
        if source_type == "local":
            return self.local_source
        if source_type == "confluence":
            return self.confluence_source
        if source_type == "jira":
            return self.jira_source
        return self.source


ICON_SETS = {
    "ascii": IconSet(
        project="",
        space="[S]",
        parent_page="[P+]",
        page="",
        folder="[F]",
        link="",
        external_link="[ext]",
        source="",
        local_source="",
        confluence_source="[C]",
        jira_source="[Ji]",
    ),
    "unicode": IconSet(
        project="",
        space="\u25a3",
        parent_page="\u25b8",
        page="\u25a1",
        folder="\u25b9",
        link="\u2192",
        external_link="\u2197",
        source="\u25c9",
        local_source="\u25c7",
        confluence_source="\u25ce",
        jira_source="\u25c6",
    ),
    "nerd": IconSet(
        project="",
        space="\uf0ac",
        parent_page="\uf07c",
        page="\uf15b",
        folder="\uf07b",
        link="\uf0c1",
        external_link="\uf08e",
        source="\uf0c2",
        local_source="\uf07b",
        confluence_source="\uf0ac",
        jira_source="\uf0ae",
    ),
}


SOURCE_SHORTCUTS = "abdefghij"


def icon_set(style: str) -> IconSet:
    return ICON_SETS.get(style, ICON_SETS["ascii"])


def result_icon(result: SearchResult, icons: IconSet, source_type: str) -> str:
    source_icon = icons.source_for(source_type)
    type_icon = item_type_icon(result, icons)
    return " ".join(part for part in [source_icon, type_icon] if part).strip()


def category_label(category: CategorySummary | None, icons: IconSet, source_type: str) -> str:
    label = "All" if category is None else category.name
    count = "" if category is None else f" ({category.count})"
    source_icon = icons.source_for(source_type)
    type_icon = "" if category is None else icons.structure(category.kind)
    if type_icon == source_icon:
        type_icon = ""
    return " ".join(part for part in [source_icon, type_icon, f"{label}{count}"] if part).strip()


def relation_label(item: RelatedItem, icons: IconSet) -> str:
    icon = icons.link if item.item_id is not None else icons.external_link
    title = item.title if item.item_id is not None else f"{item.title} (external)"
    return f"{icon}  {title}".strip() if icon else title


def item_type_icon(result: SearchResult, icons: IconSet) -> str:
    if result.content_type == "application/vnd.atlassian.jira.issue":
        issue_type = result.snippet.split("|", 1)[0].strip().lower().rstrip(".")
        if issue_type == "epic":
            return "[E]" if icons is ICON_SETS["ascii"] else "\u2b22"
        if issue_type == "story":
            return "[S]" if icons is ICON_SETS["ascii"] else "\u25aa"
        if issue_type == "bug":
            if icons is ICON_SETS["ascii"]:
                return "[B]"
            if icons is ICON_SETS["nerd"]:
                return "\uf188"
            return "!"
        return "[T]" if icons is ICON_SETS["ascii"] else "\u25ab"
    return icons.structure(result.structure_type)


class CategoryItem(ListItem):
    def __init__(self, category: CategorySummary | None, icons: IconSet, source_type: str) -> None:
        self.category_key = category.key if category else None
        self.item_id = category.item_id if category else None
        self.kind = category.kind if category else "space"
        super().__init__(Label(category_label(category, icons, source_type), markup=False))


class ResultItem(ListItem):
    def __init__(self, result: SearchResult, icons: IconSet, source_type: str) -> None:
        self.result = result
        icon = result_icon(result, icons, source_type)
        super().__init__(Label(f"{icon} {result.title}".strip(), markup=False))


class MessageItem(ListItem):
    def __init__(self, message: str) -> None:
        super().__init__(Label(message, markup=False), disabled=True)


class RelationItem(ListItem):
    def __init__(self, item: RelatedItem, icons: IconSet) -> None:
        self.related_item = item
        super().__init__(Label(relation_label(item, icons), markup=False), disabled=item.item_id is None)


class LazylensApp(App[None]):
    TITLE = "lazylens"
    BINDINGS = [
        Binding("/", "focus_search", "Search", show=False),
        Binding("c", "clear_search", "Clear Search", show=False),
        Binding("r", "refresh_index", "Refresh", show=False),
        Binding("enter", "open_selected", "Open", show=False, priority=True),
        Binding("right", "follow_relation", "Follow", show=False),
        Binding("space", "follow_relation", "Follow", show=False),
        Binding("left", "back", "Back", show=False),
        Binding("backspace", "back", "Back", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("1", "select_project(1)", "Project 1", show=False),
        Binding("2", "select_project(2)", "Project 2", show=False),
        Binding("3", "select_project(3)", "Project 3", show=False),
        Binding("4", "select_project(4)", "Project 4", show=False),
        Binding("5", "select_project(5)", "Project 5", show=False),
        Binding("6", "select_project(6)", "Project 6", show=False),
        Binding("7", "select_project(7)", "Project 7", show=False),
        Binding("8", "select_project(8)", "Project 8", show=False),
        Binding("9", "select_project(9)", "Project 9", show=False),
        Binding("a", "select_source_shortcut('a')", "Source a", show=False),
        Binding("b", "select_source_shortcut('b')", "Source b", show=False),
        Binding("d", "select_source_shortcut('d')", "Source d", show=False),
        Binding("e", "select_source_shortcut('e')", "Source e", show=False),
        Binding("f", "select_source_shortcut('f')", "Source f", show=False),
        Binding("g", "select_source_shortcut('g')", "Source g", show=False),
        Binding("h", "select_source_shortcut('h')", "Source h", show=False),
        Binding("i", "select_source_shortcut('i')", "Source i", show=False),
        Binding("j", "select_source_shortcut('j')", "Source j", show=False),
    ]
    CSS = """
    Screen {
        background: #20242c;
        color: #d7d4ca;
    }

    #projects {
        height: 1;
        padding: 0 1;
        color: #d8a24c;
    }

    #sources {
        height: 1;
        padding: 0 1;
        color: #b7c7d9;
    }

    #search {
        height: 3;
        margin: 0 1;
    }

    #body {
        height: 1fr;
    }

    #spaces {
        width: 32;
        margin: 0 0 0 1;
    }

    #categories {
        height: 1fr;
        border: solid #7a808b;
    }

    #center {
        width: 1fr;
        margin: 0 0 0 1;
    }

    #relations {
        width: 42;
        margin: 0 1 0 1;
    }

    .relation-title {
        height: 1;
        padding: 0 1;
        color: #d8a24c;
    }

    .column-title {
        height: 1;
        padding: 0 1;
        color: #d8a24c;
    }

    #results {
        height: 1fr;
        border: solid #7a808b;
    }

    #preview {
        height: 14;
        border: solid #7a808b;
        padding: 0 1 1 1;
        color: #d7d4ca;
    }

    #incoming {
        height: 1fr;
        border: solid #7a808b;
    }

    #outgoing {
        height: 1fr;
        border: solid #7a808b;
    }

    #commands {
        height: 1;
        padding: 0 1;
        color: #9ba3b1;
    }

    ListView > ListItem.--highlight {
        background: #3a3d45;
        color: #d8a24c;
    }
    """

    def __init__(self, *, config_path: str | Path | None = None, db_path: str | Path | None = None) -> None:
        super().__init__()
        self.config_path = Path(config_path).expanduser() if config_path else None
        self.db_path = Path(db_path).expanduser() if db_path else configured_db_path(config_path)
        self.display_config_path = Path(config_path).expanduser() if config_path else default_config_path()
        self.sources: list[SourceSummary] = []
        self.source_types: dict[str, str] = {}
        self.project_sources: list[SourceSummary] = []
        self.configured_sources: list[SourceConfig] = []
        self.projects: list[ProjectConfig] = []
        self.ui_config = UiConfig()
        self.icons = icon_set(self.ui_config.icon_style)
        self.results: list[SearchResult] = []
        self.selected_project_key: str | None = None
        self.selected_source_key: str | None = None
        self.selected_category_key: str | None = None
        self.pending_category_key: str | None = None
        self.query_text = ""
        self.history: list[SearchResult] = []
        self.result_stack: list[tuple[list[SearchResult], int | None]] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(Text("Projects: none configured"), id="projects")
        yield Static(Text("Sources: none indexed"), id="sources")
        yield Input(placeholder="Search", id="search")
        with Horizontal(id="body"):
            with Vertical(id="spaces"):
                yield Static(Text("Structure"), id="spaces-title", classes="column-title")
                yield ListView(id="categories")
            with Vertical(id="center"):
                yield Static(Text("Pages"), id="pages-title", classes="column-title")
                yield ListView(id="results")
                yield Static(Text("No result selected"), id="preview")
            with Vertical(id="relations"):
                yield Static(Text("Outgoing"), id="outgoing-title", classes="relation-title")
                yield ListView(id="outgoing")
                yield Static(Text("Incoming"), id="incoming-title", classes="relation-title")
                yield ListView(id="incoming")
        yield Static(
            Text(
                "Structure: Enter | Open/Drill: Enter | Links: Right/Space | Follow Link: Enter/Right | "
                "Project: 1-9 | Structure Source: a/b | Back: Left/Backspace | Search: / | "
                "Clear Search: c | Refresh: r | Quit: q"
            ),
            id="commands",
        )

    async def on_mount(self) -> None:
        self.configured_sources = load_sources(self.config_path)
        self.projects = load_projects(self.config_path, sources=self.configured_sources)
        self.ui_config = load_ui_config(self.config_path)
        self.icons = icon_set(self.ui_config.icon_style)
        await self.reload_from_db()
        self.query_one("#results", ListView).focus()

    async def reload_from_db(self) -> None:
        with Index(self.db_path) as index:
            self.sources = index.sources()
        self.source_types = {source.key: source.type for source in self.sources}
        indexed_source_keys = {source.key for source in self.sources}
        self.projects = [
            project
            for project in self.projects
            if any(source_key in indexed_source_keys for source_key in project.source_keys)
        ]
        if self.projects and self.selected_project_key not in {project.key for project in self.projects}:
            self.selected_project_key = self.projects[0].key
        if not self.projects:
            self.selected_project_key = None
        self.project_sources = [
            source
            for source in self.sources
            if source.key in set(self.selected_project_source_keys())
        ]
        if self.project_sources and self.selected_source_key not in {source.key for source in self.project_sources}:
            self.selected_source_key = self.project_sources[0].key
        if not self.project_sources:
            self.selected_source_key = None
        self.update_projects_row()
        self.update_sources_row()
        await self.refresh_categories()

    async def refresh_categories(self) -> None:
        with Index(self.db_path) as index:
            if self.selected_source_type() == "jira" and self.selected_source_key:
                categories = index.jira_structure(source_key=self.selected_source_key)
            else:
                categories = index.categories(source_key=self.selected_source_key)
                categories = [
                    *categories,
                    *index.jira_epic_structure(source_keys=self.selected_project_source_keys()),
                    *index.jira_unparented_structure(source_keys=self.selected_project_source_keys()),
                ]
        category_list = self.query_one("#categories", ListView)
        await category_list.clear()
        if not self.project_sources:
            await category_list.append(MessageItem("No indexed sources"))
            category_list.index = None
            self.selected_category_key = None
            await self.refresh_results()
            return
        category_items = [
            CategoryItem(category, self.icons, self.category_source_type(category))
            for category in categories
        ]
        if self.selected_source_type() != "jira":
            category_items = [
                CategoryItem(None, self.icons, self.selected_source_type()),
                *category_items,
            ]
        await category_list.extend(category_items)
        category_list.index = 0
        self.selected_category_key = None
        self.pending_category_key = None
        await self.refresh_results()

    async def refresh_results(self, *, highlight_item_id: int | None = None) -> None:
        with Index(self.db_path) as index:
            source_keys = self.selected_project_source_keys()
            active_source_key = self.selected_source_key if self.selected_category_key else None
            if not self.query_text and self.selected_category_key is None and active_source_key is None:
                self.results = index.project_overview(source_keys=source_keys, limit=200)
            else:
                self.results = index.search(
                    self.query_text,
                    limit=200,
                    source_key=active_source_key,
                    source_keys=source_keys if active_source_key is None else None,
                    category=self.selected_category_key,
                )
        result_list = self.query_one("#results", ListView)
        await result_list.clear()
        if self.results:
            await result_list.extend([ResultItem(result, self.icons, self.source_type(result)) for result in self.results])
            result_list.index = self.result_index(highlight_item_id)
            await self.update_current_result(self.results[result_list.index or 0])
            return
        await result_list.append(MessageItem(self.empty_results_message()))
        result_list.index = None
        await self.update_current_result(None)

    def update_projects_row(self) -> None:
        projects = self.query_one("#projects", Static)
        if not self.projects:
            label = "no projects configured" if not self.configured_sources else "no indexed projects"
            projects.update(Text(f"Projects: {label}"))
            return
        parts = []
        source_counts = {source.key: source.count for source in self.sources}
        for index, project in enumerate(self.projects[:9], start=1):
            marker = "*" if project.key == self.selected_project_key else " "
            count = sum(source_counts.get(source_key, 0) for source_key in project.source_keys)
            label = f"{self.icons.project} {project.name}".strip()
            parts.append(f"[{index}]{marker} {label} ({count})")
        projects.update(Text("Projects: " + " | ".join(parts)))

    def update_sources_row(self) -> None:
        sources = self.query_one("#sources", Static)
        if not self.project_sources:
            label = "no sources configured" if not self.configured_sources else "no indexed sources"
            sources.update(Text(f"Sources: {label}"))
            return
        parts = []
        for shortcut, source in zip(SOURCE_SHORTCUTS, self.project_sources[:len(SOURCE_SHORTCUTS)]):
            marker = "*" if source.key == self.selected_source_key else " "
            icon = self.icons.source_for(source.type)
            label = f"{icon} {source.name}".strip()
            parts.append(f"[{shortcut}]{marker} {label} ({source.count})")
        sources.update(Text("Structure Sources: " + " | ".join(parts)))

    async def update_current_result(self, result: SearchResult | None) -> None:
        self.update_preview(result)
        await self.update_relations(result)
        if result is not None:
            self.highlight_structure(result.category)

    def update_preview(self, result: SearchResult | None) -> None:
        preview = self.query_one("#preview", Static)
        if result is None:
            preview.update(Text(self.empty_preview_text()))
            return
        preview.update(preview_text(result, self.query_text))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search":
            return
        await self.apply_search(event.value)

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "categories" and isinstance(event.item, CategoryItem):
            self.pending_category_key = event.item.category_key
        elif event.list_view.id == "results" and isinstance(event.item, ResultItem):
            await self.update_current_result(event.item.result)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    async def apply_search(self, value: str) -> None:
        self.query_text = value.strip()
        self.history.clear()
        self.result_stack.clear()
        await self.refresh_results()
        self.query_one("#results", ListView).focus()

    async def action_clear_search(self) -> None:
        self.query_text = ""
        self.result_stack.clear()
        search = self.query_one("#search", Input)
        search.value = ""
        await self.refresh_results()
        self.query_one("#results", ListView).focus()

    async def update_relations(self, result: SearchResult | None) -> None:
        incoming_list = self.query_one("#incoming", ListView)
        outgoing_list = self.query_one("#outgoing", ListView)
        await incoming_list.clear()
        await outgoing_list.clear()
        if result is None:
            await incoming_list.append(MessageItem("No document selected"))
            await outgoing_list.append(MessageItem("No document selected"))
            incoming_list.index = None
            outgoing_list.index = None
            return
        if result.structure_type != "page":
            await incoming_list.append(MessageItem("No incoming links"))
            await outgoing_list.append(MessageItem("No outgoing links"))
            incoming_list.index = None
            outgoing_list.index = None
            return

        with Index(self.db_path) as index:
            source_keys = self.selected_project_source_keys()
            incoming = index.incoming_links(result.id, source_keys=source_keys)
            outgoing = index.outgoing_links(result.id, source_keys=source_keys)
        if incoming:
            await incoming_list.extend([RelationItem(item, self.icons) for item in incoming])
            incoming_list.index = 0
        else:
            await incoming_list.append(MessageItem("No incoming links"))
            incoming_list.index = None
        if outgoing:
            await outgoing_list.extend([RelationItem(item, self.icons) for item in outgoing])
            outgoing_list.index = 0
        else:
            await outgoing_list.append(MessageItem("No outgoing links"))
            outgoing_list.index = None

    async def action_refresh_index(self) -> None:
        changed = 0
        unchanged = 0
        removed = 0
        pruned = True
        skipped = 0
        with Index(self.db_path) as index:
            for source in self.configured_sources:
                try:
                    report = refresh_source(index, source)
                except (IndexingError, RuntimeError, OSError):
                    skipped += 1
                    continue
                changed += report.changed
                unchanged += report.unchanged
                removed += report.removed
                pruned = pruned and report.pruned
        await self.reload_from_db()
        prune_status = f"removed {removed}" if pruned else "prune skipped"
        message = f"Indexed {changed} changed, skipped {unchanged} unchanged, {prune_status}"
        self.notify(message + (f"; skipped {skipped} source(s)" if skipped else ""))

    async def action_open_selected(self) -> None:
        focused = self.focused
        if isinstance(focused, Input) and focused.id == "search":
            await self.apply_search(focused.value)
            return
        if focused is self.query_one("#categories", ListView):
            await self.apply_structure_filter()
            return
        if isinstance(focused, ListView) and focused.id in {"incoming", "outgoing"}:
            await self.follow_selected_relation()
            return
        if focused is not self.query_one("#results", ListView):
            return
        result = self.selected_result()
        if result is None:
            self.notify("No result selected", severity="warning")
            return
        if result.structure_type != "page":
            await self.drill_into_result(result)
            return
        if open_url(result.url):
            self.notify(f"Opened {result.title}")
            return
        self.notify(f"Could not open {result.url}", severity="error")

    async def action_select_project(self, number: int) -> None:
        index = number - 1
        if index < 0 or index >= len(self.projects):
            return
        self.selected_project_key = self.projects[index].key
        project_source_keys = set(self.selected_project_source_keys())
        self.project_sources = [source for source in self.sources if source.key in project_source_keys]
        self.selected_source_key = self.project_sources[0].key if self.project_sources else None
        self.selected_category_key = None
        self.pending_category_key = None
        self.history.clear()
        self.result_stack.clear()
        self.update_projects_row()
        self.update_sources_row()
        await self.refresh_categories()

    async def action_select_source_shortcut(self, shortcut: str) -> None:
        try:
            index = SOURCE_SHORTCUTS.index(shortcut)
        except ValueError:
            return
        if index < 0 or index >= len(self.project_sources):
            return
        self.selected_source_key = self.project_sources[index].key
        self.selected_category_key = None
        self.pending_category_key = None
        self.history.clear()
        self.result_stack.clear()
        self.update_sources_row()
        await self.refresh_categories()

    async def apply_structure_filter(self) -> None:
        category_list = self.query_one("#categories", ListView)
        item = category_list.highlighted_child
        if isinstance(item, CategoryItem) and item.item_id is not None:
            with Index(self.db_path) as index:
                result = index.item_by_id(item.item_id)
            if result is not None:
                self.history.clear()
                self.result_stack.clear()
                await self.show_children(result, push_history=False)
                return
        if (
            isinstance(item, CategoryItem)
            and item.kind == "jira-project"
            and self.selected_source_key is not None
        ):
            self.history.clear()
            self.result_stack.clear()
            await self.show_jira_epic_children(self.selected_source_key)
            return
        if isinstance(item, CategoryItem) and item.kind == "unparented" and item.category_key:
            self.history.clear()
            self.result_stack.clear()
            source_key = item.category_key.split(":", 1)[0]
            await self.show_jira_unparented_items(source_key)
            return
        self.history.clear()
        self.result_stack.clear()
        self.selected_category_key = self.pending_category_key
        await self.refresh_results()
        self.query_one("#results", ListView).focus()

    async def action_follow_relation(self) -> None:
        focused = self.focused
        if focused is self.query_one("#results", ListView):
            await self.focus_relation_links()
            return
        await self.follow_selected_relation()

    async def focus_relation_links(self) -> None:
        outgoing = self.query_one("#outgoing", ListView)
        if isinstance(outgoing.highlighted_child, RelationItem):
            outgoing.focus()
            return
        incoming = self.query_one("#incoming", ListView)
        if isinstance(incoming.highlighted_child, RelationItem):
            incoming.focus()
            return
        result = self.selected_result()
        if result is not None:
            await self.drill_into_result(result)

    async def action_back(self) -> None:
        if isinstance(self.focused, Input):
            return
        if self.result_stack:
            results, highlight_item_id = self.result_stack.pop()
            await self.replace_results(results, highlight_item_id=highlight_item_id)
            self.query_one("#results", ListView).focus()
            return
        if not self.history:
            return
        previous = self.history.pop()
        await self.refresh_results(highlight_item_id=previous.id)
        self.query_one("#results", ListView).focus()

    async def follow_selected_relation(self) -> None:
        focused = self.focused
        if not isinstance(focused, ListView) or focused.id not in {"incoming", "outgoing"}:
            return
        item = focused.highlighted_child
        if not isinstance(item, RelationItem) or item.related_item.item_id is None:
            return
        previous = self.selected_result()
        with Index(self.db_path) as index:
            result = index.item_by_id(item.related_item.item_id)
        if result is None:
            return
        if previous is not None:
            self.history.append(previous)
        await self.show_context_result(result, push_history=False)

    async def drill_into_result(self, result: SearchResult) -> None:
        with Index(self.db_path) as index:
            children = index.children(source_key=result.source_key, parent_key=result.item_key)
        if not children:
            self.notify(f"No children under {result.title}", severity="warning")
            return
        self.push_result_stack()
        await self.replace_results(children)

    async def show_children(self, result: SearchResult, *, push_history: bool = True) -> None:
        with Index(self.db_path) as index:
            children = index.children(source_key=result.source_key, parent_key=result.item_key)
        if not children:
            await self.show_context_result(result, push_history=push_history)
            return
        if push_history:
            self.push_result_stack()
        await self.replace_results(children)

    async def show_jira_epic_children(self, source_key: str) -> None:
        with Index(self.db_path) as index:
            children = index.jira_epic_children(source_key=source_key)
        await self.replace_results(children, empty_message="No Epic child tickets indexed for this Jira source")

    async def show_jira_unparented_items(self, source_key: str) -> None:
        with Index(self.db_path) as index:
            items = index.jira_unparented_items(source_key=source_key)
        await self.replace_results(items, empty_message="No unparented Jira tickets indexed for this source")

    async def show_context_result(self, result: SearchResult, *, push_history: bool = True) -> None:
        if push_history:
            self.push_result_stack()
        await self.replace_results([result], highlight_item_id=result.id)

    async def replace_results(
        self,
        results: list[SearchResult],
        *,
        highlight_item_id: int | None = None,
        empty_message: str | None = None,
    ) -> None:
        self.results = results
        result_list = self.query_one("#results", ListView)
        await result_list.clear()
        if not results:
            await result_list.append(MessageItem(empty_message or "No results"))
            result_list.index = None
            await self.update_current_result(None)
            result_list.focus()
            return
        await result_list.extend([ResultItem(result, self.icons, self.source_type(result)) for result in results])
        result_list.index = self.result_index(highlight_item_id)
        await self.update_current_result(results[result_list.index or 0])
        result_list.focus()

    def push_result_stack(self) -> None:
        self.result_stack.append((list(self.results), self.current_result_id()))

    def current_result_id(self) -> int | None:
        result = self.selected_result()
        return result.id if result is not None else None

    def selected_result(self) -> SearchResult | None:
        result_list = self.query_one("#results", ListView)
        item = result_list.highlighted_child
        if isinstance(item, ResultItem):
            return item.result
        return self.results[0] if self.results else None

    def result_index(self, item_id: int | None) -> int:
        if item_id is None:
            return 0
        for index, result in enumerate(self.results):
            if result.id == item_id:
                return index
        return 0

    def highlight_structure(self, category_key: str) -> None:
        category_list = self.query_one("#categories", ListView)
        for index, child in enumerate(category_list.children):
            if isinstance(child, CategoryItem) and child.category_key == category_key:
                category_list.index = index
                self.pending_category_key = category_key
                return

    def empty_results_message(self) -> str:
        if not self.configured_sources:
            return "No sources configured"
        if not self.project_sources:
            return "No indexed sources"
        if self.query_text:
            return "No search results"
        return "No results in this category"

    def empty_preview_text(self) -> str:
        if not self.configured_sources:
            return "\n".join(
                [
                    "No sources configured.",
                    "",
                    f"Config: {self.display_config_path}",
                    "",
                    "Run `lazylens demo` for sample data, or `lazylens init --root <folder>`.",
                ]
            )
        if not self.project_sources:
            return "\n".join(
                [
                    "Sources are configured, but nothing has been indexed yet.",
                    "",
                    "Run `lazylens index`, or press `r` to refresh local sources.",
                ]
            )
        if self.query_text:
            return f"No results for: {self.query_text}"
        return "No result selected."

    def selected_project_source_keys(self) -> tuple[str, ...]:
        for project in self.projects:
            if project.key == self.selected_project_key:
                return project.source_keys
        return tuple(source.key for source in self.sources)

    def source_type(self, result: SearchResult) -> str:
        return self.source_types.get(result.source_key, "local")

    def category_source_type(self, category: CategorySummary) -> str:
        return self.source_types.get(category.source_key or self.selected_source_key or "", "local")

    def selected_source_type(self) -> str:
        return self.source_types.get(self.selected_source_key or "", "local")


def run_tui(config_path: str | Path | None = None, db_path: str | Path | None = None) -> int:
    LazylensApp(config_path=config_path, db_path=db_path).run()
    return 0


def open_url(url: str) -> bool:
    if not url:
        return False
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
            return True
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url])
            return True
    except OSError:
        pass
    return webbrowser.open(url, new=2)


def preview_text(result: SearchResult, query: str) -> Text:
    terms = search_terms(query)
    text = Text()
    append_highlighted(text, result.title, terms, style="bold #d8a24c")
    text.append("\n")
    if result.modified_at:
        text.append(f"Modified: {format_datetime(result.modified_at)}\n", style="#9ba3b1")
    text.append(f"URL: {result.url}\n", style="#9ba3b1")
    text.append("\n")
    append_highlighted(text, result.snippet or "(no preview text available)", terms)
    return text


def append_highlighted(text: Text, value: str, terms: list[str], *, style: str | None = None) -> None:
    start = len(text.plain)
    text.append(value, style=style)
    for term in terms:
        for match in re.finditer(re.escape(term), value, flags=re.IGNORECASE):
            text.stylize("bold #f4bf75", start + match.start(), start + match.end())


def search_terms(query: str) -> list[str]:
    terms = []
    seen = set()
    for term in re.findall(r"\w+", query):
        lower_term = term.lower()
        if lower_term in seen:
            continue
        seen.add(lower_term)
        terms.append(term)
    return terms


def format_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")
