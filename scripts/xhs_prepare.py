#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from prepare_state import default_prepare_state, set_capability, set_phase, write_prepare_state
from xhs_core import PREP_STATE, health_snapshot, start_mcp_server


def prepare_payload(state: dict, snapshot: dict) -> dict:
    capabilities = state.get("capabilities", {})
    blockers = state.get("blockers", [])
    human_action = None
    if (state.get("phases", {}).get("setup") or {}).get("status") == "needs_human_action":
        human_action = {"commands": ["python scripts/setup.py", "python scripts/xhs_prepare.py"], "message": "Install the XHS binaries before continuing."}
    elif (state.get("phases", {}).get("login") or {}).get("status") == "needs_human_action":
        human_action = {"commands": ["python scripts/login.py", "python scripts/xhs_prepare.py"], "message": "Login with the visible QR-code window, then rerun prepare."}
    status = "ready"
    if human_action:
        status = "needs_human_action"
    elif blockers:
        status = "failed"
    return {
        "success": status == "ready",
        "status": status,
        "human_action_required": bool(human_action),
        "human_action": human_action,
        "state_file": str(PREP_STATE),
        "runtime_signature": state.get("runtime_signature"),
        "phases": state.get("phases", {}),
        "capabilities": capabilities,
        "blockers": blockers,
        "status_snapshot": {
            "base_ready": snapshot.get("base_ready"),
            "all_ready": snapshot.get("all_ready"),
        },
        "next_actions": human_action["commands"] if human_action else ["Preparation passed. You can continue with xhs_research.py or xhs_video_pipeline.py."],
    }


def main() -> int:
    state = default_prepare_state()
    blockers: list[str] = []
    snapshot = health_snapshot()
    state["runtime_signature"] = snapshot.get("runtime_signature", {})

    setup_ready = bool(snapshot.get("mcp_binary_installed") and snapshot.get("login_binary_installed"))
    set_phase(state, "setup", "ready" if setup_ready else "needs_human_action", snapshot)
    if not setup_ready:
        set_capability(state, "research", False, "Run python scripts/setup.py first.")
        set_capability(state, "media", False, "Run python scripts/setup.py first.")
        set_capability(state, "transcription", bool(os.getenv("DASHSCOPE_API_KEY")), "DashScope key is required for transcription." if not os.getenv("DASHSCOPE_API_KEY") else "Transcription key present.")
        state["blockers"] = []
        write_prepare_state(PREP_STATE, state)
        print(json.dumps(prepare_payload(state, snapshot), ensure_ascii=False, indent=2))
        return 2

    if not snapshot.get("cookies_exist") or not snapshot.get("xhs_logged_in"):
        set_phase(state, "login", "needs_human_action", snapshot)
        set_capability(state, "research", False, "Login is required before research can run.")
        set_capability(state, "media", False, "Login is required before media extraction can run.")
        set_capability(state, "transcription", bool(os.getenv("DASHSCOPE_API_KEY")), "DashScope key is required for transcription." if not os.getenv("DASHSCOPE_API_KEY") else "Transcription key present.")
        state["blockers"] = []
        write_prepare_state(PREP_STATE, state)
        print(json.dumps(prepare_payload(state, snapshot), ensure_ascii=False, indent=2))
        return 2

    if not snapshot.get("mcp_running"):
        started, message = start_mcp_server(headless=True)
        set_phase(state, "mcp_start", "ready" if started else "failed", {"message": message})
        if not started:
            blockers.append(message)
            state["blockers"] = blockers
            set_capability(state, "research", False, "MCP server failed to start.")
            set_capability(state, "media", False, "MCP server failed to start.")
            set_capability(state, "transcription", bool(os.getenv("DASHSCOPE_API_KEY")), "DashScope key is required for transcription." if not os.getenv("DASHSCOPE_API_KEY") else "Transcription key present.")
            write_prepare_state(PREP_STATE, state)
            print(json.dumps(prepare_payload(state, health_snapshot()), ensure_ascii=False, indent=2))
            return 1

    final_snapshot = health_snapshot()
    state["runtime_signature"] = final_snapshot.get("runtime_signature", {})
    set_phase(state, "setup", "ready", final_snapshot)
    set_phase(state, "login", "ready", final_snapshot)
    set_phase(state, "mcp_start", "ready", {"message": "MCP server is healthy."})
    set_capability(state, "research", True, "Research workflow is prepared.")
    set_capability(state, "media", True, "Media extraction workflow is prepared.")
    set_capability(state, "transcription", bool(os.getenv("DASHSCOPE_API_KEY")), "Transcription key present." if os.getenv("DASHSCOPE_API_KEY") else "Set DASHSCOPE_API_KEY in the current agent session if transcription is needed.")
    state["blockers"] = blockers
    write_prepare_state(PREP_STATE, state)
    print(json.dumps(prepare_payload(state, final_snapshot), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
