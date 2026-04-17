#!/usr/bin/env python3
from __future__ import annotations

import argparse

from xhs_core import fail, info, ok, start_mcp_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    success, message = start_mcp_server(headless=not args.headful)
    if success:
        ok(message)
        return
    fail(message)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
