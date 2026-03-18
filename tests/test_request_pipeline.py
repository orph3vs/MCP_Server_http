import tempfile
import unittest
from pathlib import Path

from src.cost_logger import CostLogger
from src.law_hint_suggestions import LawHintSuggestionStore
from src.request_pipeline import PipelineRequest, RequestPipeline


class FakeLawApiOk:
    def __init__(self):
        self.search_queries = []
        self.article_calls = []
        self.precedent_queries = []

    def search_law(self, query):
        self.search_queries.append(query)
        if query == "공동주택관리법":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "012345",
                            "법령명한글": "공동주택관리법",
                            "법령일련번호": "280069",
                        }
                    ]
                }
            }
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011357",
                        "법령명한글": "개인정보 보호법",
                        "법령일련번호": "270351",
                    }
                ]
            }
        }

    def get_version(self, law_id):
        return {
            "law_id": law_id,
            "source_target": "law_fallback",
            "version_fields": {"시행일자": "20251002", "공포일자": "20250401", "제개정구분명": "일부개정"},
        }

    def get_article(self, law_id, article_no):
        self.article_calls.append((law_id, article_no))
        titles = {
            "제1조": "목적",
            "제2조": "정의",
            "제3조": "적용범위",
            "제15조": "개인정보의 수집·이용",
            "제17조": "개인정보의 제공",
            "제34조": "개인정보 유출 통지",
            "제34조의2": "유출 신고",
            "제8조": "적용의 일부 제외",
            "제75조": "과태료",
        }
        title = titles.get(article_no, "일반")
        return {
            "law_id": law_id,
            "article_no": article_no,
            "found": True,
            "matched_via": "service:law",
            "article_text": f"{article_no}({title}) 테스트 조문 본문",
        }

    def search_precedent(self, query, reference_law=None):
        self.precedent_queries.append((query, reference_law))
        return {
            "PrecSearch": {
                "prec": [
                    {
                        "판례일련번호": "P1",
                        "사건명": "개인정보 보호법 사건",
                        "사건번호": "2025두2345",
                        "법원명": "대법원",
                        "선고일자": "20250101",
                    }
                ]
            }
        }

    def get_precedent(self, precedent_id):
        return {
            "precedent_id": precedent_id,
            "사건명": "개인정보 보호법 사건",
            "사건번호": "2025두2345",
            "판결요지": "법정 요건을 충족하지 못한 동의는 유효한 동의로 보기 어렵다.",
        }


class FakeLawApiEmpty:
    def __init__(self):
        self.search_queries = []

    def search_law(self, query):
        self.search_queries.append(query)
        return {}


class FakeLawApiNeedsNormalizedQuery(FakeLawApiEmpty):
    def get_version(self, law_id):
        return {"law_id": law_id, "version_fields": {"시행일자": "20251002"}}

    def get_article(self, law_id, article_no):
        return {"law_id": law_id, "article_no": article_no, "found": True, "article_text": f"{article_no}(목적) 본문"}

    def search_law(self, query):
        self.search_queries.append(query)
        if query == "개인정보 보호법":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "011357",
                            "법령명한글": "개인정보 보호법",
                            "법령일련번호": "270351",
                        }
                    ]
                }
            }
        return {"LawSearch": {"law": [], "totalCnt": "0"}}


class FakeLawApiLibrary(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        if query == "도서관법":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "009567",
                            "법령명한글": "도서관법",
                            "법령일련번호": "290001",
                        }
                    ]
                }
            }
        return super().search_law(query)


