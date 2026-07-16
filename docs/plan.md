# lazylens Product Plan

## Shape

`lazylens` is a search-first, project-aware TUI for work knowledge.

It should help answer:

- Where is that document/page?
- Which source owns it?
- Is this result worth opening?
- What changed recently in this project?

## Phase 1: Personal Work Index

Goal: a local, fast, source-aware TUI for finding work documents and pages.

Scope:

- Textual TUI.
- Local SQLite database with FTS5.
- Source adapters:
  - Confluence via Atlassian API.
  - SharePoint via Microsoft Graph.
  - Local folder adapter for testing and non-cloud documents.
- Incremental indexing by source item modified time.
- Store metadata and useful snippets locally.
- Open canonical item URL from the TUI.
- Optional download/cache for files where the source supports it.

Core data:

- Source: Confluence, SharePoint, local.
- Container: space, site, library, folder.
- Item: page, document, PDF, Office file, attachment.
- Metadata: title, source, URL, owner/author, modified time, content type, path.
- Extract: first useful non-boilerplate text, search snippets, headings.
- Cache: optional downloaded file path and timestamp.

TUI:

- Source row at top.
- Search-first main workflow.
- Left pane for source containers or categories.
- Main pane for ranked results.
- Details pane with title, source, modified date, owner, path/URL, and context snippet.
- `Enter`: open URL or local cached file.
- `/`: search.
- `r`: refresh.
- `d`: download/cache if supported.
- `i` or right-arrow: details.

Indexing:

- Manual refresh first.
- Daily refresh later via launchd, cron, systemd, or a simple command.
- Avoid storing whole sensitive documents by default.
- Store enough text to make search and previews useful.
- Full-content local indexing should be opt-in per source/project.

Snippet strategy:

- Capture first meaningful 200-500 characters.
- Prefer headings and body text over boilerplate.
- Strip repeated SharePoint/Confluence chrome, nav, footers, and boilerplate where practical.
- Store matched snippets from FTS for search results.

Phase 1 success:

- Can connect to one Confluence instance and one SharePoint tenant.
- Can index a small controlled scope.
- Can search locally in under a second.
- Can open the source item from the TUI.
- Can show enough context to know whether a result is worth opening.

## Phase 2: Project Intelligence Layer

Goal: organise work knowledge around projects/workstreams, regardless of source.

Scope:

- Project config maps multiple source scopes into one project.
- Project row or project selector in the TUI.
- Cross-source search within one project.
- Document classification/taxonomy.
- Freshness and ownership signals.
- Optional richer local cache.

Example config:

```toml
[projects.nebula]
name = "Nebula"
confluence_spaces = ["NEB"]
sharepoint_sites = ["SWX Nebula"]
sharepoint_paths = ["Shared Documents/Architecture", "Shared Documents/Delivery"]

[projects.assurance]
name = "Assurance"
confluence_spaces = ["ASSURE"]
sharepoint_sites = ["Assurance"]
```

Suggested taxonomy:

- Architecture
- Decisions
- Designs
- Runbooks
- Meeting Notes
- Risks
- Security
- Delivery
- Onboarding
- Reference

Phase 2 success:

- A colleague with multiple projects can switch project context quickly.
- Search results combine Confluence and SharePoint cleanly.
- Results can be filtered by source, document type, freshness, owner, and category.
- The TUI answers "Where is that thing?" without the user remembering which platform owns it.

## Later Ideas

- Jira issue/project linkage.
- Teams channel file discovery through Microsoft Graph.
- Related document suggestions.
- Stale-document surfacing.
- Recently changed in this project view.
- Optional embeddings for semantic search, only if privacy and storage are acceptable.
- Export a project index/report.
- Web UI only if the TUI proves the model.

## Principles

- Personal tool first, enterprise search later if ever.
- Do not require full local sync.
- Do not store full sensitive content unless explicitly configured.
- Prefer canonical source URLs over copied files.
- Make source connectors replaceable.
- Keep indexing transparent and inspectable.
- The TUI should stay fast even when connectors are slow.

