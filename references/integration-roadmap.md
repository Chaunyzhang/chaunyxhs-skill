# Integration Roadmap

## Current working blocks

1. Session bootstrap
   - Reuse cookies exported by the local `xiaohongshu-mcp` or `xhs-research` flow.
   - Keep browser reuse as the first choice.

2. Media extraction
   - Open a note page with a valid session.
   - Prefer page-state extraction from `window.__INITIAL_STATE__`.
   - Prefer audio candidates first.
   - Fall back to video streams only when explicitly allowed.

3. Diagnostics
   - Return the final URL after redirects.
   - Return the page title.
   - Return cookie visibility hints so failures are easier to debug on another machine.

## Why this repo is still only one block

This repository currently stores the media-extraction workflow only.
The research workflow and the MCP bootstrap workflow still live in separate repos.

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
