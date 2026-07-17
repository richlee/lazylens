from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Input, Label, ListItem, ListView, Static

from lazylens.config import configured_db_path, load_sources
from lazylens.db import Index
from lazylens.indexers.adapters import IndexingError, iter_source_items
from lazylens.models import CategorySummary, RelatedItem, SearchResult, SourceConfig, SourceSummary
from lazylens.paths import default_config_path


class CategoryItem(ListItem):
    def __init__(self, category: CategorySummary | None) -> None:
        self.category_key = category.key if category else None
        label = "All" if category is None else category.name
        count = "" if category is None else f" ({category.count})"
        super().__init__(Label(f"{label}{count}", markup=False))


class ResultItem(ListItem):
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        super().__init__(Label(result.title, markup=False))


class MessageItem(ListItem):
    def __init__(self, message: str) -> None:
        super().__init__(Label(message, markup=False), disabled=True)


class RelationItem(ListItem):
    def __init__(self, item: RelatedItem) -> None:
        self.related_item = item
        label = item.title if item.item_id is not None else f"{item.title} (external)"
        super().__init__(Label(label, markup=False), disabled=item.item_id is None)


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
        Binding("1", "select_source(1)", "Source 1", show=False),
        Binding("2", "select_source(2)", "Source 2", show=False),
        Binding("3", "select_source(3)", "Source 3", show=False),
        Binding("4", "select_source(4)", "Source 4", show=False),
        Binding("5", "select_source(5)", "Source 5", show=False),
        Binding("6", "select_source(6)", "Source 6", show=False),
        Binding("7", "select_source(7)", "Source 7", show=False),
        Binding("8", "select_source(8)", "Source 8", show=False),
        Binding("9", "select_source(9)", "Source 9", show=False),
    ]
    CSS = """
    Screen {
        background: #20242c;
        color: #d7d4ca;
    }

    #sources {
        height: 1;
        padding: 0 1;
        color: #d8a24c;
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
        self.configured_sources: list[SourceConfig] = []
        self.results: list[SearchResult] = []
        self.selected_source_key: str | None = None
        self.selected_category_key: str | None = None
        self.query_text = ""
        self.history: list[SearchResult] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(Text("Sources: none indexed"), id="sources")
        yield Input(placeholder="Search", id="search")
        with Horizontal(id="body"):
            with Vertical(id="spaces"):
                yield Static(Text("Spaces"), id="spaces-title", classes="column-title")
                yield ListView(id="categories")
            with Vertical(id="center"):
                yield Static(Text("Pages"), id="pages-title", classes="column-title")
                yield ListView(id="results")
                yield Static(Text("No result selected"), id="preview")
            with Vertical(id="relations"):
                yield Static(Text("Incoming"), id="incoming-title", classes="relation-title")
                yield ListView(id="incoming")
                yield Static(Text("Outgoing"), id="outgoing-title", classes="relation-title")
                yield ListView(id="outgoing")
        yield Static(
            Text(
                "Open: Enter | Follow: Right/Space | Back: Left/Backspace | "
                "Search: / | Clear Search: c | Refresh: r | Quit: q"
            ),
            id="commands",
        )

    async def on_mount(self) -> None:
        self.configured_sources = load_sources(self.config_path)
        await self.reload_from_db()
        self.query_one("#results", ListView).focus()

    async def reload_from_db(self) -> None:
        with Index(self.db_path) as index:
            self.sources = index.sources()
        if self.sources and self.selected_source_key not in {source.key for source in self.sources}:
            self.selected_source_key = self.sources[0].key
        if not self.sources:
            self.selected_source_key = None
        self.update_sources_row()
        await self.refresh_categories()

    async def refresh_categories(self) -> None:
        with Index(self.db_path) as index:
            categories = index.categories(source_key=self.selected_source_key)
        category_list = self.query_one("#categories", ListView)
        await category_list.clear()
        if not self.sources:
            await category_list.append(MessageItem("No indexed sources"))
            category_list.index = None
            self.selected_category_key = None
            await self.refresh_results()
            return
        await category_list.extend([CategoryItem(None), *[CategoryItem(category) for category in categories]])
        category_list.index = 0
        self.selected_category_key = None
        await self.refresh_results()

    async def refresh_results(self, *, highlight_item_id: int | None = None) -> None:
        with Index(self.db_path) as index:
            self.results = index.search(
                self.query_text,
                limit=200,
                source_key=self.selected_source_key,
                category=self.selected_category_key,
            )
        result_list = self.query_one("#results", ListView)
        await result_list.clear()
        if self.results:
            await result_list.extend([ResultItem(result) for result in self.results])
            result_list.index = self.result_index(highlight_item_id)
            await self.update_current_result(self.results[result_list.index or 0])
            return
        await result_list.append(MessageItem(self.empty_results_message()))
        result_list.index = None
        await self.update_current_result(None)

    def update_sources_row(self) -> None:
        sources = self.query_one("#sources", Static)
        if not self.sources:
            label = "no sources configured" if not self.configured_sources else "no indexed sources"
            sources.update(Text(f"Sources: {label}"))
            return
        parts = []
        for index, source in enumerate(self.sources[:9], start=1):
            marker = "*" if source.key == self.selected_source_key else " "
            parts.append(f"[{index}]{marker} {source.name} ({source.count})")
        sources.update(Text("Sources: " + " | ".join(parts)))

    async def update_current_result(self, result: SearchResult | None) -> None:
        self.update_preview(result)
        await self.update_relations(result)

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
            self.history.clear()
            self.selected_category_key = event.item.category_key
            await self.refresh_results()
        elif event.list_view.id == "results" and isinstance(event.item, ResultItem):
            await self.update_current_result(event.item.result)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    async def apply_search(self, value: str) -> None:
        self.query_text = value.strip()
        self.history.clear()
        await self.refresh_results()
        self.query_one("#results", ListView).focus()

    async def action_clear_search(self) -> None:
        self.query_text = ""
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

        with Index(self.db_path) as index:
            incoming = index.incoming_links(result.id)
            outgoing = index.outgoing_links(result.id)
        if incoming:
            await incoming_list.extend([RelationItem(item) for item in incoming])
            incoming_list.index = 0
        else:
            await incoming_list.append(MessageItem("No incoming links"))
            incoming_list.index = None
        if outgoing:
            await outgoing_list.extend([RelationItem(item) for item in outgoing])
            outgoing_list.index = 0
        else:
            await outgoing_list.append(MessageItem("No outgoing links"))
            outgoing_list.index = None

    async def action_refresh_index(self) -> None:
        indexed = 0
        skipped = 0
        with Index(self.db_path) as index:
            for source in self.configured_sources:
                try:
                    index.upsert_source(source)
                    indexed += index.upsert_items(iter_source_items(source))
                except (IndexingError, RuntimeError, OSError):
                    skipped += 1
                    continue
        await self.reload_from_db()
        self.notify(f"Indexed {indexed} items" + (f"; skipped {skipped} source(s)" if skipped else ""))

    async def action_open_selected(self) -> None:
        focused = self.focused
        if isinstance(focused, Input) and focused.id == "search":
            await self.apply_search(focused.value)
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
        if open_url(result.url):
            self.notify(f"Opened {result.title}")
            return
        self.notify(f"Could not open {result.url}", severity="error")

    async def action_select_source(self, number: int) -> None:
        index = number - 1
        if index < 0 or index >= len(self.sources):
            return
        self.selected_source_key = self.sources[index].key
        self.selected_category_key = None
        self.history.clear()
        self.update_sources_row()
        await self.refresh_categories()

    async def action_follow_relation(self) -> None:
        await self.follow_selected_relation()

    async def action_back(self) -> None:
        if isinstance(self.focused, Input):
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

    async def show_context_result(self, result: SearchResult, *, push_history: bool = True) -> None:
        if push_history:
            previous = self.selected_result()
            if previous is not None:
                self.history.append(previous)
        self.results = [result]
        result_list = self.query_one("#results", ListView)
        await result_list.clear()
        await result_list.append(ResultItem(result))
        result_list.index = 0
        await self.update_current_result(result)
        result_list.focus()

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

    def empty_results_message(self) -> str:
        if not self.configured_sources:
            return "No sources configured"
        if not self.sources:
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
        if not self.sources:
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
