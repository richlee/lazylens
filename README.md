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
folder indexing into SQLite/FTS, command-line search, and an early Textual TUI.
Confluence and SharePoint connectors are planned next.

See [docs/plan.md](docs/plan.md).

## Local Folder Smoke Test

The quickest demo path creates a small local source, writes config, indexes it,
and leaves the TUI ready to run:

```sh
lazylens demo
lazylens
```

For your own local folder, create a starter config:

```sh
lazylens init --root ~/Documents/notes --name Notes --key notes
lazylens index
lazylens
```

The generated config is a small TOML file:

```toml
database = "~/.local/share/lazylens/index.sqlite3"

[sources.notes]
name = "Notes"
type = "local"
root = "~/Documents/notes"
```

Useful commands:

```sh
lazylens doctor
lazylens index
lazylens search architecture
lazylens
```

The TUI currently supports the local index demo flow:

- `1`-`9`: switch source
- `/`: focus search
- `c`: clear search
- `r`: refresh configured local sources
- `Enter`: open the highlighted result URL in the browser
- `q`: quit

For local folders, the canonical URL defaults to the local file URI.

## Source Config

`lazylens` currently supports local folders and an early Confluence Cloud page
indexer. Confluence indexing uses Atlassian API-token basic auth, but the token
should stay in an environment variable rather than the config file.

```toml
database = "~/.local/share/lazylens/index.sqlite3"

[sources."notes"]
name = "Notes"
type = "local"
root = "~/Documents/notes"

[sources."work-confluence"]
name = "Work Confluence"
type = "confluence"
base_url = "https://example.atlassian.net/wiki"
email = "you@example.com"
api_token_env = "ATLASSIAN_API_TOKEN"
space_keys = ["ARCH"]
page_limit = 100
max_pages = 5
```

Then:

```sh
export ATLASSIAN_API_TOKEN="..."
lazylens doctor
lazylens index work-confluence
lazylens
```

For Confluence, `space_keys` is usually the friendliest scope to configure.
`page_limit` controls API page size, and `max_pages` limits how much is fetched
per space during this early connector phase.

References:

- [Confluence Cloud REST API v2 pages](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/)
- [Confluence Cloud REST API v2 spaces](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-space/)
- [Atlassian basic auth for REST APIs](https://developer.atlassian.com/cloud/confluence/basic-auth-for-rest-apis/)
