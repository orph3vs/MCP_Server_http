"""Minimal MCP stdio transport exposing the shared MCP core."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from src.mcp_core import JSONRPC_VERSION, McpProtocolError, McpServer, _log


def _read_message(stream) -> Optional[Dict[str, Any]]:
    line = stream.readline()
    if not line:
        return None

    stripped = line.decode("utf-8").strip()
    if not stripped:
        return None

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        content_length: Optional[int] = None
        if stripped.lower().startswith("content-length:"):
            content_length = int(stripped.split(":", 1)[1].strip())
            while True:
                separator = stream.readline()
                if not separator:
                    return None
                if separator in (b"\r\n", b"\n"):
                    break
            body = stream.read(content_length)
            if not body:
                return None
            try:
                return json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as nested_exc:
                raise McpProtocolError(-32700, "Parse error", {"detail": str(nested_exc)}) from nested_exc
        raise McpProtocolError(-32700, "Parse error", {"detail": str(exc)}) from exc


def _write_message(stream, message: Dict[str, Any]) -> None:
    body = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    stream.write(body)
    stream.flush()


def serve_forever(server: Optional[McpServer] = None) -> None:
    app = server or McpServer()
    _log("server_start")
    while True:
        try:
            message = _read_message(sys.stdin.buffer)
            if message is None:
                _log("server_eof")
                return
            response = app.handle_message(message)
            if response is not None:
                _write_message(sys.stdout.buffer, response)
        except McpProtocolError as exc:
            _log(f"protocol_error code={exc.code} message={exc.message}")
            _write_message(sys.stdout.buffer, McpServer._jsonrpc_error(None, exc.code, exc.message, exc.data))
        except KeyboardInterrupt:
            _log("server_keyboard_interrupt")
            return


__all__ = [
    "JSONRPC_VERSION",
    "McpProtocolError",
    "McpServer",
    "_read_message",
    "_write_message",
    "serve_forever",
]


if __name__ == "__main__":
    serve_forever()
