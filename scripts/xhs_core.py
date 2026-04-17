from __future__ import annotations

import json
import os
import platform
import random
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MCP_REPO = "xpzouying/xiaohongshu-mcp"
MCP_PORT = 18060
MCP_BASE_URL = f"http://localhost:{MCP_PORT}"
GITHUB_API = f"https://api.github.com/repos/{MCP_REPO}/releases/latest"

DATA_DIR = Path.home() / ".local" / "share" / "chaunyxhs-skill"
BIN_DIR = DATA_DIR / "bin"
COOKIES_PATH = DATA_DIR / "cookies.json"
REPORTS_DIR = Path.home() / "Documents" / "XHS-Research"

LEGACY_DATA_DIRS = [
    Path.home() / ".local" / "share" / "xhs-research",
    Path.home() / ".local" / "share" / "xiaohongshu-mcp",
]

DEPTH_CONFIG = {
    "quick": {"detail_top": 8, "comment_top": 5},
    "deep": {"detail_top": 20, "comment_top": 8},
}

PUBLISH_TIME_MAP = [
    (1, "一天内"),
    (7, "一周内"),
    (30, "一个月内"),
    (180, "半年内"),
]

QUERY_PATTERNS = {
    "推荐": ["推荐", "最好", "最佳", "top", "排名", "哪个好", "求推荐", "有没有好的"],
    "测评": ["测评", "评测", "对比", "vs", "versus", "区别"],
    "攻略": ["攻略", "教程", "怎么", "如何", "方法", "步骤", "流程", "指南"],
    "避雷": ["避雷", "踩坑", "不推荐", "别买", "差评", "吐槽", "不要"],
    "产品调研": ["产品调研", "用户体验", "使用场景", "为什么用", "怎么评价"],
    "竞品调研": ["竞品", "竞争", "赛道", "格局", "市场份额"],
    "需求调研": ["痛点", "需求", "想要", "希望", "缺点", "不足", "改进", "建议"],
    "调研": ["调研", "分析", "场景", "市场", "用户"],
}

NOISE_WORDS = frozenset({"推荐", "最好", "最佳", "求", "有没有", "哪个", "怎么样", "吗", "请问", "想问"})

FALLBACK_SUFFIXES = {
    "推荐": ["推荐", "攻略", "排名", "避雷", "种草"],
    "测评": ["测评", "对比", "体验", "优缺点"],
    "攻略": ["攻略", "教程", "新手", "小白"],
    "避雷": ["踩坑", "不推荐", "吐槽", "推荐"],
    "产品调研": ["体验", "吐槽", "优缺点", "使用场景", "推荐"],
    "竞品调研": ["推荐", "对比", "排名", "哪个好", "怎么选"],
    "需求调研": ["痛点", "吐槽", "希望", "建议", "体验"],
    "调研": ["推荐", "攻略", "体验", "痛点"],
    "通用": ["推荐", "攻略", "体验"],
}

STOP_WORDS = frozenset("的 了 在 是 我 你 他 她 它 们 这 那 有 不 也 和 与 及 或 但 如果 虽然 因为 所以".split() + list("的了在是"))

PACE_PROFILE = {
    "page_pre_wait": (0.35, 0.95),
    "page_post_wait": (1.2, 2.6),
    "search_scroll_wait": (0.45, 1.1),
    "detail_gap": (0.8, 1.8),
    "http_gap": (0.35, 1.0),
    "retry_backoff_jitter": (0.6, 1.6),
}

RISK_HINTS = [
    "安全限制",
    "验证",
    "频繁",
    "风险",
    "稍后再试",
    "请完成验证",
    "当前笔记暂时无法浏览",
]

_LAST_ACTION_TS: dict[str, float] = {}


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def log(msg: str) -> None:
    sys.stderr.write(f"[chaunyxhs] {msg}\n")
    sys.stderr.flush()


def random_pause(bucket: str, minimum: float | None = None) -> float:
    low, high = PACE_PROFILE[bucket]
    duration = random.uniform(low, high)
    if minimum is not None:
        duration = max(duration, minimum)
    time.sleep(duration)
    return duration


def paced_gate(name: str, minimum_interval: float) -> float:
    now = time.time()
    previous = _LAST_ACTION_TS.get(name, 0.0)
    wait_for = max(0.0, minimum_interval - (now - previous))
    if wait_for > 0:
        time.sleep(wait_for + random.uniform(0.08, 0.35))
    _LAST_ACTION_TS[name] = time.time()
    return wait_for


