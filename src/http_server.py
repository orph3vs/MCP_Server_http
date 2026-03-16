"""Lightweight HTTP entrypoint for RequestPipeline.

Endpoints:
- GET /health
- GET /logs/recent?limit=10
- POST /ask
- POST /tools/search_law
- POST /tools/get_article
- POST /tools/get_version
- POST /tools/validate_article
- POST /tools/search_precedent
- POST /tools/get_precedent
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.context_builder import build_context
from src.request_pipeline import PipelineRequest, RequestPipeline


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _decode_request_body(raw_body: bytes) -> str:
    """Decode request body with UTF-8 first, then common Korean Windows encodings."""
    if not raw_body:
        return ""

    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw_body.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("invalid_encoding: supported=utf-8,utf-8-sig,cp949,euc-kr")


def parse_json_body(raw_body: bytes) -> Dict[str, Any]:
    try:
        decoded = _decode_request_body(raw_body)
        return json.loads(decoded) if decoded else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{exc}") from exc


def parse_ask_request(raw_body: bytes) -> Tuple[PipelineRequest, Dict[str, Any]]:
    data = parse_json_body(raw_body)

    user_query = str(data.get("user_query", "")).strip()
    if not user_query:
        raise ValueError("missing_user_query")

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else None
    history = data.get("history") if isinstance(data.get("history"), list) else None

    context = build_context(
        explicit_context=data.get("context"),
        metadata=metadata,
        history=history,
    )

    req = PipelineRequest(
        user_query=user_query,
        context=context,
        request_id=data.get("request_id"),
    )
    return req, data


def parse_tool_request(raw_body: bytes, required_fields: Tuple[str, ...]) -> Dict[str, str]:
    data = parse_json_body(raw_body)
    out: Dict[str, str] = {}
    for key in required_fields:
        value = str(data.get(key, "")).strip()
        if not value:
            raise ValueError(f"missing_{key}")
        out[key] = value
    return out


def parse_recent_limit(path: str, default: int = 10, max_limit: int = 100) -> int:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    raw = query.get("limit", [str(default)])[0]
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("invalid_limit") from exc

    if limit <= 0:
        raise ValueError("invalid_limit")
    return min(limit, max_limit)


class PipelineHttpHandler(BaseHTTPRequestHandler):
    _pipeline: Optional[RequestPipeline] = None

    @classmethod
    def get_pipeline(cls) -> RequestPipeline:
        if cls._pipeline is None:
            cls._pipeline = RequestPipeline()
        return cls._pipeline

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            _json_response(self, 200, {"status": "ok"})
            return

        if parsed.path == "/logs/recent":
            try:
                limit = parse_recent_limit(self.path)
                rows = self.get_pipeline().logger.list_recent(limit=limit)
                _json_response(
                    self,
                    200,
                    {
                        "count": len(rows),
                        "summary": self.get_pipeline().logger.summarize_recent(limit=limit),
                        "items": [asdict(r) for r in rows],
                    },
                )
            except ValueError as exc:
                _json_response(self, 400, {"error": str(exc)})
            return

        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)

            if parsed.path == "/ask":
                req, _ = parse_ask_request(raw_body)
                result = self.get_pipeline().process(req)
                _json_response(self, 200, asdict(result))
                return

            if parsed.path == "/tools/search_law":
                fields = parse_tool_request(raw_body, ("query",))
                data = self.get_pipeline().law_api.search_law(fields["query"])
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/get_article":
                fields = parse_tool_request(raw_body, ("law_id", "article_no"))
                data = self.get_pipeline().law_api.get_article(
                    law_id=fields["law_id"], article_no=fields["article_no"]
                )
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/get_version":
                fields = parse_tool_request(raw_body, ("law_id",))
                data = self.get_pipeline().law_api.get_version(law_id=fields["law_id"])
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/validate_article":
                fields = parse_tool_request(raw_body, ("law_id", "article_no"))
                data = self.get_pipeline().law_api.validate_article(
                    law_id=fields["law_id"], article_no=fields["article_no"]
                )
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/search_precedent":
                fields = parse_tool_request(raw_body, ("query",))
                data = self.get_pipeline().law_api.search_precedent(fields["query"])
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/get_precedent":
                fields = parse_tool_request(raw_body, ("precedent_id",))
                data = self.get_pipeline().law_api.get_precedent(precedent_id=fields["precedent_id"])
                _json_response(self, 200, {"data": data})
                return

            _json_response(self, 404, {"error": "not_found"})
        except ValueError as exc:
            _json_response(self, 400, {"error": str(exc)})
        except Exception as exc:  # defensive fallback
            _json_response(self, 500, {"error": f"internal_error:{exc}"})


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), PipelineHttpHandler)
    print(f"[request-pipeline-server] listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