class RequestPipelineTests(unittest.TestCase):
    def test_refined_precedent_queries_split_broad_question_into_issue_queries(self):
        queries = RequestPipeline._precedent_search_queries_refined(
            "대한민국에서 청소년 도박과 관련된 법적 근거를 설명해줘. 형사처벌, 청소년 보호, 온라인 도박, 업주나 플랫폼 책임도 같이 알려줘.",
            "청소년 보호법",
            [],
        )

        self.assertIn("청소년 보호법 판례", queries)
        self.assertIn("청소년 도박 판례", queries)
        self.assertIn("청소년 도박 형사처벌 판례", queries)
        self.assertIn("청소년 도박 온라인 도박 판례", queries)
        self.assertNotIn("형사처벌 판례", queries)

    def test_process_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiOk(), logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 처리 위법 여부 조사 대상인지 설명",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertTrue(result.answer)
            self.assertIn("law_search", result.citations)
            self.assertIn("law_context", result.citations)
            self.assertIn("review_summary", result.citations)
            self.assertIn("prompt_policy", result.citations)
            self.assertEqual(result.citations["law_context"]["primary_law"]["law_id"], "011357")
            self.assertEqual(result.mode, "multi_agent")
            self.assertGreaterEqual(result.score, 0)
            self.assertTrue(result.citations["prompt_policy"]["require_evidence_mapping"])

            logged = logger.get_by_request_id(result.request_id)
            self.assertIsNotNone(logged)
            self.assertEqual(logged.request_id, result.request_id)
            self.assertIn("개인정보 처리", logged.question_summary)
            self.assertEqual(logged.question_intent, "illegality")
            self.assertGreaterEqual(logged.law_search_count, 1)
            self.assertGreaterEqual(logged.nlic_calls, logged.law_search_count)

    def test_process_enriches_context_with_article_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiOk(), logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제1조 설명",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제1조")
            self.assertIn("개인정보 보호법 제1조는 목적에 관한 규정입니다.", result.answer)

    def test_process_uses_normalized_law_search_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiNeedsNormalizedQuery()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제1조 설명",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(law_api.search_queries[0], "개인정보 보호법")
            self.assertEqual(result.citations["law_context"]["used_search_query"], "개인정보 보호법")
            self.assertEqual(result.citations["law_search"]["used_search_query"], "개인정보 보호법")

    def test_process_fetches_related_articles_for_difference_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제1조와 제2조 차이를 설명해줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(law_api.article_calls, [("011357", "제1조"), ("011357", "제2조")])
            self.assertEqual(result.citations["law_context"]["related_articles"][0]["article_no"], "제2조")
            self.assertIn("[비교 참고 조문]", result.answer)

    def test_process_fetches_related_articles_for_procedure_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제34조와 제34조의2 절차를 설명해줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(law_api.article_calls, [("011357", "제34조"), ("011357", "제34조의2")])
            self.assertIn("[절차 정리]", result.answer)

    def test_process_adds_precedent_for_high_risk_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제75조가 위법 판단 기준인지 설명해줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertTrue(law_api.precedent_queries)
            self.assertEqual(result.citations["law_context"]["precedent"]["precedent_id"], "P1")
            self.assertIn("[참고 판례]", result.answer)
            self.assertEqual(result.mode, "multi_agent")
            self.assertTrue(result.citations["review_summary"]["requires_caution"])

    def test_process_surfaces_precedent_relevance_in_answer_and_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제15조가 위법 판단 기준인지 설명하고 관련 판례도 같이 보여줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertIn("관련성:", result.answer)
            self.assertIn("제15조와 직접 연결된 검색", result.answer)
            self.assertTrue(result.citations["review_summary"]["precedent_relevant"])

    def test_process_adds_precedent_on_explicit_request_even_if_low_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제1조 설명하고 관련 판례도 같이 보여줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertTrue(law_api.precedent_queries)
            self.assertEqual(result.mode, "single_agent")
            self.assertIn("[참고 판례]", result.answer)

    def test_process_uses_prompt_policy_to_keep_illegality_in_multi_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="개인정보 보호법 제15조가 위법 판단 기준인지 설명해줘",
                    context="기준시점: 2025-01-01",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(result.mode, "multi_agent")
            self.assertTrue(result.citations["prompt_policy"]["prefer_multi_agent_for_risky_queries"])

    def test_process_collects_related_laws_for_apartment_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiOk()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="아파트 입주자 명부에 소유자 정보를 수집하는 경우 위법인지 설명해줘",
                    context="기준시점: 2026-03-13",
                )
            )

            self.assertIsNone(result.error)
            self.assertIn("공동주택관리법", law_api.search_queries)
            related_laws = result.citations["law_context"]["related_laws"]
            self.assertTrue(any(item["law_name"] == "공동주택관리법" for item in related_laws))
            self.assertIn("related_law_queries", result.citations["law_context"])

    def test_related_law_queries_include_location_law_hint(self):
        queries = RequestPipeline._related_law_queries("앱에서 GPS 위치정보를 수집해 지오펜싱 마케팅을 하려면?")

        self.assertIn("위치정보의 보호 및 이용 등에 관한 법률", queries)

    def test_related_law_queries_include_library_law_hint(self):
        queries = RequestPipeline._related_law_queries(
            "작은도서관 프로그램 출석부를 정산 증빙으로 제출할 때 이름을 가려도 되는지"
        )

        self.assertIn("도서관법", queries)

    def test_law_search_queries_rewrite_with_related_law_and_issue_terms(self):
        queries = RequestPipeline._law_search_queries(
            "작은도서관 출석부를 정산 증빙으로 제출할 때 개인정보를 가려도 되는지",
            related_law_queries=["도서관법", "개인정보 보호법"],
        )

        self.assertIn("도서관법", queries)
        self.assertIn("도서관법 출석부", queries)
        self.assertIn("개인정보 보호법 개인정보", queries)
        self.assertIn("증빙서류", queries)

    def test_process_collects_related_laws_for_library_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiLibrary()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="작은도서관 출석부를 정산 증빙으로 제출할 때 이름을 가려도 되는지 설명해줘.",
                    context="기준시점: 2026-03-16",
                )
            )

            self.assertIsNone(result.error)
            self.assertIn("도서관법", law_api.search_queries)
            self.assertTrue(
                any("도서관법" == (item.get("law_name")) for item in result.citations["law_context"]["related_laws"])
            )

    def test_process_error_path_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            )
            pipeline = RequestPipeline(
                law_api=FakeLawApiEmpty(),
                logger=logger,
                suggestion_store=suggestion_store,
            )

            result = pipeline.process(PipelineRequest(user_query="테스트"))

            self.assertIsNotNone(result.error)
            self.assertEqual(result.error["stage"], "LawAPI")
            self.assertTrue(result.mode.startswith("error:"))

            logged = logger.get_by_request_id(result.request_id)
            self.assertIsNotNone(logged)
            self.assertTrue(logged.mode.startswith("error:"))
            self.assertEqual(logged.error_stage, "LawAPI")
            suggestions = suggestion_store.list_suggestions()
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0].question_summary, "테스트")

    def test_process_reuses_existing_law_hint_suggestion_for_duplicate_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            )
            pipeline = RequestPipeline(
                law_api=FakeLawApiEmpty(),
                logger=logger,
                suggestion_store=suggestion_store,
            )

            first = pipeline.process(PipelineRequest(user_query="작은도서관 출석부 개인정보 마스킹"))
            second = pipeline.process(PipelineRequest(user_query="작은도서관 출석부 개인정보 마스킹"))

            self.assertIsNotNone(first.error)
            self.assertIsNotNone(second.error)
            suggestions = suggestion_store.list_suggestions()
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0].occurrence_count, 2)

    def test_approved_law_hint_override_is_used_for_related_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            )
            suggestion = suggestion_store.create_or_update_suggestion(
                request_id="req-1",
                question_summary="강사비 지급",
                user_query="강사비 지급 관련 법령",
                question_intent="explain",
                related_law_queries=["소득세법"],
                issue_terms=["원천징수"],
                search_queries=["소득세법 원천징수"],
                proposed_keywords=["강사비", "원천징수"],
            )
            suggestion_store.approve_suggestion(
                suggestion.id,
                law_name="소득세법",
                keywords=["강사비", "원천징수"],
            )
            pipeline = RequestPipeline(
                law_api=FakeLawApiOk(),
                logger=logger,
                suggestion_store=suggestion_store,
            )

            queries = pipeline._resolved_related_law_queries("외부 강사비 원천징수 기준이 궁금합니다")

            self.assertIn("소득세법", queries)

if __name__ == "__main__":
    unittest.main()
