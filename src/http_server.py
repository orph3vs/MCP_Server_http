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

import html
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.context_builder import build_context
from src.cost_logger import CostLogEntry
from src.law_hint_suggestions import LawHintSuggestion
from src.request_pipeline import PipelineRequest, RequestPipeline


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
    payload = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _html_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
    payload = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


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


def parse_recent_view(path: str) -> str:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    view = query.get("view", ["raw"])[0].strip().lower()
    if view not in {"raw", "readable", "table", "html"}:
        raise ValueError("invalid_view")
    return view


def log_field_descriptions() -> Dict[str, str]:
    return {
        "entry_type": "로그 종류입니다. request는 질문 단위, tool은 개별 MCP 도구 호출입니다.",
        "tool_name": "개별 MCP 도구 호출일 때 어떤 도구였는지 표시합니다.",
        "request_id": "요청 고유 ID입니다.",
        "question_summary": "원문 전체 대신 남기는 짧은 질문 요약입니다.",
        "risk_level": "질문 위험도입니다. HIGH면 보수적으로 검토합니다.",
        "mode": "처리 방식입니다. single_agent 또는 multi_agent, 오류 모드가 들어갑니다.",
        "question_intent": "질문 의도 분류입니다. 설명, 위법 여부, 절차, 비교 같은 유형을 뜻합니다.",
        "tokens_in": "입력으로 계산한 토큰 추정치입니다.",
        "tokens_out": "출력 답변의 토큰 추정치입니다.",
        "cost": "현재 규칙으로 계산한 예상 토큰 비용입니다.",
        "latency": "응답 생성에 걸린 시간(ms)입니다.",
        "score": "신뢰도 점수입니다.",
        "error_stage": "실패 시 어느 단계에서 실패했는지 나타냅니다.",
        "tool_calls": "이번 요청에서 발생한 총 외부 조회 호출 수입니다.",
        "nlic_calls": "국가법령정보센터 관련 호출 총합입니다.",
        "law_search_count": "법령 검색 호출 횟수입니다.",
        "version_fetch_count": "버전 조회 호출 횟수입니다.",
        "article_fetch_count": "조문 조회 호출 횟수입니다.",
        "related_article_count": "추가로 함께 조회한 관련 조문 수입니다.",
        "related_law_count": "함께 참고한 관련 법령 수입니다.",
        "precedent_search_count": "판례 검색 호출 횟수입니다.",
        "precedent_fetch_count": "판례 상세 조회 호출 횟수입니다.",
        "has_precedent": "이번 답변에 판례가 실제로 붙었는지 여부입니다.",
        "has_related_laws": "주된 법 외에 관련 법령이 함께 붙었는지 여부입니다.",
    }


def _intent_label(intent: str) -> str:
    return {
        "explain": "설명형",
        "illegality": "위법 여부형",
        "difference": "비교형",
        "requirements": "요건형",
        "procedure": "절차형",
        "applicability": "적용 가능성형",
    }.get(intent, intent)


def _build_log_notes(entry: CostLogEntry) -> list[str]:
    notes: list[str] = []
    if entry.mode == "multi_agent":
        notes.append("멀티에이전트 검토가 적용된 요청입니다.")
    if entry.precedent_search_count > 0:
        notes.append("판례 검색이 포함되어 비용과 지연시간이 늘 수 있습니다.")
    if entry.related_law_count > 0:
        notes.append("관련 법령을 함께 조회한 요청입니다.")
    if entry.related_article_count > 0:
        notes.append("추가 조문 조회가 포함되었습니다.")
    if entry.error_stage:
        notes.append(f"{entry.error_stage} 단계에서 오류가 발생한 요청입니다.")
    if not notes:
        notes.append("비교적 단순한 요청으로 보입니다.")
    return notes


