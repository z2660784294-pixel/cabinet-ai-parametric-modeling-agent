from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def mcp_endpoint(url: str) -> str:
    stripped = url.rstrip("/")
    return stripped if stripped.endswith("/sse") else f"{stripped}/sse"


def parse_sse_json(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[len("data:"):].strip()
        if not payload.startswith("{"):
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed or "jsonrpc" in parsed):
            return parsed
    return {}


def jsonrpc(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> tuple[dict[str, Any], requests.Response]:
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


class McpClient:
    def __init__(self, base_url: str, client_name: str) -> None:
        self.url = mcp_endpoint(base_url)
        self.session = requests.Session()
        self.headers = dict(HEADERS)
        self.client_name = client_name
        self._request_id = 1
        self._initialize()

    def _next_id(self) -> int:
        value = self._request_id
        self._request_id += 1
        return value

    def _initialize(self) -> None:
        result, response = jsonrpc(
            self.session,
            self.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": self.client_name, "version": "1.0.0"},
                },
            },
            self.headers,
        )
        if "error" in result:
            raise RuntimeError(f"{self.client_name} initialize failed: {result['error']}")
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.headers["mcp-session-id"] = session_id
        jsonrpc(
            self.session,
            self.url,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            self.headers,
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result, _ = jsonrpc(
            self.session,
            self.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            self.headers,
        )
        if "error" in result:
            raise RuntimeError(f"tools/call {name} failed: {result['error']}")
        return result


def ensure_json_file(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"missing JSON output: {path}")
    with path.open("r", encoding="utf-8") as file:
        json.load(file)


class ParamEditorClient:
    def __init__(self, base_url: str) -> None:
        self.client = McpClient(base_url, "regression-parameditor")

    def clear_scene(self) -> None:
        self.client.call_tool("clear_scene", {})

    def execute_script(self, script_path: Path) -> None:
        self.client.call_tool("execute_script", {"srcInput": str(script_path.resolve())})

    def capture_result_image(self, output_path: Path, camera_view_mode: str = "front") -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.call_tool(
            "get_preview_image",
            {"destOutput": str(output_path.resolve()), "cameraViewMode": camera_view_mode},
        )
        if not output_path.exists():
            raise RuntimeError(f"missing preview image output: {output_path}")


class ParamEditorDataClient:
    def __init__(self, base_url: str) -> None:
        self.client = McpClient(base_url, "regression-param-editor-data")

    def export_current_editor_data(self, output_path: Path) -> None:
        self.client.call_tool("get_current_editor_data", {"destOutput": str(output_path.resolve())})
        ensure_json_file(output_path)
