from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def extract_note_id(url: str) -> str:
    for marker in ('/explore/', '/discovery/item/'):
        if marker in url:
            return url.split(marker, 1)[1].split('?', 1)[0].split('/', 1)[0]
    return ''


def extract_video_info_from_page(url: str, user_data_dir: str | None = None, cdp_url: str | None = None) -> dict:
    with sync_playwright() as p:
        browser = None
        context = None
        page = None
        created_temp_page = False

        if cdp_url:
            browser = p.chromium.connect_over_cdp(cdp_url)
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
            else:
                context = browser.new_context()
            matching = [pg for pg in context.pages if 'xiaohongshu.com' in (pg.url or '')]
            if matching:
                page = matching[0]
            elif context.pages:
                page = context.pages[0]
            else:
                page = context.new_page()
                created_temp_page = True
        else:
            kwargs = {
                'headless': False,
            }
            if user_data_dir:
                context = p.chromium.launch_persistent_context(user_data_dir=user_data_dir, **kwargs)
                page = context.new_page()
                created_temp_page = True
            else:
                browser = p.chromium.launch(**kwargs)
                context = browser.new_context()
                page = context.new_page()
                created_temp_page = True

        if page.url != url:
            page.goto(url, wait_until='domcontentloaded', timeout=120000)
        page.wait_for_timeout(5000)

        data = page.evaluate(
            """() => {
                const state = window.__INITIAL_STATE__ || {};
                const noteId = location.pathname.includes('/explore/')
                    ? location.pathname.split('/explore/')[1]?.split('?')[0]
                    : location.pathname.includes('/discovery/item/')
                        ? location.pathname.split('/discovery/item/')[1]?.split('?')[0]
                        : '';
                const detail = state?.note?.noteDetailMap?.[noteId]?.note || null;
                if (!detail) {
                    return {
                        ok: false,
                        noteId,
                        keys: Object.keys(state || {})
                    };
                }
                const streams = detail?.video?.media?.stream?.h264 || [];
                const audioInfo = detail?.video?.media?.audioStream || detail?.video?.media?.audio || detail?.video?.audio || null;
                const audioCandidates = [];

                const pushCandidate = (url, meta = {}) => {
                    if (!url || typeof url !== 'string') return;
                    audioCandidates.push({
                        url,
                        avgBitrate: meta.avgBitrate || 0,
                        format: meta.format || '',
                        qualityType: meta.qualityType || '',
                        size: meta.size || 0,
                    });
                };

                if (Array.isArray(audioInfo)) {
                    audioInfo.forEach(item => {
                        pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {});
                    });
                } else if (audioInfo && typeof audioInfo === 'object') {
                    pushCandidate(audioInfo.masterUrl || audioInfo.backupUrl || audioInfo.url || '', audioInfo);
                    if (Array.isArray(audioInfo.streams)) {
                        audioInfo.streams.forEach(item => {
                            pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {});
                        });
                    }
                    if (Array.isArray(audioInfo.list)) {
                        audioInfo.list.forEach(item => {
                            pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {});
                        });
                    }
                }

                return {
                    ok: true,
                    noteId,
                    title: detail.title || '',
                    desc: detail.desc || '',
                    author: detail.user?.nickname || '',
                    likes: detail.interactInfo?.likedCount || '',
                    collects: detail.interactInfo?.collectedCount || '',
                    comments: detail.interactInfo?.commentCount || '',
                    duration: detail.video?.media?.duration || 0,
                    streams: streams.map((s, i) => ({
                        index: i,
                        masterUrl: s.masterUrl || '',
                        avgBitrate: s.avgBitrate || 0,
                        width: s.width || 0,
                        height: s.height || 0,
                    })),
                    audio_candidates: audioCandidates,
                };
            }"""
        )

        if cdp_url:
            if created_temp_page and page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
        else:
            context.close()
        return data


def pick_best_stream(streams: list[dict]) -> dict | None:
    if not streams:
        return None
    return sorted(streams, key=lambda s: (s.get('avgBitrate', 0), s.get('width', 0) * s.get('height', 0)), reverse=True)[0]


def download_video(url: str, output_path: Path) -> Path:
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with output_path.open('wb') as f:
        for chunk in r.iter_content(1024 * 256):
            if chunk:
                f.write(chunk)
    return output_path


def run_local_transcribe(media_path: Path, title: str) -> dict:
    script = Path(r"C:\Users\ye302\.openclaw\workspace-klmk\skills\local-transcribe\scripts\transcribe_local.py")
    cmd = [sys.executable, str(script), str(media_path), '--title', title, '--output-format', 'json']
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--output-dir', default=str(Path.cwd()))
    parser.add_argument('--user-data-dir', default='')
    parser.add_argument('--cdp-url', default='')
    parser.add_argument('--allow-video-fallback', action='store_true')
    args = parser.parse_args()

    info = extract_video_info_from_page(args.url, args.user_data_dir or None, args.cdp_url or None)
    if not info.get('ok'):
        print(json.dumps({'success': False, 'error': 'video_info_not_found', 'detail': info}, ensure_ascii=False, indent=2))
        return 1

    audio_candidates = info.get('audio_candidates', []) or []
    best_audio = sorted(audio_candidates, key=lambda a: (a.get('avgBitrate', 0), a.get('size', 0)), reverse=True)[0] if audio_candidates else None
    stream = pick_best_stream(info.get('streams', []))

    note_id = info.get('noteId') or extract_note_id(args.url) or 'xhs-video'
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    media_kind = ''
    media_path = None
    media_meta = {}

    if best_audio and best_audio.get('url'):
        media_kind = 'audio'
        media_path = output_dir / f'{note_id}.m4a'
        download_video(best_audio['url'], media_path)
        media_meta = {
            'downloaded_file': str(media_path),
            'audio_url': best_audio.get('url', ''),
            'avg_bitrate': best_audio.get('avgBitrate', 0),
            'format': best_audio.get('format', ''),
            'quality_type': best_audio.get('qualityType', ''),
            'size': best_audio.get('size', 0),
        }
    elif args.allow_video_fallback and stream and stream.get('masterUrl'):
        media_kind = 'video'
        media_path = output_dir / f'{note_id}.mp4'
        download_video(stream['masterUrl'], media_path)
        media_meta = {
            'downloaded_file': str(media_path),
            'master_url': stream.get('masterUrl', ''),
            'avg_bitrate': stream.get('avgBitrate', 0),
            'width': stream.get('width', 0),
            'height': stream.get('height', 0),
        }
    else:
        print(json.dumps({'success': False, 'error': 'audio_not_found', 'detail': {'audio_candidates': audio_candidates, 'video_available': bool(stream)}}, ensure_ascii=False, indent=2))
        return 1

    transcribed = run_local_transcribe(media_path, info.get('title') or '小红书视频转文案')

    payload = {
        'success': True,
        'source_url': args.url,
        'note': {
            'note_id': note_id,
            'title': info.get('title', ''),
            'desc': info.get('desc', ''),
            'author': info.get('author', ''),
            'likes': info.get('likes', ''),
            'collects': info.get('collects', ''),
            'comments': info.get('comments', ''),
            'duration': info.get('duration', 0),
        },
        'media': {
            'kind': media_kind,
            **media_meta,
        },
        'transcription': transcribed,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
