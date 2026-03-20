import io
import json
import tempfile
import unittest
from pathlib import Path

from src.cost_logger import CostLogger
from src.mcp_core import McpServer
from src.mcp_stdio_server import _read_message, _write_message
from src.request_pipeline import PipelineResponse


class FakeLawApi:
    def search_law(self, query):
        return {"LawSearch": {"law": [{"법령ID": "011357", "법령명한글": "개인정보 보호법"}], "키워드": query}}

    def get_article(self, law_id, article_no):
        return {"law_id": law_id, "article_no": article_no, "found": True, "article_text": "제1조 본문"}

    def get_version(self, law_id):
        return {"law_id": law_id, "source_target": "law_fallback", "version_fields": {"시행일자": "20251002"}}

    def validate_article(self, law_id, article_no):
        return {"law_id": law_id, "article_no": article_no, "is_valid": True}

    def search_precedent(self, query):
        return {"PrecSearch": {"prec": [{"판례일련번호": "123", "사건명": "개인정보 사건", "사건번호": "2025다12345"}]}}

    def get_precedent(self, precedent_id):
        return {"precedent_id": precedent_id, "사건명": "개인정보 사건", "사건번호": "2025다12345"}


class FakePipeline:
    def __init__(self):
        self.law_api = FakeLawApi()
        self.logger = CostLogger(db_path=str(Path(tempfile.gettempdir()) / "codex-mcp-tool-test.db"))

    def process(self, req):
        return PipelineResponse(
            request_id=req.request_id or "req-1",
            risk_level="HIGH",
            mode="multi_agent",
            answer="테스트 응답",
            citations={
                "law_search": {"used_search_query": "개인정보 보호법"},
                "law_context": {
                    "primary_law": {"law_name": "개인정보 보호법", "law_id": "011357"},
                    "article": {
                        "article_no": "제1조",
                        "matched_clauses": [
                            {
                                "article_no": "제18조 제3호의2",
                                "article_text_excerpt": "법 제12조의2에 따른 통합정보시스템의 구축ㆍ운영 등에 관한 사무",
                            },
                            {
                                "article_no": "제18조 제6호",
                                "article_text_excerpt": "법 제16조에 따른 가정 밖 청소년의 발생 예방 및 보호ㆍ지원에 관한 사무",
                            },
                        ],
                    },
                    "precedent": {"case_name": "개인정보 사건", "case_no": "2025다12345"},
                },
            },
            score=83.0,
            latency_ms=12.3,
            error=None,
        )


class FakeErrorPipeline(FakePipeline):
    def process(self, req):
        return PipelineResponse(
            request_id=req.request_id or "req-err",
            risk_level="LOW",
            mode="error:LawAPI",
            answer="",
            citations={},
            score=0.0,
            latency_ms=12.3,
            error={"stage": "LawAPI", "message": "empty_law_data"},
        )


