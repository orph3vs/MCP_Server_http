"""HTTP transport for the existing MCP JSON-RPC server."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

from src.mcp_core import McpProtocolError, McpServer


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _empty_response(handler: BaseHTTPRequestHandler, status: int) -> None:
    handler.send_response(status)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _unauthorized_response(handler: BaseHTTPRequestHandler) -> None:
    payload = {"error": "unauthorized", "message": "Missing or invalid bearer token"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("WWW-Authenticate", 'Bearer realm="mcp"')
    handler.end_headers()
    handler.wfile.write(body)


def _decode_request_body(raw_body: bytes) -> str:
    if not raw_body:
        return ""

    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw_body.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("invalid_encoding: supported=utf-8,utf-8-sig,cp949,euc-kr")


def parse_jsonrpc_http_body(raw_body: bytes) -> Any:
    try:
        decoded = _decode_request_body(raw_body)
        return json.loads(decoded) if decoded else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{exc}") from exc


def dispatch_http_payload(server: McpServer, payload: Any) -> Optional[Any]:
    if isinstance(payload, list):
        responses: List[Dict[str, Any]] = []
        for message in payload:
            request_id = message.get("id") if isinstance(message, dict) else None
            try:
                response = server.handle_message(message)
            except McpProtocolError as exc:
                response = McpServer._jsonrpc_error(request_id, exc.code, exc.message, exc.data)
            if response is not None:
                responses.append(response)
        return responses or None

    request_id = payload.get("id") if isinstance(payload, dict) else None
    try:
        return server.handle_message(payload)
    except McpProtocolError as exc:
        return McpServer._jsonrpc_error(request_id, exc.code, exc.message, exc.data)


def get_expected_bearer_token() -> Optional[str]:
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    return token or None


def is_authorized_request(headers: Mapping[str, str], expected_token: Optional[str] = None) -> bool:
    token = expected_token if expected_token is not None else get_expected_bearer_token()
    if not token:
        return True

    header_value = headers.get("Authorization", "").strip()
    scheme, _, credentials = header_value.partition(" ")
    return scheme.lower() == "bearer" and credentials == token


class McpHttpHandler(BaseHTTPRequestHandler):
    _server: Optional[McpServer] = None

    @classmethod
    def get_mcp_server(cls) -> McpServer:
        if cls._server is None:
            cls._server = McpServer()
        return cls._server

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            _json_response(
                self,
                200,
                {"status": "ok", "transport": "http", "protocol": "json-rpc-2.0"},
            )
            return

        if parsed.path == "/mcp":
            _json_response(
                self,
                405,
                {"error": "method_not_allowed", "allowed_methods": ["POST"]},
            )
            return

        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/mcp":
            _json_response(self, 404, {"error": "not_found"})
            return

        if not is_authorized_request(self.headers):
            _unauthorized_response(self)
            return

        raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            payload = parse_jsonrpc_http_body(raw_body)
        except ValueError as exc:
            _json_response(
                self,
                400,
                McpServer._jsonrpc_error(None, -32700, "Parse error", {"detail": str(exc)}),
            )
            return

        response = dispatch_http_payload(self.get_mcp_server(), payload)
        if response is None:
            _empty_response(self, 204)
            return

        _json_response(self, 200, response)


def run_server(host: str = "0.0.0.0", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), McpHttpHandler)
    auth_state = "enabled" if get_expected_bearer_token() else "disabled"
    print(f"[mcp-http-server] listening on http://{host}:{port}/mcp (bearer auth: {auth_state})")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
