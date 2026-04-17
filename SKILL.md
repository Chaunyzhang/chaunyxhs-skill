---
name: chaunyxhs-skill
description: 小红书视频媒体提取技能。用于从小红书视频笔记页面中按 F12 / 页面状态思路优先提取真实音频地址，下载最小必要媒体到本地，并输出视频信息、媒体文件路径与页面诊断结果。默认不下载完整视频，只有显式允许时才回退到视频流。适用于用户要处理小红书视频、提取真实媒体地址、下载音频、或把视频笔记做成后续可复用素材时使用。
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
- Return:
  - note info
  - local media path
  - page diagnostics

## Notes

- Prefer page-state extraction, not blob URL extraction.
- Prefer audio-first extraction to reduce bandwidth and avoid unnecessary video downloads.
- Keep browser reuse and login reuse as the default path.
- If extraction fails, inspect `window.__INITIAL_STATE__` first before trying other approaches.