def to_readable_log_item(entry: CostLogEntry) -> Dict[str, Any]:
    return {
        "로그종류": entry.entry_type,
        "도구명": entry.tool_name,
        "요청ID": entry.request_id,
        "질문요약": entry.question_summary,
        "위험도": entry.risk_level,
        "처리모드": entry.mode,
        "질문유형": _intent_label(entry.question_intent),
        "입력토큰수": entry.tokens_in,
        "출력토큰수": entry.tokens_out,
        "예상비용": entry.cost,
        "응답시간_ms": entry.latency,
        "신뢰도점수": entry.score,
        "오류단계": entry.error_stage,
        "총외부호출수": entry.tool_calls,
        "법령검색수": entry.law_search_count,
        "버전조회수": entry.version_fetch_count,
        "조문조회수": entry.article_fetch_count,
        "추가조문수": entry.related_article_count,
        "관련법령수": entry.related_law_count,
        "판례검색수": entry.precedent_search_count,
        "판례상세조회수": entry.precedent_fetch_count,
        "판례포함여부": entry.has_precedent,
        "관련법령포함여부": entry.has_related_laws,
        "해석메모": _build_log_notes(entry),
    }


def to_readable_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "최근요청수": summary.get("count", 0),
        "질문로그수": summary.get("request_entry_count", 0),
        "도구로그수": summary.get("tool_entry_count", 0),
        "총예상비용": summary.get("total_cost", 0.0),
        "평균예상비용": summary.get("avg_cost", 0.0),
        "평균응답시간_ms": summary.get("avg_latency", 0.0),
        "평균NLIC호출수": summary.get("avg_nlic_calls", 0.0),
        "멀티에이전트요청수": summary.get("multi_agent_count", 0),
        "고위험요청수": summary.get("high_risk_count", 0),
        "오류요청수": summary.get("error_count", 0),
        "판례검색포함요청수": summary.get("precedent_request_count", 0),
    }


def _bool_label(value: bool) -> str:
    return "Y" if value else "-"


def _truncate_cell(value: Any, max_width: int) -> str:
    text = str(value)
    if len(text) <= max_width:
        return text
    return text[: max_width - 3] + "..."


def render_log_table(rows: list[CostLogEntry], summary: Dict[str, Any]) -> str:
    header_lines = [
        "[최근 요청 요약]",
        (
            f"요청수={summary.get('count', 0)} | "
            f"총예상비용={summary.get('total_cost', 0.0)} | "
            f"평균응답시간_ms={summary.get('avg_latency', 0.0)} | "
            f"평균NLIC호출수={summary.get('avg_nlic_calls', 0.0)} | "
            f"멀티에이전트={summary.get('multi_agent_count', 0)} | "
            f"고위험={summary.get('high_risk_count', 0)} | "
            f"오류={summary.get('error_count', 0)}"
        ),
        "",
    ]

    columns = [
        ("요청ID", 10),
        ("종류", 7),
        ("도구", 18),
        ("질문요약", 24),
        ("위험도", 6),
        ("모드", 12),
        ("질문유형", 10),
        ("비용", 10),
        ("시간ms", 10),
        ("NLIC", 6),
        ("법검색", 6),
        ("조문", 6),
        ("판례", 6),
        ("관련법", 6),
        ("오류", 12),
    ]

    def row_values(entry: CostLogEntry) -> list[str]:
        return [
            _truncate_cell(entry.request_id, 10),
            _truncate_cell(entry.entry_type, 7),
            _truncate_cell(entry.tool_name or "-", 18),
            _truncate_cell(entry.question_summary or "-", 24),
            entry.risk_level,
            _truncate_cell(entry.mode, 12),
            _truncate_cell(_intent_label(entry.question_intent), 10),
            f"{entry.cost:.6f}",
            f"{entry.latency:.1f}",
            str(entry.nlic_calls),
            str(entry.law_search_count),
            str(entry.article_fetch_count),
            str(entry.precedent_search_count),
            str(entry.related_law_count),
            _truncate_cell(entry.error_stage or "-", 12),
        ]

    header = " | ".join(_truncate_cell(name, width).ljust(width) for name, width in columns)
    divider = "-+-".join("-" * width for _, width in columns)
    body_lines = [header, divider]

    for entry in rows:
        values = row_values(entry)
        body_lines.append(
            " | ".join(value.ljust(width) for value, (_, width) in zip(values, columns))
        )
        notes = ", ".join(_build_log_notes(entry))
        flags = (
            f"    메모: {notes} | "
            f"판례={_bool_label(entry.has_precedent)} | "
            f"관련법={_bool_label(entry.has_related_laws)}"
        )
        body_lines.append(flags)

    if not rows:
        body_lines.append("로그가 없습니다.")

    return "\n".join(header_lines + body_lines)


