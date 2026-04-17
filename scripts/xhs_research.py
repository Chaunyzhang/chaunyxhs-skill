#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from xhs_core import (
    DEPTH_CONFIG,
    PUBLISH_TIME_MAP,
    check_mcp_health,
    check_mcp_login,
    classify_query,
    dedupe_by_title,
    expand_query_fallback,
    fetch_research_details,
    log,
    render_research_report,
    REPORTS_DIR,
    score_research_items,
    search_notes_mcp,
    search_notes_web,
)


def search_multi(keywords: list[str], publish_time: str, search_provider: str) -> list[dict]:
    found = {}

    def run_one(keyword: str) -> list[dict]:
        if search_provider in {"auto", "web"}:
            web_results = search_notes_web(keyword)
            if web_results:
                return web_results
        if search_provider in {"auto", "mcp"}:
            return search_notes_mcp(keyword, publish_time=publish_time)
        return []

    with ThreadPoolExecutor(max_workers=min(len(keywords), 3)) as executor:
        futures = {executor.submit(run_one, keyword): keyword for keyword in keywords}
        for future in as_completed(futures):
            keyword = futures[future]
            try:
                for item in future.result():
                    found.setdefault(item["feed_id"], item)
                log(f'"{keyword}" -> {len(found)} unique notes so far')
            except Exception as exc:
                log(f'"{keyword}" search failed: {exc}')
    return dedupe_by_title(list(found.values()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chauny XHS research workflow")
    parser.add_argument("topic", nargs="*", help="Research topic when --keywords is not provided")
    parser.add_argument("--keywords", type=str, help="Comma-separated search keywords")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--save-dir", type=str, default=str(REPORTS_DIR))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--search-provider", choices=["auto", "web", "mcp"], default="auto")
    args = parser.parse_args()

    depth = "quick" if args.quick else "deep"
    detail_top = args.top or DEPTH_CONFIG[depth]["detail_top"]

    if args.keywords:
        keywords = [part.strip() for part in args.keywords.split(",") if part.strip()]
        topic = keywords[0] if keywords else ""
    elif args.topic:
        topic = " ".join(args.topic).strip()
        keywords = expand_query_fallback(topic, depth)
    else:
        raise SystemExit("Error: provide topic or --keywords")

    publish_time = "不限"
    if args.days is not None:
        for max_days, mapped in PUBLISH_TIME_MAP:
            if args.days <= max_days:
                publish_time = mapped
                break

    if not check_mcp_health():
        raise SystemExit("Error: MCP server is not running. Run: python scripts/start.py")
    if not check_mcp_login():
        raise SystemExit("Error: Xiaohongshu is not logged in. Run: python scripts/login.py")

    log(f"Topic: {topic}")
    log(f"Query type: {classify_query(topic)}")
    log(f"Keywords: {keywords}")
    log(f"Depth: {depth}, publish_time: {publish_time}, detail_top: {detail_top}")

    items = search_multi(keywords, publish_time, args.search_provider)
    log(f"After dedup: {len(items)} unique notes")
    if not items:
        raise SystemExit("No results found.")

    items = score_research_items(items, topic, args.days)
    enriched = fetch_research_details(items, top=detail_top, depth=depth)

    if args.json:
        output = json.dumps(
            {
                "topic": topic,
                "query_type": classify_query(topic),
                "keywords": keywords,
                "total_notes": len(items),
                "enriched_count": len(enriched),
                "items": items,
                "enriched": enriched,
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = render_research_report(items, enriched, keywords, topic, classify_query(topic))

    print(output)

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)
        slug = topic.replace(" ", "-")[:50] or "xhs-research"
        path = os.path.join(args.save_dir, f"{slug}-{datetime.now().strftime('%Y%m%d')}-raw.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(output)
        log(f"Saved to {path}")


if __name__ == "__main__":
    main()
