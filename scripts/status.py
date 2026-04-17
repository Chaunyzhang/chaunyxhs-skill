#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from xhs_core import check_mcp_login, check_mcp_health, health_snapshot


def main() -> None:
    snapshot = health_snapshot()
    snapshot["mcp_running"] = check_mcp_health()
    snapshot["xhs_logged_in"] = check_mcp_login() if snapshot["mcp_running"] else False
    snapshot["all_ready"] = all(
        [
            snapshot["mcp_binary_installed"],
            snapshot["login_binary_installed"],
            snapshot["cookies_exist"],
            snapshot["mcp_running"],
            snapshot["xhs_logged_in"],
        ]
    )

    if "--json" in sys.argv:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        raise SystemExit(0 if snapshot["all_ready"] else 1)

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    raise SystemExit(0 if snapshot["all_ready"] else 1)


if __name__ == "__main__":
    main()
