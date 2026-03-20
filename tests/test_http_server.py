import json
import tempfile
import unittest
from pathlib import Path

from src.cost_logger import CostLogEntry
from src.http_server import (
    PipelineHttpHandler,
    parse_ask_request,
    parse_recent_limit,
    parse_recent_page,
    parse_recent_view,
    parse_suggestion_view,
    parse_tool_request,
    render_log_html,
    render_log_table,
    render_suggestion_html,
    summarize_suggestions,
    to_readable_log_item,
    to_readable_suggestion_item,
    to_readable_summary,
)
from src.law_hint_suggestions import LawHintSuggestion, LawHintSuggestionStore


class HttpServerParsingTests(unittest.TestCase):
    def test_parse_ask_request_success(self):
        req, data = parse_ask_request(
            json.dumps(
                {
                    "user_query": "개인정보 제3자 제공 기준",
                    "context": "기준시점: 2025-01-01",
                    "request_id": "req-123",
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )
        self.assertEqual(req.user_query, "개인정보 제3자 제공 기준")
        self.assertIn("기준시점: 2025-01-01", req.context or "")
        self.assertEqual(req.request_id, "req-123")
        self.assertIn("user_query", data)

    def test_parse_ask_request_success_cp949(self):
        payload = {
            "user_query": "개인정보 위탁과 제3자 제공 차이",
            "context": "기준시점: 2025-01-01",
        }
        req, data = parse_ask_request(
            json.dumps(payload, ensure_ascii=False).encode("cp949")
        )
        self.assertEqual(req.user_query, payload["user_query"])
        self.assertIn(payload["context"], req.context or "")
        self.assertEqual(data["context"], payload["context"])

    def test_parse_ask_request_with_metadata_and_history(self):
        req, _ = parse_ask_request(
            json.dumps(
                {
                    "user_query": "질문",
                    "metadata": {"tenant": "acme", "locale": "ko-KR"},
                    "history": ["이전 질문1", "이전 질문2"],
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )
        self.assertIn("[METADATA]", req.context or "")
        self.assertIn("tenant", req.context or "")
        self.assertIn("[RECENT_HISTORY]", req.context or "")

    def test_parse_tool_request(self):
        fields = parse_tool_request(
            json.dumps(
                {"law_id": "L1", "article_no": "제1조"},
                ensure_ascii=False,
            ).encode("utf-8"),
            ("law_id", "article_no"),
        )
        self.assertEqual(fields["law_id"], "L1")
        self.assertEqual(fields["article_no"], "제1조")

    def test_parse_recent_limit(self):
        self.assertEqual(parse_recent_limit("/logs/recent?limit=7"), 7)
        self.assertEqual(parse_recent_limit("/logs/recent?limit=1000"), 100)

    def test_parse_recent_page(self):
        self.assertEqual(parse_recent_page("/logs/recent?page=2"), 2)

    def test_parse_recent_view(self):
        self.assertEqual(parse_recent_view("/logs/recent"), "raw")
        self.assertEqual(parse_recent_view("/logs/recent?view=readable"), "readable")
        self.assertEqual(parse_recent_view("/logs/recent?view=table"), "table")
        self.assertEqual(parse_recent_view("/logs/recent?view=html"), "html")

    def test_parse_suggestion_view(self):
        self.assertEqual(parse_suggestion_view("/suggestions/law-hints"), "raw")
        self.assertEqual(
            parse_suggestion_view("/suggestions/law-hints?view=readable"),
            "readable",
        )
        self.assertEqual(
            parse_suggestion_view("/suggestions/law-hints?view=html"),
            "html",
        )
        with self.assertRaises(ValueError):
            parse_suggestion_view("/suggestions/law-hints?view=table")

    def test_get_logger_does_not_require_pipeline_initialization(self):
        original_pipeline = PipelineHttpHandler._pipeline
        original_logger = PipelineHttpHandler._logger
        try:
            PipelineHttpHandler._pipeline = None
            PipelineHttpHandler._logger = None
            logger = PipelineHttpHandler.get_logger()
            self.assertIsNotNone(logger)
            self.assertIsNone(PipelineHttpHandler._pipeline)
        finally:
            PipelineHttpHandler._pipeline = original_pipeline
            PipelineHttpHandler._logger = original_logger

    def test_get_suggestion_store_does_not_require_pipeline_initialization(self):
        original_pipeline = PipelineHttpHandler._pipeline
        original_store = PipelineHttpHandler._suggestion_store
        try:
            PipelineHttpHandler._pipeline = None
            PipelineHttpHandler._suggestion_store = None
            store = PipelineHttpHandler.get_suggestion_store()
            self.assertIsNotNone(store)
            self.assertIsNone(PipelineHttpHandler._pipeline)
        finally:
            PipelineHttpHandler._pipeline = original_pipeline
            PipelineHttpHandler._suggestion_store = original_store

    def test_to_readable_log_item(self):
        item = to_readable_log_item(
            CostLogEntry(
                request_id="req-1",
                entry_type="tool",
                tool_name="search_law",
                risk_level="HIGH",
                mode="multi_agent",
                tokens_in=10,
                tokens_out=20,
                cost=0.001,
                latency=30.5,
                score=88.0,
                question_summary="개인정보 보호법 위법 여부 질문",
                question_intent="illegality",
                law_search_count=2,
                related_law_count=1,
                precedent_search_count=1,
                has_precedent=True,
            )
        )
        self.assertEqual(item["로그종류"], "tool")
        self.assertEqual(item["도구명"], "search_law")
        self.assertEqual(item["질문미리보기"], "개인정보 보호법 위법 여부 질문")
        self.assertEqual(item["질문의도"], "위법 여부형")
        self.assertTrue(item["판례포함여부"])
        self.assertTrue(any("판례 검색" in note for note in item["해석메모"]))

    def test_to_readable_log_item_tool_without_special_notes(self):
        item = to_readable_log_item(
            CostLogEntry(
                request_id="req-2",
                entry_type="tool",
                tool_name="get_article",
                risk_level="LOW",
                mode="tool",
                tokens_in=0,
                tokens_out=0,
                cost=0.0,
                latency=12.0,
                score=0.0,
                question_summary="제1조 원문 조회",
                question_intent="tool",
            )
        )
        self.assertEqual(item["해석메모"], [])

    def test_to_readable_summary(self):
        readable = to_readable_summary(
            {
                "count": 2,
                "request_entry_count": 1,
                "tool_entry_count": 1,
                "total_cost": 0.003,
                "avg_cost": 0.0015,
                "avg_latency": 40.0,
                "avg_nlic_calls": 3.0,
                "multi_agent_count": 1,
                "high_risk_count": 1,
                "error_count": 0,
                "precedent_request_count": 1,
            }
        )
        self.assertEqual(readable["최근요청수"], 2)
        self.assertEqual(readable["질문로그수"], 1)
        self.assertEqual(readable["도구로그수"], 1)
        self.assertEqual(readable["판례검색포함요청수"], 1)

    def test_render_log_table(self):
        table = render_log_table(
            [
                CostLogEntry(
                    request_id="req-1",
                    entry_type="tool",
                    tool_name="search_law",
                    risk_level="HIGH",
                    mode="multi_agent",
                    tokens_in=10,
                    tokens_out=20,
                    cost=0.001,
                    latency=30.5,
                    score=88.0,
                    question_summary="개인정보 보호법 위법 여부 질문",
                    question_intent="illegality",
                    nlic_calls=4,
                    law_search_count=2,
                    article_fetch_count=1,
                    precedent_search_count=1,
                    related_law_count=1,
                    has_precedent=True,
                    has_related_laws=True,
                )
            ],
            {
                "count": 1,
                "request_entry_count": 0,
                "tool_entry_count": 1,
                "total_cost": 0.001,
                "avg_latency": 30.5,
                "avg_nlic_calls": 4.0,
                "multi_agent_count": 1,
                "high_risk_count": 1,
                "error_count": 0,
            },
        )
        self.assertIn("[최근 요청 요약]", table)
        self.assertIn("요청ID", table)
        self.assertIn("종류", table)
        self.assertIn("도구", table)
        self.assertIn("질문미리보기", table)
        self.assertIn("개인정보 보호법 위법 여부 질문", table)
        self.assertIn("req-1", table)
        self.assertIn("메모:", table)

    def test_render_log_table_skips_empty_note_line_for_plain_tool(self):
        table = render_log_table(
            [
                CostLogEntry(
                    request_id="req-plain",
                    entry_type="tool",
                    tool_name="get_article",
                    risk_level="LOW",
                    mode="tool",
                    tokens_in=0,
                    tokens_out=0,
                    cost=0.0,
                    latency=10.0,
                    score=0.0,
                    question_summary="제1조 원문 조회",
                    question_intent="tool",
                )
            ],
            {
                "count": 1,
                "request_entry_count": 0,
                "tool_entry_count": 1,
                "total_cost": 0.0,
                "avg_latency": 10.0,
                "avg_nlic_calls": 0.0,
                "multi_agent_count": 0,
                "high_risk_count": 0,
                "error_count": 0,
            },
        )
        self.assertNotIn("메모:", table)

    def test_render_log_html(self):
        html_doc = render_log_html(
            [
                CostLogEntry(
                    request_id="req-1",
                    entry_type="tool",
                    tool_name="search_law",
                    risk_level="HIGH",
                    mode="multi_agent",
                    tokens_in=10,
                    tokens_out=20,
                    cost=0.001,
                    latency=30.5,
                    score=88.0,
                    question_summary="개인정보 보호법 위법 여부 질문",
                    question_intent="illegality",
                    nlic_calls=4,
                    law_search_count=2,
                    article_fetch_count=1,
                    precedent_search_count=1,
                    related_law_count=1,
                    has_precedent=True,
                    has_related_laws=True,
                )
            ],
            {
                "count": 1,
                "request_entry_count": 0,
                "tool_entry_count": 1,
                "total_cost": 0.001,
                "avg_latency": 30.5,
                "avg_nlic_calls": 4.0,
                "multi_agent_count": 1,
                "high_risk_count": 1,
                "error_count": 0,
            },
            has_next=False,
        )
        self.assertIn("<!doctype html>", html_doc.lower())
        self.assertIn("MyMcpServer Logs", html_doc)
        self.assertIn("개인정보 보호법 위법 여부 질문", html_doc)
        self.assertIn("search_law", html_doc)
        self.assertIn("로그 종류 필터", html_doc)
        self.assertIn("새로고침", html_doc)
        self.assertIn("error-row", html_doc)
        self.assertIn("다음 100개", html_doc)
        self.assertIn("disabled", html_doc)

    def test_render_log_html_skips_empty_notes_row_for_plain_tool(self):
        html_doc = render_log_html(
            [
                CostLogEntry(
                    request_id="req-plain",
                    entry_type="tool",
                    tool_name="get_article",
                    risk_level="LOW",
                    mode="tool",
                    tokens_in=0,
                    tokens_out=0,
                    cost=0.0,
                    latency=10.0,
                    score=0.0,
                    question_summary="제1조 원문 조회",
                    question_intent="tool",
                )
            ],
            {
                "count": 1,
                "request_entry_count": 0,
                "tool_entry_count": 1,
                "total_cost": 0.0,
                "avg_latency": 10.0,
                "avg_nlic_calls": 0.0,
                "multi_agent_count": 0,
                "high_risk_count": 0,
                "error_count": 0,
            },
        )
        self.assertNotIn("<div class=\"notes-head\">메모</div>", html_doc)

    def test_parse_ask_request_missing_query(self):
        with self.assertRaises(ValueError):
            parse_ask_request(json.dumps({"context": "x"}).encode("utf-8"))

    def test_parse_ask_request_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_ask_request(b"{bad-json")

    def test_to_readable_suggestion_item_and_summary(self):
        suggestion = LawHintSuggestion(
            id="s1",
            fingerprint="fp1",
            request_id="req-1",
            question_summary="Need decree basis",
            user_query="Can this agency collect an identifier?",
            question_intent="applicability",
            related_law_queries=["Example Decree"],
            issue_terms=["identifier"],
            search_queries=["example decree identifier"],
            proposed_keywords=["example", "identifier"],
            status="pending",
            occurrence_count=3,
            created_at="2026-03-20T00:00:00+00:00",
            updated_at="2026-03-20T01:00:00+00:00",
            suggestion_type="question_scope_gap",
            reason_code="question_scope_missing_direct_basis",
            question_law_family="Example Law",
            question_scope_direct_basis_found=False,
            question_scope_article_no="제10조",
            supplementary_law_name="Example Decree",
            supplementary_article_no="제14조",
            matched_clause_labels=["제14조 제1호", "제14조 제2호"],
        )
        item = to_readable_suggestion_item(suggestion)
        self.assertEqual(item["유형"], "question_scope_gap")
        self.assertEqual(item["사유코드"], "question_scope_missing_direct_basis")
        self.assertEqual(item["보완법령"], "Example Decree")
        self.assertEqual(item["직접관련항목"], ["제14조 제1호", "제14조 제2호"])

        summary = summarize_suggestions([suggestion])
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["pending_count"], 1)
        self.assertEqual(summary["question_scope_gap_count"], 1)

    def test_render_suggestion_html(self):
        suggestion = LawHintSuggestion(
            id="s1",
            fingerprint="fp1",
            request_id="req-1",
            question_summary="Need decree basis",
            user_query="Can this agency collect an identifier?",
            question_intent="applicability",
            related_law_queries=["Example Decree"],
            issue_terms=["identifier"],
            search_queries=["example decree identifier"],
            proposed_keywords=["example", "identifier"],
            status="approved",
            occurrence_count=2,
            created_at="2026-03-20T00:00:00+00:00",
            updated_at="2026-03-20T01:00:00+00:00",
            suggestion_type="question_scope_gap",
            reason_code="question_scope_missing_direct_basis",
            question_law_family="Example Law",
            question_scope_direct_basis_found=False,
            question_scope_article_no="제10조",
            supplementary_law_name="Example Decree",
            supplementary_article_no="제14조",
            matched_clause_labels=["제14조 제1호"],
            approved_law_name="Example Decree",
            approved_keywords=["example", "identifier"],
        )
        html_doc = render_suggestion_html(
            [suggestion],
            approved_overrides={"Example Decree": ["example", "identifier"]},
            status="approved",
        )
        self.assertIn("<!doctype html>", html_doc.lower())
        self.assertIn("Law Hint Suggestions", html_doc)
        self.assertIn("question_scope_gap", html_doc)
        self.assertIn("question_scope_missing_direct_basis", html_doc)
        self.assertIn("Example Decree", html_doc)
        self.assertIn("제14조 제1호", html_doc)
        self.assertIn('option value="approved" selected', html_doc)

    def test_law_hint_suggestion_store_approve_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
            )
            suggestion = store.create_or_update_suggestion(
                request_id="req-1",
                question_summary="도서관 출석부",
                user_query="도서관 출석부 제출",
                question_intent="explain",
                related_law_queries=["도서관법"],
                issue_terms=["출석부"],
                search_queries=["도서관법 출석부"],
                proposed_keywords=["도서관", "출석부"],
            )

            approved = store.approve_suggestion(suggestion.id)

            self.assertEqual(approved.status, "approved")
            self.assertEqual(store.approved_overrides()["도서관법"], ["도서관", "출석부"])

def _patched_test_to_readable_suggestion_item_and_summary(self):
    suggestion = LawHintSuggestion(
        id="s1",
        fingerprint="fp1",
        request_id="req-1",
        question_summary="Need decree basis",
        user_query="Can this agency collect an identifier?",
        question_intent="applicability",
        related_law_queries=["Example Decree"],
        issue_terms=["identifier"],
        search_queries=["example decree identifier"],
        proposed_keywords=["example", "identifier"],
        status="pending",
        occurrence_count=3,
        created_at="2026-03-20T00:00:00+00:00",
        updated_at="2026-03-20T01:00:00+00:00",
        suggestion_type="question_scope_gap",
        reason_code="question_scope_missing_direct_basis",
        question_law_family="Example Law",
        question_scope_direct_basis_found=False,
        question_scope_article_no="제10조",
        supplementary_law_name="Example Decree",
        supplementary_article_no="제14조",
        matched_clause_labels=["제14조 제1호", "제14조 제2호"],
        recommended_change_type="decree_title_priority_review",
        recommended_change_payload={"law_name": "Example Decree", "article_no": "제14조"},
        runtime_safe=False,
        approval_effect="review decree title priority before adding a runtime rule",
    )

    item = to_readable_suggestion_item(suggestion)
    readable_json = json.dumps(item, ensure_ascii=False)
    self.assertIn("question_scope_gap", readable_json)
    self.assertIn("question_scope_missing_direct_basis", readable_json)
    self.assertIn("Example Decree", readable_json)
    self.assertIn("제14조 제1호", readable_json)
    self.assertIn("decree_title_priority_review", readable_json)

    summary = summarize_suggestions([suggestion])
    self.assertEqual(summary["count"], 1)
    self.assertEqual(summary["pending_count"], 1)
    self.assertEqual(summary["question_scope_gap_count"], 1)
    self.assertEqual(summary["runtime_safe_count"], 0)


def _patched_test_render_suggestion_html(self):
    suggestion = LawHintSuggestion(
        id="s1",
        fingerprint="fp1",
        request_id="req-1",
        question_summary="Need decree basis",
        user_query="Can this agency collect an identifier?",
        question_intent="applicability",
        related_law_queries=["Example Decree"],
        issue_terms=["identifier"],
        search_queries=["example decree identifier"],
        proposed_keywords=["example", "identifier"],
        status="approved",
        occurrence_count=2,
        created_at="2026-03-20T00:00:00+00:00",
        updated_at="2026-03-20T01:00:00+00:00",
        suggestion_type="question_scope_gap",
        reason_code="question_scope_missing_direct_basis",
        question_law_family="Example Law",
        question_scope_direct_basis_found=False,
        question_scope_article_no="제10조",
        supplementary_law_name="Example Decree",
        supplementary_article_no="제14조",
        matched_clause_labels=["제14조 제1호"],
        recommended_change_type="decree_title_priority_review",
        recommended_change_payload={"law_name": "Example Decree", "article_no": "제14조"},
        runtime_safe=False,
        approval_effect="operator review recorded; no runtime override created",
        approved_rule_type="decree_title_priority_review",
        approved_rule_id="rule-1",
    )

    html_doc = render_suggestion_html(
        [suggestion],
        override_rule_count=1,
        status="approved",
    )
    self.assertIn("<!doctype html>", html_doc.lower())
    self.assertIn("Law Hint Suggestions", html_doc)
    self.assertIn("question_scope_gap", html_doc)
    self.assertIn("question_scope_missing_direct_basis", html_doc)
    self.assertIn("Example Decree", html_doc)
    self.assertIn("제14조 제1호", html_doc)
    self.assertIn("decree_title_priority_review", html_doc)
    self.assertIn("runtime-safe", html_doc)
    self.assertIn('option value="approved" selected', html_doc)


def _patched_test_law_hint_suggestion_store_approve_flow(self):
    with tempfile.TemporaryDirectory() as tmp:
        store = LawHintSuggestionStore(
            suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
            overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
        )
        suggestion = store.create_or_update_suggestion(
            request_id="req-1",
            question_summary="Need decree review",
            user_query="Need decree review",
            question_intent="explain",
            related_law_queries=["Example Law"],
            issue_terms=["identifier"],
            search_queries=["example law identifier"],
            proposed_keywords=["example", "identifier"],
            suggestion_type="question_scope_gap",
            reason_code="question_scope_missing_direct_basis",
            recommended_change_type="decree_title_priority_review",
            recommended_change_payload={"law_name": "Example Decree", "article_no": "제14조"},
            runtime_safe=False,
            approval_effect="review decree title priority before adding a runtime rule",
        )

        approved = store.approve_suggestion(suggestion.id)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(store.active_override_rules(), [])
        self.assertIsNone(approved.approved_rule_id)
        self.assertEqual(
            approved.approval_effect,
            "review decree title priority before adding a runtime rule",
        )


HttpServerParsingTests.test_to_readable_suggestion_item_and_summary = _patched_test_to_readable_suggestion_item_and_summary
HttpServerParsingTests.test_render_suggestion_html = _patched_test_render_suggestion_html
HttpServerParsingTests.test_law_hint_suggestion_store_approve_flow = _patched_test_law_hint_suggestion_store_approve_flow


if __name__ == "__main__":
    unittest.main()
