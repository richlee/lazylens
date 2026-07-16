# lazylens

A fast TUI lens over work knowledge.

`lazylens` is planned as a local index and terminal UI for finding work
knowledge across Confluence, SharePoint, and local project folders. It is a
separate product from `lazybooks`: the lessons carry across, but the domain,
connectors, data model, and workflows are different.

## Product Direction

The first version should be a personal work index:

- index metadata and useful snippets from configured sources
- store the index locally in SQLite with FTS5
- search and preview results quickly from a Textual TUI
- open canonical source URLs
- optionally download/cache files only when requested

Later versions can add project grouping, classification, freshness signals,
Jira links, Teams files, and richer context previews.

## Status

Phase 1 skeleton has started. The first implementation slice supports local
folder indexing into SQLite/FTS and command-line search. Confluence, SharePoint,
and the Textual TUI are planned next.

See [docs/plan.md](docs/plan.md).

## Local Folder Smoke Test

Create a config:

```toml
database = "~/.local/share/lazylens/index.sqlite3"

[sources.notes]
name = "Notes"
type = "local"
root = "~/Documents/notes"
```

Then run:

```sh
lazylens doctor
lazylens index
lazylens search architecture
```

`Enter` in the future TUI will open the canonical source URL in the browser.
For local folders, that URL defaults to the local file URI.
