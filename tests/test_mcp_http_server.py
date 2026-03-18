import json
import unittest

from src.mcp_http_server import dispatch_http_payload, is_authorized_request, parse_jsonrpc_http_body
from src.mcp_stdio_server import McpServer


class FakeLawApi:
    def search_law(self, query):
        return {"LawSearch": {"law": [{"법령ID": "011357", "법령명한글": "개인정보 보호법"}], "query": query}}

    def get_article(self, law_id, article_no):
        return {"law_id": law_id, "article_no": article_no, "found": True, "article_text": "제1조 본문"}

    def get_version(self, law_id):
        return {"law_id": law_id, "version_fields": {"시행일자": "20251002"}}

    def validate_article(self, law_id, article_no):
        return {"law_id": law_id, "article_no": article_no, "is_valid": True}

    def search_precedent(self, query):
        return {"PrecSearch": {"prec": [{"판례일련번호": "123", "사건명": "개인정보 사건", "사건번호": "2025다2345"}]}}

    def get_precedent(self, precedent_id):
        return {"precedent_id": precedent_id, "사건명": "개인정보 사건", "사건번호": "2025다2345"}


class FakePipeline:
    def __init__(self):
        self.law_api = FakeLawApi()

    def process(self, req):
        from src.request_pipeline import PipelineResponse

        return PipelineResponse(
            request_id=req.request_id or "req-http",
            risk_level="LOW",
            mode="single_agent",
            answer="테스트 응답",
            citations={},
            score=90.0,
            latency_ms=8.0,
            error=None,
        )


class McpHttpServerTests(unittest.TestCase):
    def setUp(self):
        self.server = McpServer(pipeline=FakePipeline())

    def test_parse_jsonrpc_http_body_utf8(self):
        payload = parse_jsonrpc_http_body(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, ensure_ascii=False).encode("utf-8")
        )
        self.assertEqual(payload["method"], "tools/list")

    def test_dispatch_http_payload_roundtrip(self):
        initialize = dispatch_http_payload(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
            },
        )
        self.assertEqual(initialize["result"]["protocolVersion"], "2025-03-26")

        tool_call = dispatch_http_payload(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"user_query": "개인정보 보호법 설명"}},
            },
        )
        self.assertFalse(tool_call["result"]["isError"])
        self.assertEqual(tool_call["result"]["structuredContent"]["answer"], "테스트 응답")

    def test_dispatch_http_payload_notification_returns_none(self):
        dispatch_http_payload(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
            },
        )
        response = dispatch_http_payload(
            self.server,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        self.assertIsNone(response)

    def test_dispatch_http_payload_batch_returns_only_request_responses(self):
        batch_response = dispatch_http_payload(
            self.server,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ],
        )
        self.assertEqual(len(batch_response), 2)
        self.assertEqual(batch_response[0]["id"], 1)
        self.assertEqual(batch_response[1]["id"], 2)

    def test_dispatch_http_payload_protocol_error_is_wrapped(self):
        response = dispatch_http_payload(
            self.server,
            {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response["error"]["code"], -32002)
        self.assertEqual(response["id"], 9)

    def test_is_authorized_request_allows_when_token_not_configured(self):
        self.assertTrue(is_authorized_request({}))

    def test_is_authorized_request_accepts_matching_bearer_token(self):
        self.assertTrue(
            is_authorized_request(
                {"Authorization": "Bearer secret-token"},
                expected_token="secret-token",
            )
        )

    def test_is_authorized_request_rejects_missing_or_invalid_token(self):
        self.assertFalse(is_authorized_request({}, expected_token="secret-token"))
        self.assertFalse(
            is_authorized_request(
                {"Authorization": "Bearer wrong-token"},
                expected_token="secret-token",
            )
        )
        self.assertFalse(
            is_authorized_request(
                {"Authorization": "Basic abc123"},
                expected_token="secret-token",
            )
        )


if __name__ == "__main__":
    unittest.main()
