#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

import dashscope
from dashscope.audio.asr import Recognition, Transcription
from urllib import request as urllib_request


if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(__import__("sys").stderr, "reconfigure"):
    __import__("sys").stderr.reconfigure(encoding="utf-8", errors="replace")


AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def is_audio_path(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def is_video_path(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def ensure_api_key() -> None:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("Missing DASHSCOPE_API_KEY in environment.")
    dashscope.api_key = api_key
    dashscope.base_http_api_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to transcribe local video files. Install ffmpeg or provide an audio file directly.")
    return ffmpeg


def extract_audio_from_video(video_path: Path, work_dir: Path) -> Path:
    ffmpeg = require_ffmpeg()
    audio_path = work_dir / f"{video_path.stem}.wav"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not audio_path.exists():
        raise SystemExit(result.stderr or result.stdout or "ffmpeg failed to extract audio.")
    return audio_path


def wait_for_paraformer_result(task_id: str) -> dict:
    response = Transcription.wait(task=task_id)
    if response.status_code != HTTPStatus.OK:
        raise SystemExit(f"DashScope transcription failed: {response}")

    results = []
    for item in response.output.get("results", []):
        if item.get("subtask_status") != "SUCCEEDED":
            results.append({"status": item.get("subtask_status", "UNKNOWN"), "file_url": item.get("file_url", "")})
            continue
        transcription_url = item.get("transcription_url")
        result = json.loads(urllib_request.urlopen(transcription_url).read().decode("utf-8"))
        results.append(result)

    return {
        "task_id": task_id,
        "results": results,
    }


def transcribe_with_paraformer(file_url: str, language_hints: list[str] | None = None) -> dict:
    task_response = Transcription.async_call(
        model="paraformer-v2",
        file_urls=[file_url],
        language_hints=language_hints or None,
    )
    return wait_for_paraformer_result(task_response.output.task_id)


def transcribe_local_audio(audio_path: Path, language: str | None = None) -> dict:
    recognition = Recognition(
        model="paraformer-realtime-v2",
        format=(audio_path.suffix.lower().lstrip(".") or "wav"),
        sample_rate=16000 if audio_path.suffix.lower() == ".wav" else None,
        language_hints=[language] if language else None,
        callback=None,
    )
    response = recognition.call(str(audio_path))
    if response.status_code != HTTPStatus.OK:
        raise SystemExit(f"DashScope local recognition failed: {response}")

    sentences = []
    try:
        sentences = response.get_sentence() or []
    except Exception:
        sentences = []

    return {
        "sentences": sentences,
        "raw": response.output if hasattr(response, "output") else {},
    }


def transcribe_source(
    source: str,
    language: str | None = None,
    keep_temp: bool = False,
) -> dict:
    ensure_api_key()
    work_dir = Path(tempfile.mkdtemp(prefix="chaunyxhs-transcribe-"))
    cleanup_paths: list[Path] = []

    try:
        source_url = source
        normalized_source = source
        source_kind = "remote_url"

        if not is_url(source):
            path = Path(source).expanduser().resolve()
            if not path.exists():
                raise SystemExit(f"Source file does not exist: {path}")

            normalized_source = str(path)
            if is_video_path(path):
                source_kind = "local_video"
                extracted_audio = extract_audio_from_video(path, work_dir)
                cleanup_paths.append(extracted_audio)
                local_result = transcribe_local_audio(extracted_audio, language=language)
                return {
                    "success": True,
                    "provider": "dashscope",
                    "api_mode": "recognition",
                    "model": "paraformer-realtime-v2",
                    "source_kind": source_kind,
                    "source": normalized_source,
                    "submitted_source": str(extracted_audio),
                    "result": local_result,
                }
            elif is_audio_path(path):
                source_kind = "local_audio"
                local_result = transcribe_local_audio(path, language=language)
                return {
                    "success": True,
                    "provider": "dashscope",
                    "api_mode": "recognition",
                    "model": "paraformer-realtime-v2",
                    "source_kind": source_kind,
                    "source": normalized_source,
                    "submitted_source": str(path),
                    "result": local_result,
                }
            else:
                guessed, _ = mimetypes.guess_type(path.name)
                raise SystemExit(f"Unsupported source type: {path.suffix or guessed or 'unknown'}")
        else:
            parsed = urlparse(source)
            suffix = Path(parsed.path).suffix.lower()
            source_kind = "remote_audio_url" if suffix in AUDIO_EXTS else "remote_url"

        result = transcribe_with_paraformer(
            source_url,
            language_hints=[language] if language else None,
        )

        return {
            "success": True,
            "provider": "dashscope",
            "api_mode": "transcription",
            "model": "paraformer-v2",
            "source_kind": source_kind,
            "source": normalized_source,
            "submitted_source": source_url,
            "result": result,
        }
    finally:
        if not keep_temp:
            for temp_path in cleanup_paths:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                work_dir.rmdir()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio with DashScope.")
    parser.add_argument("source", help="Local audio/video path or public audio URL")
    parser.add_argument("--language", default=None, help="Optional language hint, e.g. zh or en")
    parser.add_argument("--keep-temp", action="store_true", help="Keep extracted local audio when source is a video")
    args = parser.parse_args()

    payload = transcribe_source(
        source=args.source,
        language=args.language,
        keep_temp=args.keep_temp,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
