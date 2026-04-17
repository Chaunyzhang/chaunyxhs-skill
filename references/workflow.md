# Media Workflow

## Goal

Turn a Xiaohongshu video note into:

- note metadata
- downloaded local media
- page diagnostics

## Proven order

1. Reuse an already logged-in session
2. Normalize the note URL
3. Open the page
4. Read `window.__INITIAL_STATE__`
5. Prefer audio candidates first
6. Fall back to video only when explicitly allowed
7. Download the smallest useful media asset
8. Return combined JSON

## Why this is preferred

- The visible player may expose only `blob:` URLs
- The stable downloadable media URLs live in page state
- Audio-first reduces bandwidth and failure surface

## Input recommendation

Prefer note URLs that already contain `xsec_token`.
