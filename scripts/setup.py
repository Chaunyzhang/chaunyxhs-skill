#!/usr/bin/env python3
from __future__ import annotations

from xhs_core import detect_platform, fail, info, install_mcp_binaries, ok


def main() -> None:
    print("\nChauny XHS setup\n")
    os_name, arch = detect_platform()
    info(f"Platform: {os_name}-{arch}")
    success, message = install_mcp_binaries()
    if success:
        ok(message)
        info("Next step: python scripts/login.py")
        return
    fail(message)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
