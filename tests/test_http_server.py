import json
import unittest

from src.cost_logger import CostLogEntry
from src.http_server import (
    parse_ask_request,
    parse_recent_limit,
    parse_recent_view,
    parse_tool_request,
    render_log_table,
    to_readable_log_item,
    to_readable_summary,
)


class HttpServerParsingTests(unittest.TestCase):
    def test_parse_ask_request_success(self):
        req, data = parse_ask_request(
            json.dumps(
                {
                    "user_query": "개인정보 제3자 제공 기준",
                    "context": "기준시점: 2025-01-01",
                    "request_id": "req-123",
                }
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
            json.dumps({"law_id": "L1", "article_no": "제1조"}).encode("utf-8"),
            ("law_id", "article_no"),
        )
        self.assertEqual(fields["law_id"], "L1")

    def test_parse_recent_limit(self):
        self.assertEqual(parse_recent_limit("/logs/recent?limit=7"), 7)
        self.assertEqual(parse_recent_limit("/logs/recent?limit=1000"), 100)

    def test_parse_recent_view(self):
        self.assertEqual(parse_recent_view("/logs/recent"), "raw")
        self.assertEqual(parse_recent_view("/logs/recent?view=readable"), "readable")
        self.assertEqual(parse_recent_view("/logs/recent?view=table"), "table")

    def test_to_readable_log_item(self):
        item = to_readable_log_item(
            CostLogEntry(
                request_id="req-1",
                risk_level="HIGH",
                mode="multi_agent",
                tokens_in=10,
                tokens_out=20,
                cost=0.001,
                latency=30.5,
                score=88.0,
                question_intent="illegality",
                law_search_count=2,
                related_law_count=1,
                precedent_search_count=1,
                has_precedent=True,
            )
        )
        self.assertEqual(item["질문유형"], "위법 여부형")
        self.assertTrue(item["판례포함여부"])
        self.assertTrue(any("판례 검색" in note for note in item["해석메모"]))

    def test_to_readable_summary(self):
        readable = to_readable_summary(
            {
                "count": 2,
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
        self.assertEqual(readable["판례검색포함요청수"], 1)

    def test_render_log_table(self):
        table = render_log_table(
            [
                CostLogEntry(
                    request_id="req-1",
                    risk_level="HIGH",
                    mode="multi_agent",
                    tokens_in=10,
                    tokens_out=20,
                    cost=0.001,
                    latency=30.5,
                    score=88.0,
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
        self.assertIn("req-1", table)
        self.assertIn("메모:", table)

    def test_parse_ask_request_missing_query(self):
        with self.assertRaises(ValueError):
            parse_ask_request(json.dumps({"context": "x"}).encode("utf-8"))

    def test_parse_ask_request_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_ask_request(b"{bad-json")


if __name__ == "__main__":
    unittest.main()
