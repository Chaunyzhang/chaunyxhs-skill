# Chauny XHS Skill

Read this first if another model will operate the repo:

- `references/OPERATIONS-MANUAL.md`

A consolidated Xiaohongshu skill focused on three stable blocks:

1. session bootstrap
2. research workflow
3. media extraction workflow
4. transcription workflow

The design goal is not to hardcode one anti-bot path forever. Instead, the repo keeps a stable local core and treats `xiaohongshu-mcp` as an adapter that can evolve over time.

## Safety default

This aggregated repo is read-mostly by default.

The following active operations are considered high-risk and are intentionally not exposed as first-class workflows here:

- publish content
- publish video
- post comment
- reply comment
- like / unlike
- favorite / unfavorite

They remain possible in upstream MCP, but this repo does not treat them as default safe workflows because they are much easier to trigger risk controls.

## What this repo can do today

- Download and start the upstream `xiaohongshu-mcp` binaries on Windows, macOS, and Linux
- Open the QR-code login flow and reuse the resulting cookies
- Run a Xiaohongshu research workflow:
  - generate fallback keywords
  - search through the web page when MCP search is unstable
  - fetch details and comments through MCP
  - render a Markdown or JSON report
- Run a Xiaohongshu media extraction workflow:
  - open a note with a valid session
  - inspect `window.__INITIAL_STATE__`
  - prefer audio extraction
  - fall back to video only when explicitly allowed
  - download the smallest usable media file
- Run a DashScope transcription workflow:
  - accept a local audio file directly
  - accept a public audio URL directly
  - extract audio from a local video file first, then transcribe

## Why this shape is more stable

- The volatile anti-bot surface is isolated in the shared core
- The workflow scripts do not depend on one exact upstream MCP response shape
- Existing cookies and binaries from older setups are reused automatically
- The scripts print machine-readable JSON where it matters so weaker models can keep going
- The shared core applies conservative human-like pacing, retry backoff, and risk-signal detection

## Stability pacing

This repo intentionally adds light human-like pacing:

- small random waits before and after page loads
- serialized request pacing for sensitive operations
- light scroll behavior on web-search pages
- backoff jitter on retries
- risk-hint detection for pages that look like security checks or temporary blocks

This is for stability and lower operational burstiness, not for aggressive anti-detection tricks.

## Install

### 1. Install Python dependencies

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Install the MCP binaries

```bash
python scripts/setup.py
```

### 3. Login

```bash
python scripts/login.py
```

After you scan the QR code successfully, the repo reuses the saved cookies automatically.

### 4. Check status

```bash
python scripts/status.py --json
```

You want to see:

- `mcp_binary_installed: true`
- `login_binary_installed: true`
- `cookies_exist: true`
- `mcp_running: true`
- `xhs_logged_in: true`

## Research workflow

### Simple usage

```bash
python scripts/xhs_research.py --keywords "咖啡机推荐,咖啡机避雷,家用咖啡机" --quick --top 3
```

### Let the script expand from a topic

```bash
python scripts/xhs_research.py "深圳产检医院推荐" --deep
```

### Force a provider

```bash
python scripts/xhs_research.py "咖啡机推荐" --search-provider web
python scripts/xhs_research.py "咖啡机推荐" --search-provider mcp
```

Provider guidance:

- `auto`: web search first, MCP search second
- `web`: more stable when MCP search is blocked or slow
- `mcp`: useful for checking upstream compatibility after MCP updates

## Media extraction workflow

### Preferred input

Use a note URL that already carries `xsec_token`, for example a search-result note URL.

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out"
```

### Allow video fallback

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out" --allow-video-fallback
```

### Headless mode

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "./out" --headless --wait-ms 8000
```

## Transcription workflow

### Local audio file

```bash
python scripts/xhs_transcribe.py "D:/path/to/audio.mp3"
```

### Public audio URL

```bash
python scripts/xhs_transcribe.py "https://example.com/audio.wav"
```

### Local video file

```bash
python scripts/xhs_transcribe.py "D:/path/to/video.mp4"
```

For local video files, the script extracts audio locally first and then sends the local audio file to DashScope.

### Model guidance

- Public audio URLs use DashScope file transcription with `paraformer-v2`
- Local audio files use DashScope realtime recognition with `paraformer-realtime-v2`
- Local video files are converted to local audio first, then recognized with `paraformer-realtime-v2`

## Weak-model execution recipe

If a weaker model is operating this repo, it should follow this order exactly:

1. Run `python scripts/status.py --json`
2. If binaries are missing, run `python scripts/setup.py`
3. If login is missing, run `python scripts/login.py`
4. If MCP is not running, run `python scripts/start.py`
5. For research tasks, run `python scripts/xhs_research.py ...`
6. For media tasks, run `python scripts/xhs_video_pipeline.py ...`
7. For transcription tasks, run `python scripts/xhs_transcribe.py ...`
8. If research search fails, retry once with `--search-provider web`
9. If media extraction says `audio_not_found`, retry once with `--allow-video-fallback`

## File map

- `scripts/xhs_core.py`: shared stable core
- `scripts/setup.py`: binary installation
- `scripts/login.py`: QR-code login
- `scripts/start.py`: MCP server bootstrap
- `scripts/status.py`: health snapshot
- `scripts/xhs_research.py`: research workflow
- `scripts/xhs_video_pipeline.py`: media extraction workflow
- `scripts/xhs_transcribe.py`: DashScope transcription workflow

## Current limitations

- Direct `/explore/<id>` URLs are less reliable than URLs with `xsec_token`
- MCP search may time out on some machines or IP ranges
- Research detail fetching still benefits from MCP staying compatible upstream
- Risk detection is heuristic and intentionally conservative

## Long-term compatibility rule

Do not let workflow code depend on a single anti-bot path.
If upstream MCP changes, update `scripts/xhs_core.py` first and keep the workflow interfaces stable.