def human_page_settle(page, wait_ms: int, light_scroll: bool = False) -> None:
    random_pause("page_pre_wait")
    page.wait_for_timeout(wait_ms)
    random_pause("page_post_wait")

    if light_scroll:
        try:
            page.mouse.move(random.randint(180, 420), random.randint(180, 520), steps=random.randint(12, 28))
            for _ in range(random.randint(1, 2)):
                page.mouse.wheel(0, random.randint(300, 720))
                random_pause("search_scroll_wait")
            if random.random() < 0.45:
                page.mouse.wheel(0, -random.randint(120, 260))
                random_pause("search_scroll_wait", minimum=0.25)
        except Exception:
            pass


def detect_risk_state(final_url: str, page_title: str, extra_text: str = "") -> dict[str, Any]:
    haystack = " ".join([final_url or "", page_title or "", extra_text or ""])
    matched = [hint for hint in RISK_HINTS if hint in haystack]
    return {
        "risk_detected": bool(matched),
        "risk_hints": matched,
    }


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)


def detect_platform() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch_map = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "amd64",
        "amd64": "amd64",
    }
    arch = arch_map.get(machine)
    if arch is None:
        raise RuntimeError(f"Unsupported architecture: {machine}")
    return system, arch


def get_binary_name(prefix: str, with_ext: bool = False) -> str:
    os_name, arch = detect_platform()
    name = f"{prefix}-{os_name}-{arch}"
    if with_ext and os_name == "windows":
        return f"{name}.exe"
    return name


def data_dir_candidates() -> list[Path]:
    return [DATA_DIR, *LEGACY_DATA_DIRS]


def find_binary(prefix: str) -> str | None:
    ensure_directories()
    os_name, arch = detect_platform()
    candidates = [f"{prefix}-{os_name}-{arch}"]
    if os_name == "windows":
        candidates.insert(0, f"{prefix}-{os_name}-{arch}.exe")

    for base_dir in data_dir_candidates():
        bin_dir = base_dir / "bin"
        for candidate in candidates:
            path = bin_dir / candidate
            if path.is_file():
                return str(path)
    return None


def preferred_cookies_path() -> str:
    if COOKIES_PATH.is_file():
        return str(COOKIES_PATH)
    for base_dir in data_dir_candidates():
        candidate = base_dir / "cookies.json"
        if candidate.is_file():
            return str(candidate)
    return str(COOKIES_PATH)


def sync_cookies_into_data_dir() -> None:
    current = Path(preferred_cookies_path())
    if current.is_file() and current != COOKIES_PATH:
        ensure_directories()
        COOKIES_PATH.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")


def http_get_json(url: str, timeout: int = 5) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "chaunyxhs-skill/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def http_post_json(url: str, payload: dict[str, Any], timeout: int = 60, retries: int = 2) -> dict[str, Any] | None:
    paced_gate("http_post_json", 0.9)
    random_pause("http_gap")
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "chaunyxhs-skill/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt == retries - 1:
                log(f"POST failed for {url}: {exc}")
                return None
            time.sleep((1 + attempt) + random.uniform(*PACE_PROFILE["retry_backoff_jitter"]))
    return None


def check_mcp_health() -> bool:
    data = http_get_json(f"{MCP_BASE_URL}/health", timeout=3)
    return isinstance(data, dict) and data.get("success") is True


def check_mcp_login() -> bool:
    data = http_get_json(f"{MCP_BASE_URL}/api/v1/login/status", timeout=10)
    return isinstance(data, dict) and data.get("data", {}).get("is_logged_in") is True


