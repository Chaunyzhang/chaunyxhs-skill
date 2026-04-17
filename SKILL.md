---
name: chaunyxhs-skill
description: 一个聚合版小红书技能，包含安装与登录、调研报告、视频媒体提取、DashScope 转写四块能力。优先复用已登录会话，优先走稳定的网页与页面状态路径，并把 xiaohongshu-mcp 作为可演进适配层而不是唯一后端。适合让弱模型按步骤执行：先检查状态，再安装，再登录，再选择调研、媒体提取或转写工作流。
---

# Chauny XHS Skill

Detailed operator manual:

- `references/OPERATIONS-MANUAL.md`

## First rule

Always do state checking before real work:

```bash
python scripts/status.py --json
```

Do not pick a workflow until the state check is fully ready.

If the result is not fully ready, repair in this order:

1. install binaries
```bash
python scripts/setup.py
```

2. login
```bash
python scripts/login.py
```

3. start the MCP service if needed
```bash
python scripts/start.py
```

## Safety default

Do not use publish, comment, reply, like, or favorite as default workflow steps.
Treat this skill as read-mostly unless the user explicitly asks for a write action and accepts the account-risk tradeoff.

## Workflow A: research report

Use this when the user wants topic research, comparisons, pain points, product analysis, or recommendation summaries from Xiaohongshu.

Preferred command:

```bash
python scripts/xhs_research.py --keywords "<kw1>,<kw2>,<kw3>" --quick --top 3
```

If the user only gives a topic:

```bash
python scripts/xhs_research.py "<topic>" --deep
```

If search is unstable, force the stable fallback:

```bash
python scripts/xhs_research.py "<topic>" --search-provider web
```

## Workflow B: video media extraction

Use this when the user wants to extract real media URLs, download audio, or fall back to downloading the video file.

Preferred command:

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "<output_dir>"
```

If audio is unavailable and the user allows video fallback:

```bash
python scripts/xhs_video_pipeline.py "<note_url>" --output-dir "<output_dir>" --allow-video-fallback
```

## Workflow C: transcription

Use this when the user wants a transcript from a local audio file, a public audio URL, or a local video file.

Preferred command:

```bash
python scripts/xhs_transcribe.py "<audio_or_video_source>"
```

Rules:

1. If the input is a local video file, extract audio locally first
2. If the input is a public audio URL, transcribe the URL directly with `paraformer-v2`
3. If the input is a local audio file, use the local-file recognition path with `paraformer-realtime-v2`

## Execution rules for weaker models

1. Do not skip `status.py`
2. Do not assume login is still valid without checking
3. For research, retry once with `--search-provider web` before declaring failure
4. For media extraction, retry once with `--allow-video-fallback` before declaring failure
5. Prefer URLs that already contain `xsec_token`
6. Prefer page-state extraction, not blob URLs
7. Return JSON or file paths exactly as produced by the scripts
8. For transcription, prefer direct local-audio input or public audio URLs
9. Do not remove the built-in pacing waits; they are part of the stability strategy

## Output expectations

- Research workflow should return a report or JSON payload
- Media workflow should return:
  - note info
  - local media path
  - page diagnostics

## Important note

This repo is intentionally built so that future `xiaohongshu-mcp` updates mostly require changes in `scripts/xhs_core.py`, not in every workflow script.
The shared core also contains conservative human-like pacing and risk guards; keep those in the core, not scattered across workflows.
