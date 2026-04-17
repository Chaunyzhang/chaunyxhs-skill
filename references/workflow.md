# Workflow

## Goal

Turn a Xiaohongshu video note into:
- video metadata
- downloaded local media (audio first, video only as fallback)
- page diagnostics

## Proven flow

1. Reuse an already logged-in Xiaohongshu browser context when possible.
2. Open the note page.
3. Read `window.__INITIAL_STATE__`.
4. Locate media fields in page state. Prefer audio first, then fallback to video only if explicitly allowed:
   - audio candidates from fields like `note.noteDetailMap.<noteId>.note.video.media.audioStream` / related audio objects
   - video fallback from `note.noteDetailMap.<noteId>.note.video.media.stream.h264[].masterUrl`
5. Choose the best audio candidate first. Only choose a video stream when audio is unavailable and fallback is explicitly enabled.
6. Download the smallest necessary media URL.
7. Return combined JSON.

## Why this works

The browser player often exposes only a `blob:` URL.
The real downloadable media URL lives in the page state / player config.

So the correct extraction order is:
- page state first
- player config second
- blob URL never as the primary source

For text-first workflows, the correct media preference is:
- audio first
- video only as fallback

## Scope

This skill currently proves the flow on Xiaohongshu only.
The same general pattern can later be ported to Bilibili and Douyin, but field names differ by platform.
