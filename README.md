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

Planning scaffold only. Implementation has not started.

See [docs/plan.md](docs/plan.md).

