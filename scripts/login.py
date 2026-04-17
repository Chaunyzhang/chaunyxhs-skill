#!/usr/bin/env python3
from __future__ import annotations

from xhs_core import fail, info, login_with_mcp_binary, ok, start_mcp_server


def main() -> None:
    print("\nChauny XHS login\n")
    info("A Chrome window may open for QR-code login.")
    success, message = login_with_mcp_binary()
    if not success:
        fail(message)
        raise SystemExit(1)
    ok(message)

    server_ok, server_message = start_mcp_server(headless=True)
    if server_ok:
        ok(server_message)
        return
    fail(server_message)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