def render_log_html(rows: list[CostLogEntry], summary: Dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    summary_items = [
        ("최근 요청 수", summary.get("count", 0)),
        ("질문 로그 수", summary.get("request_entry_count", 0)),
        ("도구 로그 수", summary.get("tool_entry_count", 0)),
        ("총 예상 비용", summary.get("total_cost", 0.0)),
        ("평균 응답시간(ms)", summary.get("avg_latency", 0.0)),
        ("평균 NLIC 호출 수", summary.get("avg_nlic_calls", 0.0)),
        ("멀티에이전트 수", summary.get("multi_agent_count", 0)),
        ("고위험 수", summary.get("high_risk_count", 0)),
        ("오류 수", summary.get("error_count", 0)),
    ]

    cards = []
    for label, value in summary_items:
        cards.append(
            f"<div class='card'><div class='label'>{esc(label)}</div><div class='value'>{esc(value)}</div></div>"
        )

    rows_html = []
    for entry in rows:
        notes = "".join(f"<li>{esc(note)}</li>" for note in _build_log_notes(entry))
        row_class = "error-row" if entry.error_stage else ""
        rows_html.append(
            f"<tr class='{row_class}' data-entry-type='{esc(entry.entry_type)}'>"
            f"<td>{esc(entry.request_id)}</td>"
            f"<td>{esc(entry.entry_type)}</td>"
            f"<td>{esc(entry.tool_name or '-')}</td>"
            f"<td>{esc(entry.question_summary or '-')}</td>"
            f"<td>{esc(entry.risk_level)}</td>"
            f"<td>{esc(entry.mode)}</td>"
            f"<td>{esc(_intent_label(entry.question_intent))}</td>"
            f"<td>{entry.cost:.6f}</td>"
            f"<td>{entry.latency:.1f}</td>"
            f"<td>{esc(entry.nlic_calls)}</td>"
            f"<td>{esc(entry.law_search_count)}</td>"
            f"<td>{esc(entry.article_fetch_count)}</td>"
            f"<td>{esc(entry.precedent_search_count)}</td>"
            f"<td>{esc(entry.related_law_count)}</td>"
            f"<td>{esc(entry.error_stage or '-')}</td>"
            f"<td><ul>{notes}</ul></td>"
            "</tr>"
        )

    table_rows = "\n".join(rows_html) if rows_html else "<tr><td colspan='16'>로그가 없습니다.</td></tr>"

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MyMcpServer Logs</title>
  <style>
    :root {{
      --bg: #f5f2ea;
      --panel: #fffdf8;
      --ink: #1f2a2e;
      --muted: #5c6b70;
      --line: #d9d1c3;
      --accent: #a64b2a;
      --accent-soft: #f3dfd6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, #f6d8c6 0, transparent 28%),
        linear-gradient(180deg, #f8f5ef 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 20px 36px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 32px;
    }}
    .sub {{
      color: var(--muted);
      margin-bottom: 18px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      box-shadow: 0 8px 24px rgba(63, 42, 18, 0.06);
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 22px;
      font-weight: 700;
    }}
    .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: auto;
      box-shadow: 0 10px 28px rgba(63, 42, 18, 0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1220px;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      font-size: 14px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f2ece1;
      color: #29343a;
      z-index: 1;
    }}
    tr:nth-child(even) td {{
      background: #fffaf1;
    }}
    tr.error-row td {{
      background: #fff0eb;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 600;
      font-size: 12px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-bottom: 14px;
    }}
    .toolbar label {{
      font-size: 14px;
      color: var(--muted);
    }}
    .toolbar select,
    .toolbar button {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 10px;
      padding: 8px 12px;
      font: inherit;
    }}
    .toolbar button {{
      cursor: pointer;
      background: #f3dfd6;
      color: #6c2e18;
      font-weight: 600;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>MyMcpServer Logs</h1>
    <div class="sub">최근 요청과 MCP 도구 호출을 한눈에 확인할 수 있는 로그 뷰입니다.</div>
    <div class="cards">
      {''.join(cards)}
    </div>
    <div class="toolbar">
      <label for="entryFilter">로그 종류 필터</label>
      <select id="entryFilter">
        <option value="all">전체</option>
        <option value="request">질문 로그만</option>
        <option value="tool">도구 로그만</option>
      </select>
      <button type="button" onclick="window.location.reload()">새로고침</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>요청ID</th>
            <th>종류</th>
            <th>도구</th>
            <th>질문요약</th>
            <th>위험도</th>
            <th>모드</th>
            <th>질문유형</th>
            <th>비용</th>
            <th>시간ms</th>
            <th>NLIC</th>
            <th>법검색</th>
            <th>조문</th>
            <th>판례</th>
            <th>관련법</th>
            <th>오류</th>
            <th>메모</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
  </div>
  <script>
    const entryFilter = document.getElementById('entryFilter');
    const rows = Array.from(document.querySelectorAll('tbody tr[data-entry-type]'));
    entryFilter.addEventListener('change', () => {{
      const selected = entryFilter.value;
      rows.forEach((row) => {{
        const entryType = row.getAttribute('data-entry-type');
        row.style.display = (selected === 'all' || entryType === selected) ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>"""


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
                view = parse_recent_view(self.path)
                rows = self.get_pipeline().logger.list_recent(limit=limit)
                summary = self.get_pipeline().logger.summarize_recent(limit=limit)
                if view == "table":
                    _text_response(self, 200, render_log_table(rows, summary))
                    return
                if view == "html":
                    _html_response(self, 200, render_log_html(rows, summary))
                    return
                payload: Dict[str, Any] = {
                    "count": len(rows),
                    "summary": summary,
                    "items": [asdict(r) for r in rows],
                }
                if view == "readable":
                    payload["descriptions"] = log_field_descriptions()
                    payload["readable_summary"] = to_readable_summary(summary)
                    payload["readable_items"] = [to_readable_log_item(r) for r in rows]
                _json_response(
                    self,
                    200,
                    payload,
                )
            except ValueError as exc:
                _json_response(self, 400, {"error": str(exc)})
            return

        if parsed.path == "/suggestions/law-hints":
            try:
                query = parse_qs(parsed.query)
                status = query.get("status", [None])[0]
                suggestions = self.get_pipeline().suggestion_store.list_suggestions(status=status)
                _json_response(
                    self,
                    200,
                    {
                        "count": len(suggestions),
                        "items": [asdict(item) for item in suggestions],
                        "approved_overrides": self.get_pipeline().suggestion_store.approved_overrides(),
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

            if parsed.path == "/suggestions/law-hints/approve":
                data = parse_json_body(raw_body)
                suggestion_id = str(data.get("suggestion_id", "")).strip()
                if not suggestion_id:
                    raise ValueError("missing_suggestion_id")
                keywords = data.get("keywords")
                if keywords is not None and not isinstance(keywords, list):
                    raise ValueError("invalid_keywords")
                suggestion = self.get_pipeline().suggestion_store.approve_suggestion(
                    suggestion_id,
                    law_name=str(data.get("law_name", "")).strip() or None,
                    keywords=[str(keyword) for keyword in keywords] if keywords else None,
                )
                _json_response(self, 200, {"data": asdict(suggestion)})
                return

            if parsed.path == "/suggestions/law-hints/reject":
                data = parse_json_body(raw_body)
                suggestion_id = str(data.get("suggestion_id", "")).strip()
                if not suggestion_id:
                    raise ValueError("missing_suggestion_id")
                suggestion = self.get_pipeline().suggestion_store.reject_suggestion(suggestion_id)
                _json_response(self, 200, {"data": asdict(suggestion)})
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
