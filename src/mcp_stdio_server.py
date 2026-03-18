"""Minimal MCP stdio server exposing the current law tools."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.request_pipeline import PipelineRequest, RequestPipeline
from src.cost_logger import CostLogEntry


JSONRPC_VERSION = "2.0"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "mcp_server.log"


def _log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message.rstrip()}\n")
    except Exception:
        pass


class McpProtocolError(RuntimeError):
    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class McpServer:
    def __init__(self, pipeline: Optional[RequestPipeline] = None) -> None:
        self._pipeline = pipeline
        self.initialized = False
        self.negotiated_protocol_version: Optional[str] = None

    @property
    def pipeline(self) -> RequestPipeline:
        if self._pipeline is None:
            _log("pipeline_init_start")
            self._pipeline = RequestPipeline()
            _log("pipeline_init_done")
        return self._pipeline

    def _server_info(self) -> Dict[str, str]:
        return {"name": "MyMcpServer", "version": "0.1.0"}

    def _tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "ask",
                "description": (
                    "Primary tool for end-user Korean legal Q&A using 국가법령정보센터 evidence. "
                    "Use this first for natural-language legal questions, interpretation requests, compliance questions, "
                    "or when the user wants a final answer rather than raw lookup steps. "
                    "Prefer this over search_law/get_article/validate_article unless raw inspection is specifically needed. "
                    "Returns a synthesized answer plus summarized citations."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_query": {
                            "type": "string",
                            "description": "Natural-language legal question in Korean.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional extra context such as 기준시점, company situation, or prior facts.",
                        },
                        "request_id": {"type": "string", "description": "Optional caller-supplied request id."},
                    },
                    "required": ["user_query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "answer_with_citations",
                "description": (
                    "Preferred final-answer tool for end-user legal Q&A. "
                    "Use this before raw tools when the user asks a legal question in prose and wants a grounded answer with citations. "
                    "search_law/get_article/validate_article are investigation helpers, not the default path for final answers."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_query": {"type": "string", "description": "Natural-language Korean legal question."},
                        "context": {
                            "type": "string",
                            "description": "Optional extra context such as 기준시점, company facts, or constraints.",
                        },
                        "request_id": {"type": "string", "description": "Optional caller-supplied request id."},
                    },
                    "required": ["user_query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_law",
                "description": (
                    "Investigation helper that returns raw law search hits via 국가법령정보센터. "
                    "Use only when you need raw search results, to identify a law_id, or to inspect candidate laws before another step. "
                    "Do not prefer this over ask/answer_with_citations for ordinary legal Q&A."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Law search query text."}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_article",
                "description": (
                    "Investigation helper that fetches the raw text of a specific article. "
                    "Use when law_id and article number are already known and you need to inspect or quote article text directly. "
                    "Do not use this as the default final-answer path when ask/answer_with_citations can answer the question."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "law_id": {"type": "string", "description": "법령ID such as 011357."},
                        "article_no": {"type": "string", "description": "Article number such as 제1조."},
                    },
                    "required": ["law_id", "article_no"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_version",
                "description": (
                    "Investigation helper that fetches version metadata such as 시행일자 and 공포일자 for a law. "
                    "Use when version timing itself matters."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "law_id": {"type": "string", "description": "법령ID such as 011357."},
                    },
                    "required": ["law_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "validate_article",
                "description": (
                    "Investigation helper that checks whether a law/article pair resolves to an actual article text. "
                    "Use for validation or guardrails after a likely article has already been identified, not as the default answer tool."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "law_id": {"type": "string", "description": "법령ID such as 011357."},
                        "article_no": {"type": "string", "description": "Article number such as 제1조."},
                    },
                    "required": ["law_id", "article_no"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_precedent",
                "description": (
                    "Investigation helper for Korean precedents. "
                    "Use when the issue is ambiguous, high-risk, interpretation-heavy, or statutory text alone may not be enough. "
                    "For ordinary statutory Q&A, start with ask/answer_with_citations."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Precedent search query text."},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_precedent",
                "description": "Fetch the detail payload for a specific precedent id returned by search_precedent.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "precedent_id": {"type": "string", "description": "Precedent id such as 판례일련번호."},
                    },
                    "required": ["precedent_id"],
                    "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    @staticmethod
    def _jsonrpc_error(request_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        error: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}

    @staticmethod
    def _tool_text(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _tool_input_summary(tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name in ("ask", "answer_with_citations"):
            return str(arguments.get("user_query", "")).strip()
        if tool_name == "search_law":
            return str(arguments.get("query", "")).strip()
        if tool_name == "get_article":
            return f"{arguments.get('law_id', '')} {arguments.get('article_no', '')}".strip()
        if tool_name == "get_version":
            return str(arguments.get("law_id", "")).strip()
        if tool_name == "validate_article":
            return f"{arguments.get('law_id', '')} {arguments.get('article_no', '')}".strip()
        if tool_name == "search_precedent":
            return str(arguments.get("query", "")).strip()
        if tool_name == "get_precedent":
            return str(arguments.get("precedent_id", "")).strip()
        return tool_name

    def _log_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        latency_ms: float,
        error_stage: Optional[str] = None,
    ) -> None:
        nlic_tools = {
            "search_law",
            "get_article",
            "get_version",
            "validate_article",
            "search_precedent",
            "get_precedent",
        }
        self.pipeline.logger.log_request(
            CostLogEntry(
                request_id=str(arguments.get("request_id", "")).strip() or f"tool-{int(time.time() * 1000)}",
                risk_level="LOW",
                mode="tool" if not error_stage else f"error:{error_stage}",
                tokens_in=0,
                tokens_out=0,
                cost=0.0,
                latency=latency_ms,
                score=0.0,
                entry_type="tool",
                tool_name=tool_name,
                question_summary=self._tool_input_summary(tool_name, arguments),
                question_intent="tool",
                error_stage=error_stage,
                tool_calls=1,
                nlic_calls=1 if tool_name in nlic_tools else 0,
                law_search_count=1 if tool_name == "search_law" else 0,
                version_fetch_count=1 if tool_name == "get_version" else 0,
                article_fetch_count=1 if tool_name in {"get_article", "validate_article"} else 0,
                precedent_search_count=1 if tool_name == "search_precedent" else 0,
                precedent_fetch_count=1 if tool_name == "get_precedent" else 0,
            )
        )

    @staticmethod
    def _tool_summary(tool_name: str, payload: Dict[str, Any]) -> str:
        if tool_name in ("ask", "answer_with_citations"):
            answer = str(payload.get("answer", "")).strip()
            citations = payload.get("citations") or {}
            law_context = citations.get("law_context") or {}
            primary_law = law_context.get("primary_law") or {}
            article = law_context.get("article") or {}
            precedent = law_context.get("precedent") or {}
            lines = []
            if answer:
                lines.append(answer)
            if primary_law.get("law_name"):
                lines.append(f"[근거 법령] {primary_law['law_name']} ({primary_law.get('law_id', '-')})")
            if article.get("article_no"):
                lines.append(f"[관련 조문] {article['article_no']}")
            if precedent.get("case_name") or precedent.get("case_no"):
                lines.append(f"[참고 판례] {precedent.get('case_name') or precedent.get('case_no')}")
            return "\n".join(lines).strip() or McpServer._tool_text(payload)

        if tool_name == "search_law":
            raw_items = payload.get("LawSearch", {}).get("law") or payload.get("law") or []
            if isinstance(raw_items, dict):
                raw_items = [raw_items]
            items = []
            for item in raw_items[:5]:
                if isinstance(item, dict):
                    law_name = item.get("법령명한글") or item.get("법령명_한글") or "-"
                    law_id = item.get("법령ID") or "-"
                    items.append(f"- {law_name} ({law_id})")
            return "법령 검색 결과\n" + "\n".join(items) if items else McpServer._tool_text(payload)

        if tool_name == "get_article":
            article_no = payload.get("article_no") or "-"
            article_text = str(payload.get("article_text", "")).strip()
            return f"{article_no}\n{article_text}".strip() or McpServer._tool_text(payload)

        if tool_name == "get_version":
            version_fields = payload.get("version_fields") or {}
            lines = ["법령 버전 정보"]
            if version_fields.get("시행일자"):
                lines.append(f"- 시행일자: {version_fields['시행일자']}")
            if version_fields.get("공포일자") or version_fields.get("공포 일자"):
                lines.append(f"- 공포일자: {version_fields.get('공포일자') or version_fields.get('공포 일자')}")
            if version_fields.get("제개정구분명") or version_fields.get("제개정구분"):
                lines.append(f"- 제개정구분: {version_fields.get('제개정구분명') or version_fields.get('제개정구분')}")
            return "\n".join(lines) if len(lines) > 1 else McpServer._tool_text(payload)

        if tool_name == "validate_article":
            return f"조문 유효성: {'true' if payload.get('is_valid') else 'false'}"

        if tool_name == "search_precedent":
            raw_items = payload.get("PrecSearch", {}).get("prec") or payload.get("prec") or []
            if isinstance(raw_items, dict):
                raw_items = [raw_items]
            items = []
            for item in raw_items[:5]:
                if isinstance(item, dict):
                    case_name = item.get("사건명") or item.get("판례명") or item.get("사건번호") or "-"
                    case_no = item.get("사건번호") or "-"
                    items.append(f"- {case_name} ({case_no})")
            return "판례 검색 결과\n" + "\n".join(items) if items else McpServer._tool_text(payload)

        if tool_name == "get_precedent":
            return McpServer._tool_text(payload)

        return McpServer._tool_text(payload)

    def _tool_success(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": self._tool_summary(tool_name, payload)}],
            "structuredContent": payload,
            "isError": False,
        }

    def _tool_failure(self, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"error": message}
        if data:
            payload["data"] = data
        return {
            "content": [{"type": "text", "text": self._tool_text(payload)}],
            "structuredContent": payload,
            "isError": True,
        }

    @staticmethod
    def _require_string(arguments: Dict[str, Any], key: str) -> str:
        value = str(arguments.get(key, "")).strip()
        if not value:
            raise ValueError(f"missing_{key}")
        return value

    def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise McpProtocolError(-32602, "protocolVersion is required")

        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[-1]
        self.negotiated_protocol_version = negotiated
        self.initialized = False
        _log(f"initialize requested={requested} negotiated={negotiated}")
        return self._jsonrpc_result(
            request_id,
            {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": self._server_info(),
            },
        )

    def _ensure_ready(self) -> None:
        if self.negotiated_protocol_version is None:
            raise McpProtocolError(-32002, "Server not initialized")

    def _handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        self._ensure_ready()
        _log("tools/list")
        return self._jsonrpc_result(request_id, {"tools": self._tool_definitions()})

    def _handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_ready()

        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str):
            raise McpProtocolError(-32602, "Tool name is required")
        if not isinstance(arguments, dict):
            raise McpProtocolError(-32602, "Tool arguments must be an object")
        _log(f"tools/call name={tool_name}")
        started = time.perf_counter()

        try:
            if tool_name in ("ask", "answer_with_citations"):
                result = self.pipeline.process(
                    PipelineRequest(
                        user_query=self._require_string(arguments, "user_query"),
                        context=str(arguments.get("context", "")).strip() or None,
                        request_id=str(arguments.get("request_id", "")).strip() or None,
                    )
                )
                payload = asdict(result)
                if payload.get("error"):
                    error = payload.get("error") or {}
                    stage = str(error.get("stage", "Pipeline"))
                    message = str(error.get("message", "tool_execution_failed"))
                    _log(f"tool_result_error name={tool_name} stage={stage} message={message}")
                    return self._jsonrpc_result(
                        request_id,
                        self._tool_failure(message, payload),
                    )
            elif tool_name == "search_law":
                payload = self.pipeline.law_api.search_law(self._require_string(arguments, "query"))
            elif tool_name == "get_article":
                payload = self.pipeline.law_api.get_article(
                    law_id=self._require_string(arguments, "law_id"),
                    article_no=self._require_string(arguments, "article_no"),
                )
            elif tool_name == "get_version":
                payload = self.pipeline.law_api.get_version(law_id=self._require_string(arguments, "law_id"))
            elif tool_name == "validate_article":
                payload = self.pipeline.law_api.validate_article(
                    law_id=self._require_string(arguments, "law_id"),
                    article_no=self._require_string(arguments, "article_no"),
                )
            elif tool_name == "search_precedent":
                payload = self.pipeline.law_api.search_precedent(self._require_string(arguments, "query"))
            elif tool_name == "get_precedent":
                payload = self.pipeline.law_api.get_precedent(
                    precedent_id=self._require_string(arguments, "precedent_id")
                )
            else:
                raise McpProtocolError(-32602, f"Unknown tool: {tool_name}")
        except McpProtocolError:
            raise
        except ValueError as exc:
            self._log_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_stage="Validation",
            )
            return self._jsonrpc_result(request_id, self._tool_failure(str(exc)))
        except Exception as exc:
            self._log_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_stage="ToolRuntime",
            )
            _log(f"tool_result_error name={tool_name} stage=ToolRuntime message={str(exc)}")
            return self._jsonrpc_result(request_id, self._tool_failure("tool_execution_failed", {"detail": str(exc)}))

        if tool_name not in ("ask", "answer_with_citations"):
            self._log_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        return self._jsonrpc_result(request_id, self._tool_success(tool_name, payload))

    def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(message, dict):
            raise McpProtocolError(-32600, "Invalid Request")
        if message.get("jsonrpc") != JSONRPC_VERSION:
            raise McpProtocolError(-32600, "Invalid Request")

        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise McpProtocolError(-32602, "params must be an object")

        if method == "initialize":
            return self._handle_initialize(request_id, params)
        if method == "notifications/initialized":
            self._ensure_ready()
            self.initialized = True
            _log("notifications/initialized")
            return None
        if method == "tools/list":
            return self._handle_tools_list(request_id)
        if method == "tools/call":
            return self._handle_tools_call(request_id, params)
        if method == "resources/list":
            self._ensure_ready()
            _log("resources/list")
            return self._jsonrpc_result(request_id, {"resources": []})
        if method == "resources/templates/list":
            self._ensure_ready()
            _log("resources/templates/list")
            return self._jsonrpc_result(request_id, {"resourceTemplates": []})
        if request_id is None:
            return None
        raise McpProtocolError(-32601, f"Method not found: {method}")


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


if __name__ == "__main__":
    serve_forever()
