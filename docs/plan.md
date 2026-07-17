# lazylens Product Plan

## Shape

`lazylens` is a search-first, project-aware TUI for work knowledge.

It should help answer:

- Where is that document/page?
- Which source owns it?
- Is this result worth opening?
- What is connected to it?
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
- Links: outgoing document links, resolved internal links where possible, and unresolved external URLs.
- Cache: optional downloaded file path and timestamp.

TUI:

- Source row at top.
- Search-first main workflow.
- Left pane for navigation views:
  - Source Structure: Confluence spaces/page trees, SharePoint sites/libraries/folders, local folders.
  - Intelligent Tags: generated categories based on title, metadata, path, and optionally preview text.
  - Later: All, Recent, Stale, Owner, and Type views.
- Main pane for ranked results, initially as a title list.
- Persistent preview/details panel inside the right side of the layout.
- Preview panel updates as the highlighted result changes.
- Preview panel shows title, source, modified date, owner, path/URL, and context snippet.
- Related-docs view:
  - First version can be a third vertical panel listing linked/related documents for the highlighted item.
  - Split related documents into inbound links and outbound links when there is enough screen width.
  - The panel should be keyboard navigable; `Enter` opens the related document URL.
  - It may later become a horizontally expanding series of relationship panes, similar to column-based directory navigation, where moving through one list reveals the next level of related documents.
- Search result rows should be backed by title, preview text, and metadata, even where the first TUI only renders the title.
- `Enter`: open the canonical source URL in the browser.
- `/`: search.
- `r`: refresh.
- `g`: open graph view.
- `d`: download/cache if supported.
- `i` or right-arrow: details.

Result model:

- Title: concise display label from source metadata or extracted heading.
- Preview: a useful 200-500 character chunk from the page/document, not full stored content by default.
- Metadata: source, category, container/path, URL, owner/author, modified time, content type.
- Category: initially source-derived from folders, spaces, sites, or page hierarchy.
- Intelligent category: later generated from content and metadata, similar to the lazybooks taxonomy work.

Indexing:

- Manual refresh first.
- Daily refresh later via launchd, cron, systemd, or a simple command.
- Avoid storing whole sensitive documents by default.
- Store enough text to make search and previews useful.
- Extract and store links between indexed items:
  - Confluence page links and web links from storage/body HTML.
  - SharePoint/Office links where exposed by Microsoft Graph or extractable from previews.
  - Local Markdown links for local folder sources.
  - Resolve target URLs to indexed item IDs where possible; keep unresolved URLs as edges too.
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
- Can open the source item in a browser from the TUI.
- Can show enough context to know whether a result is worth opening.
- Can show related documents for the highlighted result when links are available.

## Navigation Model

The primary workflow is:

1. Fast exploration of the document landscape for orientation and discovery.
2. Local search/filtering over titles, metadata, and a few hundred useful preview characters per document.
3. Navigation to a specific canonical source document.
4. Navigation from that document to related documents.

Related navigation should support both:

- A TUI related-docs panel for fast keyboard-driven use.
- A generated local browser graph for visual exploration.

Relationship column view:

- Start from the current search/category results.
- Selecting a document opens a relationship column to the right.
- Each relationship column is split vertically:
  - Top: documents that link to the selected document.
  - Bottom: documents the selected document links out to.
- Selecting a related document opens another relationship column to the right using the same inbound/outbound split.
- Limit rightward expansion, probably to 3-4 relationship columns.
- When the limit is reached, shift older columns left or replace the rightmost column rather than letting the layout become unreadable.
- This should behave like a document-oriented column file manager: fast keyboard movement, clear context, and explicit link direction.
- This is an advanced evolution of the simpler third-panel related-docs view, not required for the first link-tracking implementation.

Graph view:

- Generate a local HTML graph from the SQLite index.
- Use a client-side graph library such as D3 or Cytoscape.
- Nodes represent indexed documents/pages.
- Edges represent extracted links or inferred relationships.
- Clicking a node opens the canonical source URL.
- Keep the graph local/private; do not require a hosted service.
- Start with bounded neighbourhood graphs around the current item before attempting a whole-project graph.

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
[projects.platform-modernisation]
name = "Platform Modernisation"
confluence_spaces = ["PLAT"]
sharepoint_sites = ["Platform Modernisation"]
sharepoint_paths = ["Shared Documents/Architecture", "Shared Documents/Delivery"]

[projects.customer-portal]
name = "Customer Portal"
confluence_spaces = ["PORTAL"]
sharepoint_sites = ["Customer Portal"]
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
- Related document suggestions beyond explicit links.
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