class FakeClarificationPipeline(FakePipeline):
    def process(self, req):
        return PipelineResponse(
            request_id=req.request_id or "req-clarify",
            risk_level="HIGH",
            mode="multi_agent",
            answer=(
                "[결론]\n기본 답변\n\n"
                "[추가 확인 필요]\n"
                "- 그 업체·기관이 법령상 관리주체인지, 위탁 또는 수탁을 받은 외부 업체인지 알 수 있나요?"
            ),
            citations={
                "law_search": {"used_search_query": "공동주택관리법"},
                "law_context": {
                    "primary_law": {"law_name": "공동주택관리법", "law_id": "012345"},
                    "article": {"article_no": "제7조"},
                },
            },
            score=77.0,
            latency_ms=9.4,
            error=None,
            clarification={
                "clarification_needed": True,
                "clarification_reason": "행위자 지위와 정보 흐름에 따라 결론이 달라질 수 있습니다.",
                "clarification_questions": [
                    "그 업체·기관이 법령상 관리주체인지, 위탁 또는 수탁을 받은 외부 업체인지 알 수 있나요?",
                    "정보를 정보주체에게 직접 받는 상황인가요, 아니면 다른 기관이나 관리주체로부터 제공받는 상황인가요?",
                ],
            },
            answer_plan={
                "intent": "applicability",
                "risk_level": "HIGH",
                "direct_basis": {"law_name": "공동주택관리법", "article_no": "제7조", "found": True},
                "question_law_scope": None,
                "supplementary_basis": None,
                "privacy_processing_question": True,
                "processing_actions": ["수집"],
                "privacy_analysis": {
                    "actor_status_explicit": True,
                    "processing_actions": ["수집"],
                    "data_scope": "general",
                    "legal_basis_checkpoints": ["개인정보 보호법 제15조 수집·이용 근거"],
                    "clarification_needed": True,
                },
                "clarification": {
                    "clarification_needed": True,
                    "clarification_questions": [
                        "그 업체·기관이 법령상 관리주체인지, 위탁 또는 수탁을 받은 외부 업체인지 알 수 있나요?"
                    ],
                },
            },
        )


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.server = McpServer(pipeline=FakePipeline())

    def _initialize(self):
        return self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
            }
        )

    def test_initialize_and_list_tools(self):
        init_response = self._initialize()
        self.assertEqual(init_response["result"]["protocolVersion"], "2025-03-26")

        list_response = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = [tool["name"] for tool in list_response["result"]["tools"]]
        self.assertIn("ask", tool_names)
        self.assertIn("answer_with_citations", tool_names)
        self.assertIn("get_article", tool_names)
        self.assertIn("search_precedent", tool_names)
        self.assertIn("get_precedent", tool_names)

    def test_tools_call_ask(self):
        self._initialize()
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"user_query": "개인정보 보호법 제1조 설명"}},
            }
        )

        self.assertFalse(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["answer"], "테스트 응답")
        self.assertEqual(payload["citations"]["law_search"]["used_search_query"], "개인정보 보호법")
        self.assertIn("테스트 응답", response["result"]["content"][0]["text"])
        self.assertIn("[직접 관련 항목]", response["result"]["content"][0]["text"])
        self.assertIn("제18조 제3호의2", response["result"]["content"][0]["text"])
        self.assertIn("제18조 제6호", response["result"]["content"][0]["text"])
        self.assertIn("[참고 판례] 개인정보 사건", response["result"]["content"][0]["text"])

    def test_tools_call_answer_with_citations_alias(self):
        self._initialize()
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "answer_with_citations", "arguments": {"user_query": "개인정보 보호법 제1조 설명"}},
            }
        )

        self.assertFalse(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["answer"], "테스트 응답")

    def test_tools_call_ask_exposes_clarification_in_text_and_payload(self):
        server = McpServer(pipeline=FakeClarificationPipeline())
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"user_query": "아파트 관리업체가 주민 정보를 수집할 수 있나요?"}},
            }
        )

        self.assertFalse(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["clarification"]["clarification_needed"])
        self.assertTrue(payload["answer_plan"]["clarification"]["clarification_needed"])
        self.assertTrue(payload["answer_plan"]["privacy_analysis"]["clarification_needed"])
        self.assertEqual(response["result"]["content"][0]["text"].count("[추가 확인 필요]"), 1)
        self.assertIn("관리주체", response["result"]["content"][0]["text"])

    def test_tools_call_answer_with_citations_returns_error_when_pipeline_fails(self):
        server = McpServer(pipeline=FakeErrorPipeline())
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "answer_with_citations", "arguments": {"user_query": "개인정보 보호법 제1조 설명"}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["error"], "empty_law_data")

    def test_tools_call_search_law_creates_tool_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = FakePipeline()
            pipeline.logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            server = McpServer(pipeline=pipeline)
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
                }
            )
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "search_law", "arguments": {"query": "개인정보 보호법"}},
                }
            )

            logged = pipeline.logger.list_recent(limit=1)[0]
            self.assertEqual(logged.entry_type, "tool")
            self.assertEqual(logged.tool_name, "search_law")
            self.assertEqual(logged.law_search_count, 1)

    def test_tools_call_search_precedent(self):
        self._initialize()
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "search_precedent", "arguments": {"query": "개인정보 보호법 제15조 위법 판례"}},
            }
        )

        self.assertFalse(response["result"]["isError"])
        self.assertIn("개인정보 사건", response["result"]["content"][0]["text"])
        self.assertEqual(response["result"]["structuredContent"]["PrecSearch"]["prec"][0]["판례일련번호"], "123")

    def test_tools_call_missing_argument_returns_tool_error(self):
        self._initialize()
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_article", "arguments": {"law_id": "011357"}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["error"], "missing_article_no")

    def test_resources_methods_return_empty_lists(self):
        self._initialize()

        resources_response = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}})
        templates_response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}}
        )

        self.assertEqual(resources_response["result"]["resources"], [])
        self.assertEqual(templates_response["result"]["resourceTemplates"], [])

    def test_transport_roundtrip(self):
        buffer = io.BytesIO()
        _write_message(buffer, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        buffer.seek(0)
        message = _read_message(buffer)
        self.assertEqual(message["method"], "ping")


if __name__ == "__main__":
    unittest.main()
