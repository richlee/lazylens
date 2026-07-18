# lazylens

[![Tests](https://github.com/richlee/lazylens/actions/workflows/tests.yml/badge.svg)](https://github.com/richlee/lazylens/actions/workflows/tests.yml)

A fast terminal lens over work knowledge.

`lazylens` builds a local SQLite/FTS index over work knowledge, then gives you
a keyboard-first Textual TUI for search, source structure, previews, and
cross-linked document relationships.

The intended first use case is an Atlassian project: Confluence pages provide
the design/document structure, Jira issues provide delivery detail, and
relationships let you navigate between them without losing the source context.
Local folders are also supported for notes, demos, and non-cloud documents.
SharePoint is planned next.

## Screenshot

![lazylens TUI showing sources, structure, page navigation, outgoing links, and incoming links](https://raw.githubusercontent.com/richlee/lazylens/main/docs/assets/lazylens-tui.jpg)

## Features

- Local SQLite index with FTS5 search.
- Confluence Cloud indexing with page hierarchy, folders, snippets, and links.
- Jira Cloud indexing with issues, hierarchy, snippets, and linked issues.
- Cross-source relationship navigation: Confluence pages can lead into Jira
  Epics/Stories/Bugs and Jira issues can lead back to Confluence LLDs/KDDs.
- Local folder indexing for Markdown, text, and other readable project files.
- TUI project/source navigation with scoped `All` views, Confluence/page
  structure, Jira roots, Epics, and Unparented tickets.
- Browser/file opening from the selected page.
- About popup with version, commit, credit, and tech stack.
- Optional Nerd Font icon mode for richer terminal presentation.

## Install

From PyPI:

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

For a real Atlassian project, configure Confluence and Jira as separate sources
that share the same Atlassian env file:

```sh
lazylens init confluence \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --space-key ARCH

lazylens init jira \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --project-key ARCH
```

Edit the generated env file and paste your Atlassian API token:

```sh
${EDITOR:-vi} ~/.config/lazylens/atlassian.env
source ~/.config/lazylens/atlassian.env
lazylens doctor
lazylens index
lazylens
```

Inside the TUI, projects and sources are selected separately. A project selection
shows the combined project structure: `All`, Confluence/local document
structure, Jira roots, Jira Epics, and Unparented Jira tickets. A source
selection scopes both Structure and Pages to that source. The outgoing/incoming
relationship panes can still cross between Confluence and Jira inside the
selected project.

For a no-credentials demo:

```sh
lazylens demo
lazylens
```

If your config has explicit `[projects]`, `lazylens demo` also adds a small
`Demo` project so the demo source is visible in the TUI.

Useful commands:

```sh
lazylens doctor
lazylens index
lazylens search architecture
lazylens
```

## Atlassian Setup

`lazylens` uses Atlassian API-token basic auth for Confluence Cloud and Jira
Cloud. Remote APIs are used only to refresh the local SQLite index; TUI search
and navigation read from local data.

Credentials belong in:

```sh
~/.config/lazylens/atlassian.env
```

Source scope belongs in:

```sh
~/.config/lazylens/config.toml
```

Token values should stay out of `config.toml` and out of source control.
Atlassian site URLs and account emails can live on each source in
`config.toml`; this lets one LazyLens config index multiple Atlassian sites or
accounts in the same run.

For personal or non-client testing, create a small Atlassian Cloud site, add a
Confluence space and Jira project, create an API token from your Atlassian
account security settings, then run `lazylens doctor` before indexing.

### Confluence Source

Generate or append a Confluence source:

```sh
lazylens init confluence \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --space-key ARCH
```

Then:

```sh
source ~/.config/lazylens/atlassian.env
lazylens index personal-confluence
```

### Jira Source

Generate or append a Jira source:

```sh
lazylens init jira \
  --base-url "https://example.atlassian.net" \
  --email "you@example.com" \
  --project-key LAZY
```

Then:

```sh
source ~/.config/lazylens/atlassian.env
lazylens index personal-jira
```

By default, Jira config uses `project_keys` to build a JQL query. You can use a
custom `jql` value in `config.toml` when you need a narrower scope.

Jira snippets and embedded links come from the first configured description
field that contains content. This supports projects that use custom fields such
as `Description (DSP)` instead of the standard Jira `description` field.

### Local Folder Source

Local folders are useful for notes, exported documents, or demos:

```sh
lazylens init --root ~/Documents/notes --name Notes --key notes
lazylens index notes
```

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
base_url = "https://example.atlassian.net"
email = "you@example.com"
space_keys = ["ARCH"]
page_limit = 100
max_pages = 5

[sources."personal-jira"]
name = "Personal Jira"
type = "jira"
base_url = "https://example.atlassian.net"
email = "you@example.com"
project_keys = ["LAZY"]
description_fields = ["description"]
issue_limit = 100
max_pages = 5

[projects.arch]
name = "Architecture"
sources = ["personal-confluence", "personal-jira"]
```

Projects group separately named sources into one working context. Selecting a
project with `1`-`9` shows the whole project: `All` means all project sources,
Structure includes Confluence/local document categories plus Jira roots, Epics,
and Unparented entries, and relationship navigation can cross source boundaries.

Selecting a source with `a`, `b`, `d`, etc. switches to source mode: `All` means
that source only, Structure is limited to that source, and Pages resets to that
source's overview. Selecting the project again returns to the full project view.

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

For Atlassian sources, prefer setting `base_url`, `email`, and `api_token_env`
on each source. Token values should stay out of TOML and should be exported
from `~/.config/lazylens/atlassian.env`. `CONFLUENCE_BASE_URL`,
`CONFLUENCE_EMAIL`, `JIRA_BASE_URL`, and `JIRA_EMAIL` are still supported as
fallbacks for simple one-account setups. `CONFLUENCE_BASE_URL` may be either
the Atlassian site root or the `/wiki` URL; `JIRA_BASE_URL` should be the
Atlassian site root.

For multiple Atlassian accounts or tenants, give each source its own token
environment variable:

```toml
[sources."client-a-confluence"]
name = "Client A Confluence"
type = "confluence"
base_url = "https://client-a.atlassian.net"
email = "a@example.com"
api_token_env = "CLIENT_A_CONFLUENCE_TOKEN"
space_keys = ["ARCH"]

[sources."client-b-jira"]
name = "Client B Jira"
type = "jira"
base_url = "https://client-b.atlassian.net"
email = "b@example.com"
api_token_env = "CLIENT_B_JIRA_TOKEN"
project_keys = ["DEL"]
```

Then export only the secrets:

```sh
export CLIENT_A_CONFLUENCE_TOKEN="..."
export CLIENT_B_JIRA_TOKEN="..."
lazylens index
```

## Corporate Network TLS

Some corporate networks inspect HTTPS traffic and re-sign certificates with an
internal root certificate. If `lazylens index` can read local/demo sources but
Confluence or Jira fail with:

```text
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

configure Python to trust a complete CA bundle. `lazylens` uses Python's
standard `urllib` for Atlassian requests, so the important runtime variable is
`SSL_CERT_FILE`. `REQUESTS_CA_BUNDLE` is useful for tools that use the
`requests` library, but it is not enough by itself for LazyLens.

Do not point `SSL_CERT_FILE` at only the corporate root certificate. That
replaces Python's public CA bundle and can break normal public HTTPS trust.
Instead, create a combined PEM bundle containing the normal public roots plus
the corporate root/intermediate certificate, then export both variables:

```sh
export SSL_CERT_FILE="$HOME/.certs/python-public-plus-company.pem"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
source ~/.config/lazylens/atlassian.env
lazylens index
```

To confirm which Python executable `pipx` is using for LazyLens:

```sh
command -v lazylens
head -1 "$(command -v lazylens)"
```

Use that interpreter when testing TLS, because it is the one that runs
LazyLens:

```sh
/path/from/shebang/python -c "import ssl, urllib.request; print(ssl.get_default_verify_paths()); print(urllib.request.urlopen('https://example.atlassian.net', timeout=10).status)"
```

## TUI Keys

- `1`-`9`: select project
- `a`, `b`, `d`...: select source within the current project
- `/`: focus search
- `c`: clear search
- `r`: refresh configured sources
- `Enter`: select structure, open pages, or drill into folders
- `Right` / `Space`: drill into page/folder children or follow selected links
- `Left` / `Backspace`: go back from a drilled view
- `?`: About
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