def latest_release_asset() -> dict[str, Any]:
    req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "chaunyxhs-skill/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def install_mcp_binaries() -> tuple[bool, str]:
    ensure_directories()
    existing_mcp = find_binary("xiaohongshu-mcp")
    existing_login = find_binary("xiaohongshu-login")
    if existing_mcp and existing_login:
        return True, "binaries already installed"

    os_name, arch = detect_platform()
    archive_ext = ".zip" if os_name == "windows" else ".tar.gz"
    target_name = f"xiaohongshu-mcp-{os_name}-{arch}{archive_ext}"
    release = latest_release_asset()
    assets = release.get("assets", [])
    asset_url = next((asset["browser_download_url"] for asset in assets if asset["name"] == target_name), None)
    if not asset_url:
        available = ", ".join(asset["name"] for asset in assets)
        return False, f"release asset {target_name} not found; available: {available}"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=archive_ext, delete=False) as tmp:
            tmp_path = tmp.name
            urllib.request.urlretrieve(asset_url, tmp_path)

        if archive_ext == ".zip":
            with zipfile.ZipFile(tmp_path, "r") as archive:
                for name in archive.namelist():
                    base = os.path.basename(name)
                    if base.startswith(("xiaohongshu-mcp-", "xiaohongshu-login-")):
                        target = BIN_DIR / base
                        with archive.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())
        else:
            with tarfile.open(tmp_path, "r:gz") as archive:
                for member in archive.getmembers():
                    if member.name.startswith(("xiaohongshu-mcp-", "xiaohongshu-login-")):
                        member.name = os.path.basename(member.name)
                        archive.extract(member, BIN_DIR)

        for path in BIN_DIR.iterdir():
            if path.is_file():
                os.chmod(path, path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return True, f"installed binaries to {BIN_DIR}"
    except Exception as exc:
        return False, f"download or extract failed: {exc}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def start_mcp_server(headless: bool = True) -> tuple[bool, str]:
    if check_mcp_health():
        return True, f"MCP server already running on port {MCP_PORT}"

    binary = find_binary("xiaohongshu-mcp")
    if not binary:
        return False, "xiaohongshu-mcp binary not found; run setup.py first"

    sync_cookies_into_data_dir()
    env = os.environ.copy()
    env["COOKIES_PATH"] = str(COOKIES_PATH)

    ensure_directories()
    log_path = BIN_DIR / ("mcp-server-headful.log" if not headless else "mcp-server.log")
    log_file = open(log_path, "a", encoding="utf-8")
    args = [binary, "-port", f":{MCP_PORT}"]
    if headless:
        args.append("-headless")
    else:
        args.append("-headless=false")

    try:
        subprocess.Popen(args, env=env, stdout=log_file, stderr=log_file, start_new_session=True)
    except Exception as exc:
        log_file.close()
        return False, f"failed to start MCP: {exc}"
    log_file.close()

    for _ in range(10):
        time.sleep(1)
        if check_mcp_health():
            return True, f"MCP server running on port {MCP_PORT}; log: {log_path}"
    return False, f"MCP server did not become healthy; check log: {log_path}"


def login_with_mcp_binary() -> tuple[bool, str]:
    login_binary = find_binary("xiaohongshu-login")
    if not login_binary:
        return False, "xiaohongshu-login binary not found; run setup.py first"

    ensure_directories()
    result = subprocess.run([login_binary], cwd=str(DATA_DIR))
    if result.returncode != 0:
        return False, f"login process exited with code {result.returncode}"

    sync_cookies_into_data_dir()
    if not Path(preferred_cookies_path()).is_file():
        return False, "cookies.json was not created after login"

    return True, f"login cookies available at {preferred_cookies_path()}"


def load_cookies(context, cookies_path: str | None = None) -> int:
    cookies_path = cookies_path or preferred_cookies_path()
    path = Path(cookies_path)
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
    if cookies:
        context.add_cookies(cookies)
    return len(cookies)


def extract_note_id(url: str) -> str:
    for marker in ("/explore/", "/discovery/item/", "/search_result/"):
        if marker in url:
            return url.split(marker, 1)[1].split("?", 1)[0].split("/", 1)[0]
    return ""


def normalize_note_url(url: str) -> str:
    if "/search_result/" in url:
        note_id = extract_note_id(url)
        query = url.split("?", 1)[1] if "?" in url else ""
        if note_id:
            return f"https://www.xiaohongshu.com/explore/{note_id}" + (f"?{query}" if query else "")
    return url


def search_notes_web(keyword: str, wait_ms: int = 6000) -> list[dict[str, Any]]:
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(keyword)}"
    try:
        with sync_playwright() as p:
            paced_gate("web_search_navigation", 1.6)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            load_cookies(context)
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=120000)
            human_page_settle(page, wait_ms, light_scroll=True)
            risk_state = detect_risk_state(page.url, page.title())
            if risk_state["risk_detected"]:
                log(f'web search risk hints for "{keyword}": {risk_state["risk_hints"]}')
            items = page.evaluate(
                """() => {
                    const notes = [];
                    for (const section of document.querySelectorAll('section.note-item')) {
                        const titleAnchor = section.querySelector('a.title');
                        if (!titleAnchor) continue;
                        const href = titleAnchor.getAttribute('href') || '';
                        if (!href.startsWith('/search_result/')) continue;
                        const noteId = href.split('/search_result/')[1]?.split('?')[0] || '';
                        const params = new URLSearchParams(href.split('?')[1] || '');
                        const xsecToken = params.get('xsec_token') || '';
                        if (!noteId || !xsecToken) continue;
                        notes.push({
                            feed_id: noteId,
                            xsec_token: xsecToken,
                            title: (titleAnchor.textContent || '').trim(),
                            url: 'https://www.xiaohongshu.com' + href,
                            author: (section.querySelector('.author')?.textContent || '').trim(),
                            likes_text: (section.querySelector('.count')?.textContent || '').trim(),
                        });
                    }
                    return notes;
                }"""
            )
            browser.close()
    except Exception as exc:
        log(f'web search failed for "{keyword}": {exc}')
        return []

    results = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "feed_id": item.get("feed_id", ""),
                "xsec_token": item.get("xsec_token", ""),
                "title": item.get("title", ""),
                "snippet": item.get("title", ""),
                "url": item.get("url", ""),
                "author": item.get("author", ""),
                "date": None,
                "likes": to_int(item.get("likes_text")),
                "comments": 0,
                "favorites": 0,
                "keyword": keyword,
                "source": "web_search",
            }
        )
    return results


