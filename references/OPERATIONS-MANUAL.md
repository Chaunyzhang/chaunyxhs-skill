# Chauny XHS Skill Operations Manual

This is the practical operating manual for the aggregated Xiaohongshu skill.

It is intentionally written for weaker models and operators with low context.
Do not assume hidden knowledge. Follow the procedures in order.

## 1. Purpose

This repository provides a stable Xiaohongshu skill with four safe-by-default blocks:

1. environment and session bootstrap
2. research and analysis
3. media extraction
4. DashScope transcription

This repository is read-mostly by default.

The following active actions are intentionally not first-class workflows here because they are far more likely to trigger account risk:

- publish content
- publish video
- post comment
- reply comment
- like / unlike
- favorite / unfavorite

## 2. Core idea

Do not treat `xiaohongshu-mcp` as the only backend.

Use this logic instead:

1. keep a stable local core in this repo
2. reuse `xiaohongshu-mcp` where it is good
3. fall back when one MCP feature is unstable

Current practical split:

- login and session reuse: MCP-backed and stable enough
- note detail and comments: MCP-backed and useful
- search: use repo workflow default, which can fall back to the web path
- media extraction: page-state based
- transcription: DashScope based

## 3. First command always

Before any real work, run:

```bash
python scripts/status.py --json
python scripts/xhs_prepare.py
```

Interpretation:

- `all_ready: true`
  You can continue directly.
- `mcp_binary_installed: false`
  Run setup.
- `login_binary_installed: false`
  Run setup.
- `cookies_exist: false`
  Run login.
- `mcp_running: false`
  Run start.
- `xhs_logged_in: false`
  Run login.

Repair order:

```bash
python scripts/setup.py
python scripts/login.py
python scripts/start.py
python scripts/status.py --json
```

Do not skip the final status check.

## 4. Directory model

Primary runtime directory:

```text
~/.local/share/chaunyxhs-skill/
```

Important files:

- `bin/`:
  downloaded MCP binaries
- `cookies.json`:
  current reusable login cookies

Legacy directories that may still be reused automatically:

- `~/.local/share/xhs-research/`
- `~/.local/share/xiaohongshu-mcp/`

The repo tries to normalize storage back into `chaunyxhs-skill`.

## 5. Install requirements

Python packages:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Optional but important:

- `ffmpeg`
  Required for local video -> audio -> transcription

Verification:

```bash
python -c "import dashscope, requests"
python -c "import shutil; print(shutil.which('ffmpeg'))"
```

## 6. Login model

Login is done by:

```bash
python scripts/login.py
```

Expected behavior:

1. a Chrome window may open
2. the user scans the QR code
3. login finishes
4. cookies are copied into the stable local data directory
5. MCP is started

Important:

- If the browser window closes after login, that can be normal.
- The real truth is in `status.py --json`, not whether the login window stayed open.

## 7. Stable operating policy

This repo intentionally includes conservative human-like pacing:

- jittered waits before and after page navigation
- serialized pacing for sensitive calls
- light scrolling on search pages
- retry backoff jitter
- basic risk-hint detection

These are for stability, not for aggressive anti-detection behavior.

Do not remove them when "optimizing speed".

## 8. Research workflow

### 8.1 Preferred commands

Known keywords:

```bash
python scripts/xhs_research.py --keywords "coffee machine recommendations, coffee machine pitfalls, home coffee machine" --quick --top 3
```

Topic only:

```bash
python scripts/xhs_research.py "Shenzhen prenatal hospital recommendations" --deep
```

Force web search:

```bash
python scripts/xhs_research.py "coffee machine recommendations" --search-provider web
```

### 8.2 What the workflow actually does

1. checks MCP health and login
2. expands keywords if only a topic is provided
3. searches notes
4. deduplicates by title similarity
5. scores by relevance, recency, and engagement
6. fetches details and comments for top notes
7. renders Markdown or JSON

### 8.3 Important search reality

`search_feeds` in upstream MCP may be unstable on some machines or IP ranges.

Practical rule:

- do not assume MCP search is the source of truth
- the repo research workflow can use a web-search path and still complete the report

### 8.4 If research fails

Use this fallback ladder:

1. rerun status
2. retry once
3. force web search

```bash
python scripts/xhs_research.py "coffee machine recommendations" --search-provider web
```

4. if details fail on some notes, keep the run and inspect partial output

### 8.5 Good output signs

- report prints at least one detailed note
- comments or replies appear under `--- 热评 ---`
- a raw report file is saved under:

