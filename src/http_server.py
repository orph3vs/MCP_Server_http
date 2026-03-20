"""Lightweight HTTP entrypoint for RequestPipeline."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.context_builder import build_context
from src.cost_logger import CostLogEntry, CostLogger
from src.law_hint_suggestions import LawHintSuggestion, LawHintSuggestionStore
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

    request = PipelineRequest(
        user_query=user_query,
        context=context,
        request_id=data.get("request_id"),
    )
    return request, data


def parse_tool_request(raw_body: bytes, required_fields: Tuple[str, ...]) -> Dict[str, str]:
    data = parse_json_body(raw_body)
    fields: Dict[str, str] = {}
    for key in required_fields:
        value = str(data.get(key, "")).strip()
        if not value:
            raise ValueError(f"missing_{key}")
        fields[key] = value
    return fields


def parse_recent_limit(path: str, default: int = 100, max_limit: int = 100) -> int:
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


def parse_recent_page(path: str, default: int = 1) -> int:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    raw = query.get("page", [str(default)])[0]
    try:
        page = int(raw)
    except ValueError as exc:
        raise ValueError("invalid_page") from exc
    if page <= 0:
        raise ValueError("invalid_page")
    return page


def parse_recent_view(path: str) -> str:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    view = query.get("view", ["raw"])[0].strip().lower()
    if view not in {"raw", "readable", "table", "html"}:
        raise ValueError("invalid_view")
    return view


def parse_suggestion_view(path: str) -> str:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    view = query.get("view", ["raw"])[0].strip().lower()
    if view not in {"raw", "readable", "html"}:
        raise ValueError("invalid_view")
    return view


def log_field_descriptions() -> Dict[str, str]:
    return {
        "entry_type": "로그 종류입니다. request는 질문 단위, tool은 개별 MCP 도구 호출입니다.",
        "tool_name": "도구 호출 로그일 때 실행된 MCP 도구 이름입니다.",
        "request_id": "요청 고유 ID입니다.",
        "question_summary": "질문 원문의 앞부분을 보여주는 미리보기입니다.",
        "risk_level": "질문 위험도입니다. HIGH면 더 보수적으로 검토합니다.",
        "mode": "처리 방식입니다. single_agent, multi_agent, tool, error:* 형태가 들어갑니다.",
        "question_intent": "질문 의도 분류입니다. 설명, 위법 여부, 절차, 비교 같은 유형을 뜻합니다.",
        "tokens_in": "입력 토큰 추정치입니다.",
        "tokens_out": "출력 토큰 추정치입니다.",
        "cost": "예상 토큰 비용입니다.",
        "latency": "응답 생성에 걸린 시간(ms)입니다.",
        "score": "신뢰도 점수입니다.",
        "error_stage": "오류가 발생했다면 어느 단계에서 났는지 보여줍니다.",
        "tool_calls": "이번 요청에서 발생한 전체 도구 호출 수입니다.",
        "nlic_calls": "국가법령정보센터 관련 호출 수입니다.",
        "law_search_count": "법령 검색 호출 수입니다.",
        "version_fetch_count": "버전 조회 호출 수입니다.",
        "article_fetch_count": "조문 조회 호출 수입니다.",
        "related_article_count": "추가로 조회한 관련 조문 수입니다.",
        "related_law_count": "추가로 조회한 관련 법령 수입니다.",
        "precedent_search_count": "판례 검색 호출 수입니다.",
        "precedent_fetch_count": "판례 상세 조회 호출 수입니다.",
        "has_precedent": "최종 답변에 판례가 포함되었는지 여부입니다.",
        "has_related_laws": "최종 답변에 관련 법령이 포함되었는지 여부입니다.",
    }


def _intent_label(intent: str) -> str:
    return {
        "explain": "설명형",
        "illegality": "위법 여부형",
        "difference": "비교형",
        "requirements": "요건형",
        "procedure": "절차형",
        "applicability": "적용 가능성형",
        "tool": "도구호출형",
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
    if not notes and entry.entry_type != "tool":
        notes.append("비교적 단순한 요청으로 보입니다.")
    return notes


def to_readable_log_item(entry: CostLogEntry) -> Dict[str, Any]:
    return {
        "로그종류": entry.entry_type,
        "도구명": entry.tool_name or "-",
        "요청ID": entry.request_id,
        "질문미리보기": entry.question_summary or "-",
        "위험도": entry.risk_level,
        "처리모드": entry.mode,
        "질문의도": _intent_label(entry.question_intent),
        "입력토큰수": entry.tokens_in,
        "출력토큰수": entry.tokens_out,
        "예상비용": entry.cost,
        "응답시간_ms": entry.latency,
        "신뢰도점수": entry.score,
        "오류단계": entry.error_stage,
        "총도구호출수": entry.tool_calls,
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


def suggestion_field_descriptions() -> Dict[str, str]:
    return {
        "suggestion_type": "추천이 생성된 유형입니다. 완전 검색 실패인지, 질문 기준 법령과 보완 근거가 어긋난 경우인지 보여줍니다.",
        "reason_code": "추천이 생성된 직접 사유 코드입니다.",
        "question_law_family": "질문에서 기준으로 본 법령군입니다.",
        "question_scope_direct_basis_found": "질문 기준 법령군 안에서 직접 근거를 찾았는지 여부입니다.",
        "supplementary_law_name": "직접 근거를 못 찾았을 때 보완적으로 따라간 법령명입니다.",
        "supplementary_article_no": "보완 법령에서 잡은 조문 번호입니다.",
        "matched_clause_labels": "직접 관련 항목으로 인식한 항/호 라벨입니다.",
        "approved_keywords": "승인 후 override에 반영된 키워드입니다.",
    }


def to_readable_suggestion_item(item: LawHintSuggestion) -> Dict[str, Any]:
    return {
        "상태": item.status,
        "유형": item.suggestion_type,
        "사유코드": item.reason_code or "-",
        "질문요약": item.question_summary,
        "질문의도": item.question_intent,
        "질문기준법령군": item.question_law_family or "-",
        "질문범위직접근거발견": item.question_scope_direct_basis_found,
        "질문범위조문": item.question_scope_article_no or "-",
        "보완법령": item.supplementary_law_name or "-",
        "보완조문": item.supplementary_article_no or "-",
        "직접관련항목": item.matched_clause_labels or [],
        "관련법후보": item.related_law_queries,
        "이슈키워드": item.issue_terms,
        "검색쿼리": item.search_queries,
        "제안키워드": item.proposed_keywords,
        "발생횟수": item.occurrence_count,
        "생성시각": item.created_at,
        "갱신시각": item.updated_at,
        "승인법령": item.approved_law_name or "-",
        "승인키워드": item.approved_keywords or [],
    }


def summarize_suggestions(items: list[LawHintSuggestion]) -> Dict[str, Any]:
    summary = {
        "count": len(items),
        "pending_count": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "law_search_gap_count": 0,
        "question_scope_gap_count": 0,
    }
    for item in items:
        if item.status == "pending":
            summary["pending_count"] += 1
        elif item.status == "approved":
            summary["approved_count"] += 1
        elif item.status == "rejected":
            summary["rejected_count"] += 1

        if item.suggestion_type == "law_search_gap":
            summary["law_search_gap_count"] += 1
        elif item.suggestion_type == "question_scope_gap":
            summary["question_scope_gap_count"] += 1
    return summary


def render_suggestion_html(
    items: list[LawHintSuggestion],
    *,
    approved_overrides: Dict[str, list[str]],
    status: Optional[str] = None,
) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    summary = summarize_suggestions(items)
    summary_cards = "".join(
        f"""
        <div class="card">
          <div class="label">{esc(label)}</div>
          <div class="value">{esc(value)}</div>
        </div>
        """
        for label, value in [
            ("전체 추천 수", summary["count"]),
            ("대기 중", summary["pending_count"]),
            ("승인됨", summary["approved_count"]),
            ("거절됨", summary["rejected_count"]),
            ("검색 실패형", summary["law_search_gap_count"]),
            ("질문범위 gap형", summary["question_scope_gap_count"]),
            ("승인 override 법령 수", len(approved_overrides)),
        ]
    )

    rows = []
    for item in items:
        related_laws = "".join(f"<li>{esc(name)}</li>" for name in item.related_law_queries) or "<li>-</li>"
        keywords = "".join(f"<li>{esc(name)}</li>" for name in item.proposed_keywords) or "<li>-</li>"
        clause_labels = "".join(f"<li>{esc(name)}</li>" for name in (item.matched_clause_labels or [])) or "<li>-</li>"
        approved_keywords = "".join(f"<li>{esc(name)}</li>" for name in (item.approved_keywords or [])) or "<li>-</li>"
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(item.status)}</strong></td>
              <td>{esc(item.suggestion_type)}</td>
              <td>{esc(item.reason_code or "-")}</td>
              <td>{esc(item.question_summary)}</td>
              <td>{esc(item.question_law_family or "-")}</td>
              <td>{esc(item.supplementary_law_name or "-")}</td>
              <td>{esc(item.supplementary_article_no or "-")}</td>
              <td>{esc(item.occurrence_count)}</td>
              <td>{esc(item.updated_at)}</td>
            </tr>
            <tr class="detail-row">
              <td colspan="9">
                <div class="detail-grid">
                  <div><div class="detail-label">질문 원문</div><div>{esc(item.user_query)}</div></div>
                  <div><div class="detail-label">질문 범위 직접 근거</div><div>{esc(item.question_scope_direct_basis_found)}</div></div>
                  <div><div class="detail-label">질문 범위 조문</div><div>{esc(item.question_scope_article_no or "-")}</div></div>
                  <div><div class="detail-label">직접 관련 항목</div><ul>{clause_labels}</ul></div>
                  <div><div class="detail-label">관련 법 후보</div><ul>{related_laws}</ul></div>
                  <div><div class="detail-label">제안 키워드</div><ul>{keywords}</ul></div>
                  <div><div class="detail-label">승인 법령</div><div>{esc(item.approved_law_name or "-")}</div></div>
                  <div><div class="detail-label">승인 키워드</div><ul>{approved_keywords}</ul></div>
                </div>
              </td>
            </tr>
            """
        )

    selected_status = status or "all"
    status_options = "".join(
        f'<option value="{esc(value)}" {"selected" if selected_status == value else ""}>{esc(label)}</option>'
        for value, label in [("all", "전체"), ("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")]
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Law Hint Suggestions</title>
  <style>
    body {{ font-family: sans-serif; margin: 0; background: #f6f1e8; color: #1f2a37; }}
    .page {{ max-width: 1440px; margin: 0 auto; padding: 28px; }}
    .hero, .panel, .card {{ background: rgba(255,255,255,0.76); border: 1px solid rgba(193, 153, 92, 0.22); border-radius: 24px; box-shadow: 0 20px 48px rgba(134, 97, 40, 0.08); }}
    .hero, .panel {{ padding: 24px 28px; margin-bottom: 20px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 20px; }}
    .card {{ padding: 18px 22px; }}
    .label {{ font-size: 14px; color: #7b5b2f; margin-bottom: 10px; }}
    .value {{ font-size: 20px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.88); border-radius: 20px; overflow: hidden; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid rgba(193, 153, 92, 0.18); vertical-align: top; text-align: left; }}
    th {{ background: rgba(246, 238, 224, 0.95); }}
    .detail-row td {{ background: rgba(251, 247, 239, 0.8); }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
    .detail-label {{ font-size: 12px; color: #7b5b2f; margin-bottom: 6px; font-weight: 700; }}
    ul {{ margin: 0; padding-left: 18px; }}
    select, button {{ font: inherit; padding: 10px 14px; border-radius: 14px; border: 1px solid rgba(193, 153, 92, 0.36); background: #fffaf1; }}
    .controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Law Hint Suggestions</h1>
      <p>법령 정규화 실패, 질문 기준 법령군과 보완 근거의 어긋남을 모아 운영자가 검토하는 대시보드입니다.</p>
    </div>
    <div class="summary-grid">{summary_cards}</div>
    <div class="panel">
      <div class="controls">
        <label for="status">상태 필터</label>
        <select id="status" onchange="location.href='?status=' + (this.value === 'all' ? '' : this.value) + '&view=html'">
          {status_options}
        </select>
        <button onclick="location.reload()">새로고침</button>
      </div>
    </div>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>상태</th>
            <th>유형</th>
            <th>사유코드</th>
            <th>질문요약</th>
            <th>질문기준법령군</th>
            <th>보완법령</th>
            <th>보완조문</th>
            <th>발생횟수</th>
            <th>최근갱신</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows) or '<tr><td colspan="9">표시할 추천이 없습니다.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


def suggestion_field_descriptions() -> Dict[str, str]:
    return {
        "suggestion_type": "추천이 생성된 유형입니다. 완전 검색 실패인지, 질문 기준 법령과 보완 근거가 갈린 경우인지 보여줍니다.",
        "reason_code": "추천이 생성된 직접 사유 코드입니다.",
        "question_law_family": "질문에서 기준으로 삼은 법령군입니다.",
        "question_scope_direct_basis_found": "질문 기준 법령군 안에서 직접 근거를 찾았는지 여부입니다.",
        "supplementary_law_name": "질문 기준 법령군 밖에서 보완적으로 따라간 법령입니다.",
        "supplementary_article_no": "보완 법령에서 확인된 조문 번호입니다.",
        "matched_clause_labels": "직접 관련 항목으로 식별된 항/호 목록입니다.",
        "proposed_keywords": "진단 과정에서 참고용으로 뽑은 키워드입니다. 자동 runtime 힌트가 아닙니다.",
        "recommended_change_type": "이 suggestion이 제안하는 보강 유형입니다.",
        "runtime_safe": "true이면 승인 시 runtime override rule로 반영 가능하고, false이면 코드/정책 검토가 필요합니다.",
        "approval_effect": "승인할 경우 어떤 효과가 생기는지 설명합니다.",
        "approved_rule_type": "승인 후 실제로 생성된 runtime rule 유형입니다.",
    }


def to_readable_suggestion_item(item: LawHintSuggestion) -> Dict[str, Any]:
    return {
        "상태": item.status,
        "유형": item.suggestion_type,
        "사유코드": item.reason_code or "-",
        "질문요약": item.question_summary,
        "질문의도": item.question_intent,
        "질문기준법령군": item.question_law_family or "-",
        "질문범위직접근거발견": item.question_scope_direct_basis_found,
        "질문범위조문": item.question_scope_article_no or "-",
        "보완법령": item.supplementary_law_name or "-",
        "보완조문": item.supplementary_article_no or "-",
        "직접관련항목": item.matched_clause_labels or [],
        "관련법후보": item.related_law_queries,
        "이슈키워드": item.issue_terms,
        "검색쿼리": item.search_queries,
        "진단키워드": item.proposed_keywords,
        "추천보강유형": item.recommended_change_type or "-",
        "runtime안전": item.runtime_safe,
        "승인효과": item.approval_effect or "-",
        "발생횟수": item.occurrence_count,
        "생성시각": item.created_at,
        "갱신시각": item.updated_at,
        "승인법령": item.approved_law_name or "-",
        "승인키워드": item.approved_keywords or [],
        "승인rule유형": item.approved_rule_type or "-",
        "승인ruleID": item.approved_rule_id or "-",
    }


def summarize_suggestions(items: list[LawHintSuggestion]) -> Dict[str, Any]:
    summary = {
        "count": len(items),
        "pending_count": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "law_search_gap_count": 0,
        "question_scope_gap_count": 0,
        "runtime_safe_count": 0,
    }
    for item in items:
        if item.status == "pending":
            summary["pending_count"] += 1
        elif item.status == "approved":
            summary["approved_count"] += 1
        elif item.status == "rejected":
            summary["rejected_count"] += 1

        if item.suggestion_type == "law_search_gap":
            summary["law_search_gap_count"] += 1
        elif item.suggestion_type == "question_scope_gap":
            summary["question_scope_gap_count"] += 1
        if item.runtime_safe:
            summary["runtime_safe_count"] += 1
    return summary


def render_suggestion_html(
    items: list[LawHintSuggestion],
    *,
    override_rule_count: int,
    status: Optional[str] = None,
) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    summary = summarize_suggestions(items)
    summary_cards = "".join(
        f"""
        <div class="card">
          <div class="label">{esc(label)}</div>
          <div class="value">{esc(value)}</div>
        </div>
        """
        for label, value in [
            ("전체 추천 수", summary["count"]),
            ("대기 중", summary["pending_count"]),
            ("승인됨", summary["approved_count"]),
            ("거절됨", summary["rejected_count"]),
            ("검색 실패형", summary["law_search_gap_count"]),
            ("질문범위 gap형", summary["question_scope_gap_count"]),
            ("runtime-safe", summary["runtime_safe_count"]),
            ("활성 rule 수", override_rule_count),
        ]
    )

    rows = []
    for item in items:
        related_laws = "".join(f"<li>{esc(name)}</li>" for name in item.related_law_queries) or "<li>-</li>"
        issue_terms = "".join(f"<li>{esc(name)}</li>" for name in item.issue_terms) or "<li>-</li>"
        keywords = "".join(f"<li>{esc(name)}</li>" for name in item.proposed_keywords) or "<li>-</li>"
        clause_labels = "".join(f"<li>{esc(name)}</li>" for name in (item.matched_clause_labels or [])) or "<li>-</li>"
        approved_keywords = "".join(f"<li>{esc(name)}</li>" for name in (item.approved_keywords or [])) or "<li>-</li>"
        payload_html = esc(json.dumps(item.recommended_change_payload or {}, ensure_ascii=False, indent=2))
        rows.append(
            f"""
            <tr>
              <td><strong>{esc(item.status)}</strong></td>
              <td>{esc(item.suggestion_type)}</td>
              <td>{esc(item.reason_code or "-")}</td>
              <td>{esc(item.question_summary)}</td>
              <td>{esc(item.question_law_family or "-")}</td>
              <td>{esc(item.supplementary_law_name or "-")}</td>
              <td>{esc(item.supplementary_article_no or "-")}</td>
              <td>{esc(item.recommended_change_type or "-")}</td>
              <td>{esc(item.runtime_safe)}</td>
              <td>{esc(item.updated_at)}</td>
            </tr>
            <tr class="detail-row">
              <td colspan="10">
                <div class="detail-grid">
                  <div><div class="detail-label">질문 원문</div><div>{esc(item.user_query)}</div></div>
                  <div><div class="detail-label">질문 범위 직접 근거</div><div>{esc(item.question_scope_direct_basis_found)}</div></div>
                  <div><div class="detail-label">질문 범위 조문</div><div>{esc(item.question_scope_article_no or "-")}</div></div>
                  <div><div class="detail-label">직접 관련 항목</div><ul>{clause_labels}</ul></div>
                  <div><div class="detail-label">관련 법 후보</div><ul>{related_laws}</ul></div>
                  <div><div class="detail-label">이슈 키워드</div><ul>{issue_terms}</ul></div>
                  <div><div class="detail-label">진단 키워드</div><ul>{keywords}</ul></div>
                  <div><div class="detail-label">승인 효과</div><div>{esc(item.approval_effect or "-")}</div></div>
                  <div><div class="detail-label">추천 payload</div><pre>{payload_html}</pre></div>
                  <div><div class="detail-label">승인 법령</div><div>{esc(item.approved_law_name or "-")}</div></div>
                  <div><div class="detail-label">승인 키워드</div><ul>{approved_keywords}</ul></div>
                  <div><div class="detail-label">승인 rule</div><div>{esc(item.approved_rule_type or "-")} / {esc(item.approved_rule_id or "-")}</div></div>
                </div>
              </td>
            </tr>
            """
        )

    selected_status = status or "all"
    status_options = "".join(
        f'<option value="{esc(value)}" {"selected" if selected_status == value else ""}>{esc(label)}</option>'
        for value, label in [("all", "전체"), ("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")]
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Law Hint Suggestions</title>
  <style>
    body {{ font-family: "Segoe UI", "Malgun Gothic", sans-serif; margin: 0; background: #f6f1e8; color: #1f2a37; }}
    .page {{ max-width: 1480px; margin: 0 auto; padding: 28px; }}
    .hero, .panel, .card {{ background: rgba(255,255,255,0.82); border: 1px solid rgba(193, 153, 92, 0.22); border-radius: 24px; box-shadow: 0 20px 48px rgba(134, 97, 40, 0.08); }}
    .hero, .panel {{ padding: 24px 28px; margin-bottom: 20px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 16px; margin-bottom: 20px; }}
    .card {{ padding: 18px 22px; }}
    .label {{ font-size: 13px; color: #7b5b2f; margin-bottom: 10px; }}
    .value {{ font-size: 20px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.88); border-radius: 20px; overflow: hidden; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid rgba(193, 153, 92, 0.18); vertical-align: top; text-align: left; }}
    th {{ background: rgba(246, 238, 224, 0.95); }}
    .detail-row td {{ background: rgba(251, 247, 239, 0.8); }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
    .detail-label {{ font-size: 12px; color: #7b5b2f; margin-bottom: 6px; font-weight: 700; }}
    ul {{ margin: 0; padding-left: 18px; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
    select, button {{ font: inherit; padding: 10px 14px; border-radius: 14px; border: 1px solid rgba(193, 153, 92, 0.36); background: #fffaf1; }}
    .controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Law Hint Suggestions</h1>
      <p>추천은 runtime 힌트가 아니라 진단 큐입니다. 무엇이 실패했고, 왜 추천이 떴으며, 승인하면 실제로 어떤 효과가 생기는지 구분해서 보여줍니다.</p>
    </div>
    <div class="summary-grid">{summary_cards}</div>
    <div class="panel">
      <div class="controls">
        <label for="status">상태 필터</label>
        <select id="status" onchange="location.href='?status=' + (this.value === 'all' ? '' : this.value) + '&view=html'">
          {status_options}
        </select>
        <button onclick="location.reload()">새로고침</button>
      </div>
    </div>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>상태</th>
            <th>유형</th>
            <th>사유코드</th>
            <th>질문요약</th>
            <th>질문기준법령군</th>
            <th>보완법령</th>
            <th>보완조문</th>
            <th>추천보강유형</th>
            <th>runtime-safe</th>
            <th>최근갱신</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows) or '<tr><td colspan="10">표시할 추천이 없습니다.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


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
            f"질문로그={summary.get('request_entry_count', 0)} | "
            f"도구로그={summary.get('tool_entry_count', 0)} | "
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
        ("질문미리보기", 26),
        ("위험도", 6),
        ("모드", 14),
        ("질문의도", 12),
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
            _truncate_cell(entry.question_summary or "-", 26),
            entry.risk_level,
            _truncate_cell(entry.mode, 14),
            _truncate_cell(_intent_label(entry.question_intent), 12),
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
        notes_list = _build_log_notes(entry)
        if notes_list:
            notes = ", ".join(notes_list)
            body_lines.append(
                f"    메모: {notes} | 판례={_bool_label(entry.has_precedent)} | 관련법={_bool_label(entry.has_related_laws)}"
            )

    if not rows:
        body_lines.append("로그가 없습니다.")

    return "\n".join(header_lines + body_lines)


def render_log_html(
    rows: list[CostLogEntry],
    summary: Dict[str, Any],
    page: int = 1,
    limit: int = 100,
    has_next: bool = False,
) -> str:
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
    cards = "".join(
        f"""
        <div class="card">
          <div class="label">{esc(label)}</div>
          <div class="value">{esc(value)}</div>
        </div>
        """
        for label, value in summary_items
    )

    row_chunks = []
    for entry in rows:
        notes_list = _build_log_notes(entry)
        notes = "".join(f"<li>{esc(note)}</li>" for note in notes_list)
        row_class = "error-row" if entry.error_stage else ""
        type_badge = "mode-tool" if entry.entry_type == "tool" else "mode-request"
        risk_badge = "risk-high" if entry.risk_level == "HIGH" else "risk-low"
        row_chunks.append(
            f"""
            <tr class="{row_class}" data-entry-type="{esc(entry.entry_type)}">
              <td>{esc(entry.request_id)}</td>
              <td><span class="badge {type_badge}">{esc(entry.entry_type)}</span></td>
              <td>{esc(entry.tool_name or "-")}</td>
              <td class="summary-cell">{esc(entry.question_summary or "-")}</td>
              <td><span class="badge {risk_badge}">{esc(entry.risk_level)}</span></td>
              <td><span class="badge mode">{esc(entry.mode)}</span></td>
              <td>{esc(_intent_label(entry.question_intent))}</td>
              <td>{entry.cost:.6f}</td>
              <td>{entry.latency:.1f}</td>
              <td>{esc(entry.nlic_calls)}</td>
              <td>{esc(entry.law_search_count)}</td>
              <td>{esc(entry.article_fetch_count)}</td>
              <td>{esc(entry.precedent_search_count)}</td>
              <td>{esc(entry.related_law_count)}</td>
              <td>{esc(entry.error_stage or "-")}</td>
            </tr>
            """
        )
        if notes_list:
            row_chunks.append(
                f"""
                <tr class="notes-row {row_class}" data-entry-type="{esc(entry.entry_type)}">
                  <td colspan="15">
                    <div class="notes-head">메모</div>
                    <ul>{notes}</ul>
                    <div class="flags">판례={esc(_bool_label(entry.has_precedent))} | 관련법={esc(_bool_label(entry.has_related_laws))}</div>
                  </td>
                </tr>
                """
            )

    if not row_chunks:
        row_chunks.append("<tr><td colspan='15' class='empty'>로그가 없습니다.</td></tr>")

    prev_page = max(page - 1, 1)
    next_page = page + 1
    prev_disabled = "disabled" if page <= 1 else ""
    next_disabled = "disabled" if not has_next else ""

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MyMcpServer Logs</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --panel-strong: #fffaf0;
      --line: #dfd6c7;
      --text: #22201c;
      --muted: #6d675f;
      --accent-soft: #f8e6de;
      --blue-soft: #e7eef8;
      --green-soft: #e7f3ea;
      --shadow: 0 16px 40px rgba(65, 50, 35, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px;
      background:
        radial-gradient(circle at top left, #efe5d8 0, transparent 30%),
        linear-gradient(180deg, #f8f5ef 0%, var(--bg) 100%);
      color: var(--text);
      font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    }}
    .wrap {{ max-width: 1540px; margin: 0 auto; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .hero-card, .toolbar, .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .hero-card {{ padding: 22px 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.1; }}
    .subtitle {{ color: var(--muted); line-height: 1.5; font-size: 14px; }}
    .toolbar {{
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 14px;
    }}
    .toolbar-head {{ font-size: 13px; color: var(--muted); }}
    .toolbar-controls, .pager {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
      box-shadow: 0 10px 26px rgba(65, 50, 35, 0.05);
    }}
    .label {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .value {{ font-size: 24px; font-weight: 700; letter-spacing: -0.03em; }}
    .table-wrap {{ overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1320px; }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #efe7d8;
      z-index: 1;
      font-size: 12px;
      color: #5d564e;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    tbody tr:hover td {{ background: #fbf4e8; }}
    tr.error-row td {{ background: #fff1f2; }}
    tr.notes-row td {{ background: #faf7f1; }}
    .summary-cell {{ max-width: 360px; line-height: 1.45; }}
    .notes-head {{ font-weight: 700; margin-bottom: 8px; }}
    ul {{ margin: 0; padding-left: 18px; line-height: 1.5; }}
    .flags {{ color: var(--muted); margin-top: 10px; font-size: 12px; }}
    .empty {{ text-align: center; color: var(--muted); padding: 28px 12px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
    }}
    .risk-high {{ background: var(--accent-soft); color: #923e24; border-color: #e9b6a3; }}
    .risk-low {{ background: var(--green-soft); color: #326744; border-color: #b8d9c2; }}
    .mode {{ background: #f2ede4; color: #5c5448; border-color: #ddd2c2; }}
    .mode-tool {{ background: var(--blue-soft); color: #365b8a; border-color: #bfd0ea; }}
    .mode-request {{ background: #f3ece2; color: #7c5a2b; border-color: #dfcfb6; }}
    button, select, .pager a {{
      padding: 9px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: white;
      color: var(--text);
      text-decoration: none;
    }}
    button, .pager a {{ cursor: pointer; background: #fff7ea; }}
    .pager .current {{ background: #efe7d8; font-weight: 700; }}
    .pager .disabled {{ pointer-events: none; opacity: 0.45; }}
    @media (max-width: 980px) {{
      body {{ padding: 18px; }}
      .hero {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="hero-card">
        <h1>MyMcpServer Logs</h1>
        <div class="subtitle">
          질문 로그와 MCP 도구 호출 로그를 한 화면에서 확인하는 대시보드입니다.
          비용, 응답시간, 법령·판례 호출 수, 오류 여부를 빠르게 읽을 수 있습니다.
        </div>
      </div>
      <div class="toolbar">
        <div class="toolbar-head">로그 종류 필터, 페이지 이동, 새로고침 버튼을 제공합니다.</div>
        <div class="toolbar-controls">
          <label for="entryTypeFilter">로그 종류 필터</label>
          <select id="entryTypeFilter">
            <option value="all">전체</option>
            <option value="request">질문 로그만</option>
            <option value="tool">도구 로그만</option>
          </select>
          <button type="button" onclick="window.location.reload()">새로고침</button>
        </div>
        <div class="pager">
          <a class="{prev_disabled}" href="?view=html&limit={limit}&page={prev_page}">이전 100개</a>
          <span class="current">페이지 {page}</span>
          <a class="{next_disabled}" href="?view=html&limit={limit}&page={next_page}">다음 100개</a>
        </div>
      </div>
    </div>
    <div class="cards">{cards}</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>요청ID</th>
            <th>종류</th>
            <th>도구</th>
            <th>질문미리보기</th>
            <th>위험도</th>
            <th>모드</th>
            <th>질문의도</th>
            <th>비용</th>
            <th>시간ms</th>
            <th>NLIC</th>
            <th>법검색</th>
            <th>조문</th>
            <th>판례</th>
            <th>관련법</th>
            <th>오류</th>
          </tr>
        </thead>
        <tbody>
          {''.join(row_chunks)}
        </tbody>
      </table>
    </div>
  </div>
  <script>
    const filter = document.getElementById('entryTypeFilter');
    filter.addEventListener('change', () => {{
      const selected = filter.value;
      document.querySelectorAll('tbody tr').forEach((row) => {{
        const kind = row.dataset.entryType;
        row.style.display = selected === 'all' || kind === selected ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>"""


class PipelineHttpHandler(BaseHTTPRequestHandler):
    _pipeline: Optional[RequestPipeline] = None
    _logger: Optional[CostLogger] = None
    _suggestion_store: Optional[LawHintSuggestionStore] = None

    @classmethod
    def get_pipeline(cls) -> RequestPipeline:
        if cls._pipeline is None:
            cls._pipeline = RequestPipeline()
        return cls._pipeline

    @classmethod
    def get_logger(cls) -> CostLogger:
        if cls._logger is None:
            cls._logger = CostLogger()
        return cls._logger

    @classmethod
    def get_suggestion_store(cls) -> LawHintSuggestionStore:
        if cls._suggestion_store is None:
            cls._suggestion_store = LawHintSuggestionStore()
        return cls._suggestion_store

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            _json_response(self, 200, {"status": "ok"})
            return

        if parsed.path == "/logs/recent":
            try:
                limit = parse_recent_limit(self.path)
                page = parse_recent_page(self.path)
                offset = (page - 1) * limit
                view = parse_recent_view(self.path)
                logger = self.get_logger()
                rows_plus = logger.list_recent(limit=limit + 1, offset=offset)
                has_next = len(rows_plus) > limit
                rows = rows_plus[:limit]
                summary = logger.summarize_all()
                if view == "table":
                    _text_response(self, 200, render_log_table(rows, summary))
                    return
                if view == "html":
                    _html_response(
                        self,
                        200,
                        render_log_html(rows, summary, page=page, limit=limit, has_next=has_next),
                    )
                    return
                payload: Dict[str, Any] = {
                    "count": len(rows),
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                    "items": [asdict(r) for r in rows],
                }
                if view == "readable":
                    payload["descriptions"] = log_field_descriptions()
                    payload["readable_summary"] = to_readable_summary(summary)
                    payload["readable_items"] = [to_readable_log_item(r) for r in rows]
                _json_response(self, 200, payload)
                return
            except ValueError as exc:
                _json_response(self, 400, {"error": str(exc)})
                return

        if parsed.path == "/suggestions/law-hints":
            try:
                query = parse_qs(parsed.query)
                status = query.get("status", [None])[0]
                if status == "all":
                    status = None
                view = parse_suggestion_view(self.path)
                suggestion_store = self.get_suggestion_store()
                suggestions = suggestion_store.list_suggestions(status=status)
                override_rules = suggestion_store.active_override_rules()
                summary = summarize_suggestions(suggestions)
                if view == "html":
                    _html_response(
                        self,
                        200,
                        render_suggestion_html(
                            suggestions,
                            override_rule_count=len(override_rules),
                            status=status,
                        ),
                    )
                    return

                payload: Dict[str, Any] = {
                    "count": len(suggestions),
                    "summary": summary,
                    "items": [asdict(item) for item in suggestions],
                    "override_rules": [asdict(item) for item in override_rules],
                }
                if view == "readable":
                    payload["descriptions"] = suggestion_field_descriptions()
                    payload["readable_items"] = [to_readable_suggestion_item(item) for item in suggestions]
                _json_response(self, 200, payload)
                return
            except ValueError as exc:
                _json_response(self, 400, {"error": str(exc)})
                return

        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))

        try:
            if parsed.path == "/ask":
                request, _data = parse_ask_request(raw_body)
                response = self.get_pipeline().process(request)
                _json_response(self, 200, asdict(response))
                return

            if parsed.path == "/tools/search_law":
                fields = parse_tool_request(raw_body, ("query",))
                data = self.get_pipeline().law_api.search_law(fields["query"])
                _json_response(self, 200, {"data": data})
                return

            if parsed.path == "/tools/get_article":
                fields = parse_tool_request(raw_body, ("law_id", "article_no"))
                data = self.get_pipeline().law_api.get_article(
                    law_id=fields["law_id"],
                    article_no=fields["article_no"],
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
                    law_id=fields["law_id"],
                    article_no=fields["article_no"],
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
        except Exception as exc:
            _json_response(self, 500, {"error": f"internal_error:{exc}"})


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), PipelineHttpHandler)
    print(f"[request-pipeline-server] listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