def search_notes_mcp(keyword: str, publish_time: str = "不限") -> list[dict[str, Any]]:
    payload = {
        "keyword": keyword,
        "filters": {
            "sort_by": "综合",
            "note_type": "不限",
            "publish_time": publish_time,
            "search_scope": "不限",
            "location": "不限",
        },
    }
    resp = http_post_json(f"{MCP_BASE_URL}/api/v1/feeds/search", payload, timeout=90, retries=2)
    if not resp:
        return []
    feeds = resp.get("data", {}).get("feeds", [])
    if not isinstance(feeds, list):
        return []

    results = []
    for feed in feeds:
        if not isinstance(feed, dict):
            continue
        note = feed.get("noteCard") or {}
        interact = note.get("interactInfo") or {}
        feed_id = str(feed.get("id") or note.get("noteId") or "").strip()
        if not feed_id:
            continue

        date_str = None
        raw_time = note.get("time")
        try:
            if raw_time:
                dt = datetime.fromtimestamp(int(raw_time) / 1000.0, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = None

        results.append(
            {
                "feed_id": feed_id,
                "xsec_token": str(feed.get("xsecToken") or note.get("xsecToken") or ""),
                "title": str(note.get("displayTitle") or note.get("title") or "").strip(),
                "snippet": str(note.get("desc") or note.get("displayDesc") or "").strip(),
                "url": f"https://www.xiaohongshu.com/explore/{feed_id}",
                "author": "",
                "date": date_str,
                "likes": to_int(interact.get("likedCount")),
                "comments": to_int(interact.get("commentCount")),
                "favorites": to_int(interact.get("collectedCount")),
                "keyword": keyword,
                "source": "mcp_search",
            }
        )
    return results


def get_feed_detail(feed_id: str, xsec_token: str) -> dict[str, Any] | None:
    return http_post_json(
        f"{MCP_BASE_URL}/api/v1/feeds/detail",
        {"feed_id": feed_id, "xsec_token": xsec_token},
        timeout=45,
        retries=2,
    )


def extract_note_media(
    url: str,
    user_data_dir: str | None = None,
    cdp_url: str | None = None,
    headless: bool = False,
    wait_ms: int = 5000,
) -> dict[str, Any]:
    url = normalize_note_url(url)
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
                load_cookies(context)
            page = context.new_page()
            created_temp_page = True

        if page.url != url:
            paced_gate("media_navigation", 1.3)
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
        human_page_settle(page, wait_ms, light_scroll=False)

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
        risk_state = detect_risk_state(
            data.get("final_url", data.get("finalUrl", page.url)),
            data.get("page_title", data.get("pageTitle", page.title())),
        )
        data.update(risk_state)

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


def to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return 0
    try:
        if text.endswith("万"):
            return int(float(text[:-1]) * 10000)
        if text.endswith("亿"):
            return int(float(text[:-1]) * 100000000)
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def classify_query(topic: str) -> str:
    lowered = topic.lower()
    for query_type, patterns in QUERY_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            return query_type
    return "通用"


def expand_query_fallback(topic: str, depth: str) -> list[str]:
    core = " ".join(part for part in topic.strip().split() if part not in NOISE_WORDS)
    query_type = classify_query(topic)
    suffixes = FALLBACK_SUFFIXES.get(query_type, FALLBACK_SUFFIXES["通用"])
    queries = [topic.strip()]
    if core:
        for suffix in suffixes:
            candidate = f"{core}{suffix}"
            if candidate not in queries:
                queries.append(candidate)
    return queries[: (3 if depth == "quick" else 5)]


def trigrams(text: str) -> set[str]:
    text = text.lower().strip()
    if len(text) < 3:
        return {text}
    return {text[i : i + 3] for i in range(len(text) - 2)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe_by_title(items: list[dict[str, Any]], threshold: float = 0.60) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: item["likes"] + item["comments"] * 2 + item["favorites"], reverse=True)
    keep = [True] * len(ranked)
    title_sets = [trigrams(item["title"]) for item in ranked]
    for i in range(len(ranked)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(ranked)):
            if keep[j] and jaccard(title_sets[i], title_sets[j]) >= threshold:
                keep[j] = False
    return [item for item, keep_item in zip(ranked, keep) if keep_item]


def tokenize_cn(text: str) -> list[str]:
    text = text.lower().strip()
    if not text:
        return []
    tokens = [text[i : i + 2] for i in range(len(text) - 1)] if len(text) >= 2 else [text]
    return [token for token in tokens if token not in STOP_WORDS and token.strip()]


def compute_relevance(title: str, snippet: str, query: str) -> float:
    query_tokens = set(tokenize_cn(query))
    if not query_tokens:
        return 0.5
    title_tokens = set(tokenize_cn(title))
    snippet_tokens = set(tokenize_cn(snippet[:200]))
    doc_tokens = title_tokens | snippet_tokens
    if not doc_tokens:
        return 0.05
    coverage = len(query_tokens & doc_tokens) / len(query_tokens)
    precision = len(query_tokens & doc_tokens) / len(doc_tokens)
    title_coverage = len(query_tokens & title_tokens) / len(query_tokens)
    score = 0.60 * (coverage**1.35) + 0.25 * precision + (0.15 if title_coverage >= 0.5 else 0.0)
    return min(1.0, max(0.05, round(score, 3)))


def recency_score(date_str: str | None, max_days: int | None = None) -> float:
    if not date_str:
        return 30.0
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 30.0
    window = max_days if max_days and max_days > 0 else 365
    return max(0.0, min(100.0, 100 * (1 - age_days / window)))


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [50.0] * len(values)
    return [100 * (value - low) / (high - low) for value in values]


def engagement_raw(likes: int, comments: int, favorites: int) -> float:
    import math

    return 0.40 * math.log1p(favorites) + 0.30 * math.log1p(likes) + 0.30 * math.log1p(comments)


def score_research_items(items: list[dict[str, Any]], query: str, max_days: int | None = None) -> list[dict[str, Any]]:
    for item in items:
        item["_rel"] = compute_relevance(item["title"], item["snippet"], query) * 100
        item["_rec"] = recency_score(item.get("date"), max_days)
        item["_eng_raw"] = engagement_raw(item["likes"], item["comments"], item["favorites"])

    for item, eng in zip(items, normalize([item["_eng_raw"] for item in items])):
        item["_eng"] = eng
        item["score"] = int(0.40 * item["_rel"] + 0.25 * item["_rec"] + 0.35 * item["_eng"])

    return sorted(items, key=lambda item: (item["score"], item["_eng_raw"]), reverse=True)


def fetch_research_details(items: list[dict[str, Any]], top: int, depth: str) -> list[dict[str, Any]]:
    comment_limit = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["deep"])["comment_top"]
    enriched = []
    for item in items[:top]:
        paced_gate("detail_fetch", 1.1)
        detail = get_feed_detail(item["feed_id"], item["xsec_token"])
        if not detail:
            item["content"] = ""
            item["top_comments"] = []
            enriched.append(item)
            continue
        note = detail.get("data", {}).get("data", {}).get("note", {})
        comments = detail.get("data", {}).get("data", {}).get("comments", {}).get("list", [])
        interact = note.get("interactInfo", {})
        item["content"] = str(note.get("desc", ""))[:800]
        item["author"] = note.get("user", {}).get("nickname", item.get("author", ""))
        item["likes"] = to_int(interact.get("likedCount")) or item["likes"]
        item["comments"] = to_int(interact.get("commentCount")) or item["comments"]
        item["favorites"] = to_int(interact.get("collectedCount")) or item["favorites"]

        top_comments = []
        if isinstance(comments, list):
            for comment in comments[:comment_limit]:
                if not isinstance(comment, dict):
                    continue
                replies = []
                for reply in (comment.get("subComments") or [])[:2]:
                    if isinstance(reply, dict):
                        replies.append(
                            {
                                "user": reply.get("userInfo", {}).get("nickname", "?"),
                                "content": str(reply.get("content", ""))[:200],
                                "likes": to_int(reply.get("likeCount")),
                            }
                        )
                top_comments.append(
                    {
                        "user": comment.get("userInfo", {}).get("nickname", "?"),
                        "content": str(comment.get("content", ""))[:200],
                        "likes": to_int(comment.get("likeCount")),
                        "sub_comments": replies,
                    }
                )
        item["top_comments"] = top_comments
        enriched.append(item)
        random_pause("detail_gap")
    return enriched


