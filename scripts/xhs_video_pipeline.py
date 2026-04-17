from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def extract_note_id(url: str) -> str:
    for marker in ("/explore/", "/discovery/item/"):
        if marker in url:
            return url.split(marker, 1)[1].split("?", 1)[0].split("/", 1)[0]
    return ""


def default_cookies_path() -> str:
    home = Path.home()
    candidates = [
        home / ".local" / "share" / "xhs-research" / "cookies.json",
        home / ".local" / "share" / "xiaohongshu-mcp" / "cookies.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def load_cookies(context, cookies_path: str | None) -> int:
    if not cookies_path:
        return 0
    path = Path(cookies_path).expanduser()
    if not path.is_file():
        return 0

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    if not isinstance(raw, list):
        return 0

    cookies = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cookie = {
            "name": item.get("name", ""),
            "value": item.get("value", ""),
            "domain": item.get("domain", ""),
            "path": item.get("path", "/"),
        }
        if not cookie["name"] or not cookie["domain"]:
            continue
        if isinstance(item.get("expires"), (int, float)) and item["expires"] > 0:
            cookie["expires"] = item["expires"]
        if "httpOnly" in item:
            cookie["httpOnly"] = bool(item["httpOnly"])
        if "secure" in item:
            cookie["secure"] = bool(item["secure"])
        if item.get("sameSite") in {"Strict", "Lax", "None"}:
            cookie["sameSite"] = item["sameSite"]
        cookies.append(cookie)

    if not cookies:
        return 0

    context.add_cookies(cookies)
    return len(cookies)


def extract_video_info_from_page(
    url: str,
    user_data_dir: str | None = None,
    cdp_url: str | None = None,
    cookies_path: str | None = None,
    headless: bool = False,
    wait_ms: int = 5000,
) -> dict:
    with sync_playwright() as p:
        browser = None
        context = None
        page = None
        created_temp_page = False

        if cdp_url:
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            matches = [candidate for candidate in context.pages if "xiaohongshu.com" in (candidate.url or "")]
            page = matches[0] if matches else (context.pages[0] if context.pages else context.new_page())
            created_temp_page = not bool(matches or context.pages[:-1])
        else:
            launch_args = {"headless": headless}
            if user_data_dir:
                context = p.chromium.launch_persistent_context(user_data_dir=user_data_dir, **launch_args)
            else:
                browser = p.chromium.launch(**launch_args)
                context = browser.new_context()
                load_cookies(context, cookies_path)
            page = context.new_page()
            created_temp_page = True

        if page.url != url:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(wait_ms)

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
                        keys: Object.keys(state || {}),
                        finalUrl: location.href,
                        pageTitle: document.title || '',
                        documentCookieLength: (document.cookie || '').length,
                    };
                }

                const streams = detail?.video?.media?.stream?.h264 || [];
                const audioInfo = detail?.video?.media?.audioStream || detail?.video?.media?.audio || detail?.video?.audio || null;
                const audioCandidates = [];

                const pushCandidate = (candidateUrl, meta = {}) => {
                    if (!candidateUrl || typeof candidateUrl !== 'string') return;
                    audioCandidates.push({
                        url: candidateUrl,
                        avgBitrate: meta.avgBitrate || 0,
                        format: meta.format || '',
                        qualityType: meta.qualityType || '',
                        size: meta.size || 0,
                    });
                };

                if (Array.isArray(audioInfo)) {
                    audioInfo.forEach(item => pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {}));
                } else if (audioInfo && typeof audioInfo === 'object') {
                    pushCandidate(audioInfo.masterUrl || audioInfo.backupUrl || audioInfo.url || '', audioInfo);
                    if (Array.isArray(audioInfo.streams)) {
                        audioInfo.streams.forEach(item => pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {}));
                    }
                    if (Array.isArray(audioInfo.list)) {
                        audioInfo.list.forEach(item => pushCandidate(item?.masterUrl || item?.backupUrl || item?.url || '', item || {}));
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
                    streams: streams.map((stream, index) => ({
                        index,
                        masterUrl: stream.masterUrl || '',
                        avgBitrate: stream.avgBitrate || 0,
                        width: stream.width || 0,
                        height: stream.height || 0,
                    })),
                    audio_candidates: audioCandidates,
                    final_url: location.href,
                    page_title: document.title || '',
                    document_cookie_length: (document.cookie || '').length,
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
    return sorted(
        streams,
        key=lambda stream: (stream.get("avgBitrate", 0), stream.get("width", 0) * stream.get("height", 0)),
        reverse=True,
    )[0]


def download_media(url: str, output_path: Path) -> Path:
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with output_path.open("wb") as handle:
        for chunk in response.iter_content(1024 * 256):
            if chunk:
                handle.write(chunk)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output-dir", default=str(Path.cwd()))
    parser.add_argument("--user-data-dir", default="")
    parser.add_argument("--cdp-url", default="")
    parser.add_argument("--cookies-path", default=default_cookies_path())
    parser.add_argument("--allow-video-fallback", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=5000)
    args = parser.parse_args()

    info = extract_video_info_from_page(
        args.url,
        args.user_data_dir or None,
        args.cdp_url or None,
        args.cookies_path or None,
        headless=args.headless,
        wait_ms=max(args.wait_ms, 0),
    )
    if not info.get("ok"):
        print(json.dumps({"success": False, "error": "video_info_not_found", "detail": info}, ensure_ascii=False, indent=2))
        return 1

    audio_candidates = info.get("audio_candidates", []) or []
    best_audio = (
        sorted(audio_candidates, key=lambda item: (item.get("avgBitrate", 0), item.get("size", 0)), reverse=True)[0]
        if audio_candidates
        else None
    )
    stream = pick_best_stream(info.get("streams", []))

    note_id = info.get("noteId") or extract_note_id(args.url) or "xhs-video"
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    media_kind = ""
    media_meta: dict[str, object] = {}
    if best_audio and best_audio.get("url"):
        media_kind = "audio"
        media_path = output_dir / f"{note_id}.m4a"
        download_media(best_audio["url"], media_path)
        media_meta = {
            "downloaded_file": str(media_path),
            "audio_url": best_audio.get("url", ""),
            "avg_bitrate": best_audio.get("avgBitrate", 0),
            "format": best_audio.get("format", ""),
            "quality_type": best_audio.get("qualityType", ""),
            "size": best_audio.get("size", 0),
        }
    elif args.allow_video_fallback and stream and stream.get("masterUrl"):
        media_kind = "video"
        media_path = output_dir / f"{note_id}.mp4"
        download_media(stream["masterUrl"], media_path)
        media_meta = {
            "downloaded_file": str(media_path),
            "master_url": stream.get("masterUrl", ""),
            "avg_bitrate": stream.get("avgBitrate", 0),
            "width": stream.get("width", 0),
            "height": stream.get("height", 0),
        }
    else:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "audio_not_found",
                    "detail": {"audio_candidates": audio_candidates, "video_available": bool(stream)},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    payload = {
        "success": True,
        "source_url": args.url,
        "note": {
            "note_id": note_id,
            "title": info.get("title", ""),
            "desc": info.get("desc", ""),
            "author": info.get("author", ""),
            "likes": info.get("likes", ""),
            "collects": info.get("collects", ""),
            "comments": info.get("comments", ""),
            "duration": info.get("duration", 0),
        },
        "media": {"kind": media_kind, **media_meta},
        "page": {
            "final_url": info.get("final_url", ""),
            "page_title": info.get("page_title", ""),
            "document_cookie_length": info.get("document_cookie_length", 0),
            "cookies_path": args.cookies_path,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
