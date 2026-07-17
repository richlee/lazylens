# lazylens

[![Tests](https://github.com/richlee/lazylens/actions/workflows/tests.yml/badge.svg)](https://github.com/richlee/lazylens/actions/workflows/tests.yml)

A fast terminal lens over work knowledge.

`lazylens` builds a local SQLite/FTS index for project documents, then gives you
a keyboard-first Textual TUI for search, structure navigation, previews, and
document relationships. It currently supports local folders, Confluence Cloud,
and Jira Cloud. SharePoint is planned next.

It is useful when you want to explore work documents quickly without waiting on
browser search, full sync clients, or heavyweight document UIs.

## Screenshot

![lazylens TUI showing sources, structure, page navigation, outgoing links, and incoming links](https://raw.githubusercontent.com/richlee/lazylens/main/docs/assets/lazylens-tui.jpg)

## Features

- Local SQLite index with FTS5 search.
- Local folder indexing for Markdown, text, and other readable project files.
- Confluence Cloud indexing with page hierarchy, folders, snippets, and links.
- Jira Cloud indexing with issues, hierarchy, snippets, and linked issues.
- TUI structure navigation: source, top-level pages, folders, and child pages.
- Relationship navigation: outgoing and incoming links remain global across
  sources, so Confluence pages can lead into Jira issues and back.
- Browser/file opening from the selected page.
- Optional Nerd Font icon mode for richer terminal presentation.

## Install

From PyPI, once published:

```sh
pipx install lazylens
lazylens --help
```

From a checkout:

```sh
git clone https://github.com/richlee/lazylens.git
cd lazylens
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/lazylens --help
```

On Windows PowerShell:

```powershell
git clone https://github.com/richlee/lazylens.git
cd lazylens
py -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\lazylens --help
```

## Quick Start

Create a local demo source and open the TUI:

```sh
lazylens demo
lazylens
```

For your own local folder:

```sh
lazylens init --root ~/Documents/notes --name Notes --key notes
lazylens index
lazylens
```

Useful commands:

```sh
lazylens doctor
lazylens index
lazylens search architecture
lazylens
```

## Confluence Setup

`lazylens` uses Atlassian API-token basic auth for Confluence Cloud. Search in
the TUI remains local; the Confluence API is used only to refresh the SQLite
index.

Generate config and an env-file skeleton:

```sh
lazylens init confluence \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --space-key ARCH
```

Edit the generated env file and paste an Atlassian API token:

```sh
${EDITOR:-vi} ~/.config/lazylens/atlassian.env
source ~/.config/lazylens/atlassian.env
lazylens doctor
lazylens index personal-confluence
lazylens
```

The token should stay in `~/.config/lazylens/atlassian.env` or your shell
environment, not in `config.toml`.

For personal or non-client testing, create a small Atlassian Cloud site, add a
dedicated space, create an API token from your Atlassian account security
settings, then run `lazylens doctor` before indexing.

## Jira Setup

Jira uses the same Atlassian API-token auth pattern. The API is used only to
refresh the local SQLite index; TUI search and navigation stay local.

Generate config and append Jira entries to the Atlassian env file:

```sh
lazylens init jira \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --project-key LAZY
```

Edit the env file and paste an Atlassian API token:

```sh
${EDITOR:-vi} ~/.config/lazylens/atlassian.env
source ~/.config/lazylens/atlassian.env
lazylens doctor
lazylens index personal-jira
lazylens
```

By default, Jira config uses `project_keys` to build a JQL query. You can use a
custom `jql` value in `config.toml` when you need a narrower scope.

## Configuration

Default config path:

- macOS/Linux: `~/.config/lazylens/config.toml`
- Windows: `%APPDATA%\lazylens\config.toml`

Default database path:

- macOS/Linux: `~/.local/share/lazylens/index.sqlite3`
- Windows: `%LOCALAPPDATA%\lazylens\index.sqlite3`

Example:

```toml
database = "~/.local/share/lazylens/index.sqlite3"

[ui]
icon_style = "ascii" # ascii, unicode, or nerd

[sources."notes"]
name = "Notes"
type = "local"
root = "~/Documents/notes"

[sources."personal-confluence"]
name = "Personal Confluence"
type = "confluence"
space_keys = ["ARCH"]
page_limit = 100
max_pages = 5

[sources."personal-jira"]
name = "Personal Jira"
type = "jira"
project_keys = ["LAZY"]
description_fields = ["description"]
issue_limit = 100
max_pages = 5
```

For Confluence, `space_keys` is usually the friendliest scope to configure. You
can also configure `space_ids` if you already know them. `page_limit` controls
API page size, and `max_pages` limits how many API result pages are fetched per
space.

For Jira, `project_keys` is the simplest scope. You can set `jql` instead when
you want to index a board, issue type, component, label, or other controlled
slice. `description_fields` is an ordered list of Jira field IDs or names to
use for snippets and embedded links. The first field with content wins, so a
project using a custom field can use:

```toml
description_fields = ["description", "Description (DSP)"]
```

If needed, `base_url`, `email`, or `api_token_env` can be set on Atlassian
sources. Token values should stay out of TOML. `CONFLUENCE_BASE_URL` may be
either the Atlassian site root or the `/wiki` URL; `JIRA_BASE_URL` should be the
Atlassian site root.

## TUI Keys

- `1`-`9`: switch source
- `/`: focus search
- `c`: clear search
- `r`: refresh configured sources
- `Enter`: select structure, open pages, or drill into folders
- `Right` / `Space`: drill into page/folder children or follow selected links
- `Left` / `Backspace`: go back from a drilled view
- `q`: quit

## Icons

The TUI defaults to portable ASCII labels. For richer icons:

```toml
[ui]
icon_style = "nerd" # ascii, unicode, or nerd
```

`nerd` mode expects a Nerd Font in your terminal, for example FiraCode Nerd Font.
On macOS with Homebrew:

```sh
brew install --cask font-fira-code-nerd-font
```

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The project is intentionally local-first: remote APIs refresh the index, while
interactive search/navigation reads from SQLite.

See [docs/plan.md](docs/plan.md) for the broader direction.

## References

- [Confluence Cloud REST API v2 pages](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/)
- [Confluence Cloud REST API v2 spaces](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-space/)
- [Jira Cloud REST API issue search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
- [Atlassian basic auth for REST APIs](https://developer.atlassian.com/cloud/confluence/basic-auth-for-rest-apis/)
