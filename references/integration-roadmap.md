# Integration Roadmap

## Current working blocks

1. Session bootstrap
   - Reuse cookies exported by the local `xiaohongshu-mcp` or older `xhs-research` flow.
   - Keep browser reuse as the first choice.
   - Normalize storage into `~/.local/share/chaunyxhs-skill`.

2. Media extraction
   - Open a note page with a valid session.
   - Prefer page-state extraction from `window.__INITIAL_STATE__`.
   - Prefer audio candidates first.
   - Fall back to video streams only when explicitly allowed.

3. Research workflow
   - Search through the web layer when MCP search is unstable.
   - Fetch note details through MCP when available.
   - Keep report rendering independent from the search adapter.

4. Diagnostics
   - Return the final URL after redirects.
   - Return the page title.
   - Return cookie visibility hints so failures are easier to debug on another machine.

## Default policy

Keep the aggregated skill read-mostly by default.
Do not promote publishing or social interactions into default workflows unless there is a dedicated safety gate for them.

## What is still not fully merged

This repository now contains the stable shared core, the research workflow,
and the media-extraction workflow.

What is still external:

- upstream `xiaohongshu-mcp`
- any future posting or monitoring workflows that may be split into their own repos today

## Recommended future merge shape

1. Stable core
   - session/cookies
   - URL normalization
   - note id and xsec token handling
   - provider selection

2. Providers
   - web provider
   - MCP provider

3. Workflows
   - research report
   - media extraction
   - future posting / monitoring flows

## MCP compatibility principle

Treat `xiaohongshu-mcp` as an adapter, not the only backend.
That keeps the skill usable when anti-bot changes break one path, while still making it easy to follow upstream MCP updates later.
