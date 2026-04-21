from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from xhs_core import capability_gate, extract_note_id, extract_note_media, normalize_note_url, preferred_cookies_path


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
    gate = capability_gate("media")
    if not gate.get("ready"):
        print(json.dumps({"success": False, "message": gate.get("message"), "prepare_summary": gate.get("prepare_summary")}, ensure_ascii=False, indent=2))
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output-dir", default=str(Path.cwd()))
    parser.add_argument("--user-data-dir", default="")
    parser.add_argument("--cdp-url", default="")
    parser.add_argument("--cookies-path", default=preferred_cookies_path())
    parser.add_argument("--allow-video-fallback", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=5000)
    args = parser.parse_args()

    source_url = normalize_note_url(args.url)
    info = extract_note_media(
        source_url,
        user_data_dir=args.user_data_dir or None,
        cdp_url=args.cdp_url or None,
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

    note_id = info.get("noteId") or extract_note_id(source_url) or "xhs-video"
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
        "source_url": source_url,
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
