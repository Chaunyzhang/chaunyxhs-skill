---
name: chaunyxhs-skill
description: 小红书视频转文案工作流技能。用于从小红书视频笔记页面中按 F12 / 页面状态思路优先提取真实音频地址，下载最小必要媒体到本地，再调用本地转写能力输出视频信息、完整原文和文案草稿。默认不下载完整视频，只有显式允许时才回退到视频流。适用于用户要处理小红书视频、把视频转文字、从页面/F12思路拿真实媒体地址、或把视频笔记做成可复用文案时使用。
---

# Chauny XHS Skill

## Quick start

1. Reuse an already logged-in Xiaohongshu browser session whenever possible.
2. Read `references/workflow.md` before changing the extraction path.
3. Run `scripts/xhs_video_pipeline.py` with a Xiaohongshu video note URL.
4. Default to audio-first extraction. Only allow video fallback when explicitly needed.
5. Return the combined JSON result.

## Command

```bash
python scripts/xhs_video_pipeline.py "<xiaohongshu_video_url>" --output-dir "<optional_output_dir>"
```

Optional:

```bash
python scripts/xhs_video_pipeline.py "<xiaohongshu_video_url>" --output-dir "<optional_output_dir>" --user-data-dir "<playwright_user_data_dir>"

# only when audio extraction is unavailable and video fallback is explicitly allowed
python scripts/xhs_video_pipeline.py "<xiaohongshu_video_url>" --output-dir "<optional_output_dir>" --allow-video-fallback
```

## What this skill does

- Extract note metadata from page state
- Find the real audio URL first, and only fall back to video when explicitly allowed
- Download the smallest necessary local media file
- Call the local transcription skill
- Return:
  - note info
  - local media path
  - transcript
  - cleaned draft copy

## Notes

- Prefer page-state extraction, not blob URL extraction.
- Prefer audio-first extraction to reduce bandwidth and avoid unnecessary video downloads.
- Keep browser reuse and login reuse as the default path.
- This skill depends on the local transcription skill already being available at:
  - `skills/local-transcribe/scripts/transcribe_local.py`
- If extraction fails, inspect `window.__INITIAL_STATE__` first before trying other approaches.
