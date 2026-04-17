# Research Workflow

## Goal

Turn a research topic into:

- expanded search keywords
- deduplicated Xiaohongshu note candidates
- detailed note content and comments
- a report that a weaker model can summarize or continue from

## Provider strategy

1. Try web search first in `auto` mode
2. Use MCP detail fetching for strong structured note detail
3. Keep MCP search available for compatibility testing, not as the only path

## Proven order

1. Check status
2. Ensure login is valid
3. Generate or accept keywords
4. Search and deduplicate
5. Score by relevance, recency, and engagement
6. Fetch details for the top notes
7. Render Markdown or JSON
8. Preserve built-in pacing, retry jitter, and risk guards

## Stability principle

The search layer changes faster than the report layer.
Keep search adapters replaceable and keep the report interface stable.