def render_research_report(
    items: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    keywords: list[str],
    topic: str,
    query_type: str,
) -> str:
    total_likes = sum(item["likes"] for item in items)
    total_favorites = sum(item["favorites"] for item in items)
    total_comments = sum(item["comments"] for item in items)

    lines = [
        f"## 小红书调研：{topic}",
        f"查询类型：{query_type}",
        f"关键词：{', '.join(keywords)}",
        f"搜索结果：{len(items)} 条笔记（去重后），{len(enriched)} 篇详情",
        "",
        "### 详情笔记（含正文和评论）",
        "",
    ]
    for index, item in enumerate(enriched, start=1):
        lines.append(
            f"**XHS{index}** (score:{item.get('score', 0)}) {item.get('author', '?')} "
            f"[赞{item['likes']} 评{item['comments']} 藏{item['favorites']}]"
        )
        lines.append(f"  {item['title']}")
        lines.append(f"  {item['url']}")
        if item.get("content"):
            lines.append(f"  {item['content'][:500]}")
        if item.get("top_comments"):
            lines.append("  --- 热评 ---")
            for comment in item["top_comments"]:
                lines.append(f"  [{comment['likes']}赞] {comment['user']}: {comment['content']}")
                for reply in comment.get("sub_comments", []):
                    lines.append(f"    [{reply['likes']}赞] {reply['user']}: {reply['content']}")
        lines.append("")

    remaining_ids = {item["feed_id"] for item in enriched}
    remaining = [item for item in items if item["feed_id"] not in remaining_ids]
    if remaining:
        lines.extend(["### 其他相关笔记", ""])
        start_index = len(enriched) + 1
        for index, item in enumerate(remaining[:30], start=start_index):
            lines.append(f"**XHS{index}** (score:{item.get('score', 0)}) [赞{item['likes']} 评{item['comments']} 藏{item['favorites']}]")
            lines.append(f"  {item['title']}")
            lines.append(f"  {item['url']}")
            lines.append("")

    top_post = max(items, key=lambda item: item["likes"]) if items else None
    top_authors = list(dict.fromkeys(item.get("author", "?") for item in enriched if item.get("author")))[:5]
    lines.extend(
        [
            "---",
            f"小红书 {len(items)} 条笔记（{len(keywords)} 轮搜索） | {len(enriched)} 篇详情 | "
            f"{total_likes} 赞 | {total_favorites} 收藏 | {total_comments} 评论",
        ]
    )
    if top_post:
        lines.append(f"最高互动：{top_post['title'][:40]}（赞 {top_post['likes']}）")
    if top_authors:
        lines.append(f"主要作者：{', '.join(top_authors)}")
    lines.append("---")
    return "\n".join(lines)


def health_snapshot() -> dict[str, Any]:
    sync_cookies_into_data_dir()
    return {
        "platform": "-".join(detect_platform()),
        "data_dir": str(DATA_DIR),
        "cookies_path": preferred_cookies_path(),
        "mcp_binary_installed": find_binary("xiaohongshu-mcp") is not None,
        "login_binary_installed": find_binary("xiaohongshu-login") is not None,
        "cookies_exist": Path(preferred_cookies_path()).is_file(),
        "mcp_running": check_mcp_health(),
        "xhs_logged_in": check_mcp_login(),
    }
