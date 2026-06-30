from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests


HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def endpoint(url: str) -> str:
    return url.rstrip("/") if url.rstrip("/").endswith("/sse") else f"{url.rstrip('/')}/sse"


def parse_sse_json(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[len("data:"):].strip()
        if not payload.startswith("{"):
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("result" in obj or "error" in obj or "jsonrpc" in obj):
            return obj
    return {}


def jsonrpc(session: requests.Session, url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[dict[str, Any], requests.Response]:
    response = session.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    raw_text = response.content.decode("utf-8", errors="replace")
    if not raw_text.strip():
        return {}, response
    if raw_text.lstrip().startswith("{"):
        return json.loads(raw_text), response
    parsed = parse_sse_json(raw_text)
    if not parsed:
        raise RuntimeError(f"failed to parse SSE response: {raw_text[:500]}")
    return parsed, response


def create_client(url: str, name: str) -> tuple[requests.Session, str, dict[str, str]]:
    resolved_url = endpoint(url)
    session = requests.Session()
    headers = dict(HEADERS)
    result, response = jsonrpc(
        session,
        resolved_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": name, "version": "1.0.0"},
            },
        },
        headers,
    )
    if "error" in result:
        raise RuntimeError(f"{name} initialize failed: {result['error']}")
    session_id = response.headers.get("mcp-session-id")
    if session_id:
        headers["mcp-session-id"] = session_id
    jsonrpc(
        session,
        resolved_url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers,
    )
    return session, resolved_url, headers


def call_tool(client: tuple[requests.Session, str, dict[str, str]], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    session, url, headers = client
    result, _ = jsonrpc(
        session,
        url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers,
    )
    if "error" in result:
        raise RuntimeError(f"tools/call {name} failed: {result['error']}")
    return result


def ensure_json(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"missing output file: {path}")
    with path.open("r", encoding="utf-8") as f:
        json.load(f)


def run_once(parameditor_url: str, editor_data_url: str, script_path: Path, edit_data_path: Path) -> None:
    parameditor = create_client(parameditor_url, "phase0-parameditor")
    editor_data = create_client(editor_data_url, "phase0-param-editor-data")
    call_tool(parameditor, "clear_scene", {})
    call_tool(parameditor, "execute_script", {"srcInput": str(script_path.resolve())})
    call_tool(editor_data, "get_current_editor_data", {"destOutput": str(edit_data_path.resolve())})
    ensure_json(edit_data_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parameditor-url", required=True)
    parser.add_argument("--editor-data-url", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--edit-data", required=True)
    args = parser.parse_args()

    run_once(
        args.parameditor_url,
        args.editor_data_url,
        Path(args.script),
        Path(args.edit_data),
    )
    print(f"wrote editData: {Path(args.edit_data).resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