```text
~/Documents/XHS-Research/
```

## 9. Media extraction workflow

### 9.1 Preferred input

Prefer note URLs that already contain `xsec_token`.

Best form:

```text
https://www.xiaohongshu.com/search_result/<note_id>?xsec_token=...&xsec_source=
```

Why:

- direct `/explore/<id>` links are less reliable in practice
- the URL with `xsec_token` usually survives better through the extraction flow

### 9.2 Commands

Audio first:

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out"
```

Video fallback allowed:

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out" --allow-video-fallback
```

### 9.3 What success looks like

The output should include:

- `success: true`
- `note`
- `media.kind`
- `media.downloaded_file`
- `page.final_url`

### 9.4 Important failure meanings

`video_info_not_found`

Meaning:

- the page loaded, but the note detail was not found in `window.__INITIAL_STATE__`

Likely causes:

- bad URL
- redirect to homepage
- note inaccessible in current context
- current page is not the actual note page

Next steps:

1. use a URL with `xsec_token`
2. increase `--wait-ms`
3. try again after login check

`audio_not_found`

Meaning:

- the note loaded, but no direct audio stream was found

Next step:

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out" --allow-video-fallback
```

### 9.5 Practical reality

Many successful runs are video-fallback runs.
That is acceptable.

## 10. Transcription workflow

### 10.1 API key requirement

DashScope transcription requires:

```bash
DASHSCOPE_API_KEY
```

Without it, the script stops immediately.

Example:

```powershell
$env:DASHSCOPE_API_KEY="your_key"
```

### 10.2 Supported source types

1. local audio file
2. public audio URL
3. local video file

### 10.3 Commands

Local audio:

```bash
python scripts/xhs_transcribe.py "D:/path/to/audio.mp3"
```

Public audio URL:

```bash
python scripts/xhs_transcribe.py "https://example.com/audio.wav"
```

Local video:

```bash
python scripts/xhs_transcribe.py "D:/path/to/video.mp4"
```

### 10.4 Backend split

The script intentionally uses two DashScope paths:

- public audio URL:
  `Transcription` with `paraformer-v2`
- local audio or local video-derived audio:
  `Recognition` with `paraformer-realtime-v2`

### 10.5 Why local video must extract audio first

This repo does not assume direct remote video transcription support is stable enough.

So the local-video path is:

1. use `ffmpeg`
2. extract local WAV
3. send the local audio into DashScope

### 10.6 What success looks like

The output should include:

- `success: true`
- `provider: dashscope`
- `api_mode`
- `model`
- `result.sentences` or `result.results`

## 11. Read-only acceptance checklist

Safe flows to verify:

1. status
```bash
python scripts/status.py --json
```

2. research
```bash
python scripts/xhs_research.py --keywords "coffee machine recommendations, coffee machine pitfalls" --quick --top 1 --search-provider auto
```

3. media extraction
```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out" --headless --wait-ms 8000 --allow-video-fallback
```

4. transcription
```bash
python scripts/xhs_transcribe.py "./out/<video>.mp4"
```

## 12. Known issues and their meaning

### MCP search tool returns filter-conversion errors

Meaning:

- the upstream MCP search tool is not reliable in the current environment

Do not stop the workflow immediately.
Use the repo research workflow, because it can fall back to the web path.

### Status says logged out right after a successful run

Meaning:

- first suspect a temporary state mismatch

Action:

```bash
python scripts/status.py --json
```

If later calls still work and the next status returns `all_ready: true`, continue.

### Login window closes after QR login

Meaning:

- this can be normal

Truth source:

```bash
python scripts/status.py --json
```

### Video extraction succeeds only with fallback

Meaning:

- audio streams were not directly available

This is acceptable.

## 13. Default safety rule

Do not run these actions as default validation:

- publish
- comment
- reply
- like
- favorite

These actions are much more likely to trigger account risk controls.

## 14. If upstream MCP changes

Update order:

1. inspect `scripts/xhs_core.py`
2. adapt provider-specific logic there
3. keep workflow CLIs stable if possible
4. update docs only after the code path is confirmed

Do not scatter MCP compatibility logic into every workflow script.

## 15. Minimal operator summary

If you are in a hurry, remember only this:

1. `status.py --json`
2. repair with `setup.py`, `login.py`, `start.py`
3. research: `xhs_research.py`
4. media: `xhs_video_pipeline.py`
5. transcription: `xhs_transcribe.py`
6. prefer URLs with `xsec_token`
7. if MCP search is unstable, prefer the repo workflow over the raw MCP search tool
