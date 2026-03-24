import json
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


class FakeLawApiSchoolYouth(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        if query == "청소년복지 지원법 시행령":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "009682",
                            "법령명한글": "청소년복지 지원법 시행령",
                            "법령일련번호": "9682",
                        }
                    ]
                }
            }
        if query == "청소년복지 지원법":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "009681",
                            "법령명한글": "청소년복지 지원법",
                            "법령일련번호": "9681",
                        }
                    ]
                }
            }
        if query == "청소년 기본법 시행령":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "005206",
                            "법령명한글": "청소년 기본법 시행령",
                            "법령일련번호": "5206",
                        }
                    ]
                }
            }
        if query == "청소년 기본법":
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "000816",
                            "법령명한글": "청소년 기본법",
                            "법령일련번호": "816",
                        }
                    ]
                }
            }
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "012054",
                        "법령명한글": "학교 밖 청소년 지원에 관한 법률",
                        "법령일련번호": "12054",
                    }
                ]
            }
        }

    def search_related_laws(self, query=None, law_id=None):
        if law_id == "012054":
            return {
                "lsRltSearch": {
                    "법령": {
                        "관련법령": [
                            {
                                "관련법령ID": "000816",
                                "관련법령명": "청소년 기본법",
                                "관련법령본문조회": "https://www.law.go.kr/법령/청소년기본법",
                                "법령간관계": "3유형(기본법)",
                            }
                        ]
                    }
                }
            }
        if law_id == "000816":
            return {
                "lsRltSearch": {
                    "법령": {
                        "관련법령": [
                            {
                                "관련법령ID": "009681",
                                "관련법령명": "청소년복지 지원법",
                                "관련법령본문조회": "https://www.law.go.kr/법령/청소년복지지원법",
                                "법령간관계": "4유형(개별법)",
                            }
                        ]
                    }
                }
            }
        return {"lsRltSearch": {"법령": {"관련법령": []}}}

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "009682" and any(keyword in {"주민등록번호", "고유식별정보"} for keyword in keywords):
            return {
                "law_id": "009682",
                "article_no": "제18조 제6호",
                "article_base_no": "제18조",
                "article_text": "제18조 제6호 법 제16조에 따른 가정 밖 청소년의 발생 예방 및 보호ㆍ지원에 관한 사무",
                "matched_via": "service:law:keyword_scan",
                "score": 7,
            }
        return None


class FakeLawApiSeniorIdentifier(FakeLawApiOk):
    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제24조",
                "article_base_no": "제24조",
                "article_text": "제24조(고유식별정보의 처리) 개인정보처리자는 ... 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        if law_id == "014765":
            return {
                "law_id": "014765",
                "article_no": "제14조",
                "article_base_no": "제14조",
                "article_text": "제14조(민감정보 및 고유식별정보의 처리) ... 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        return None


class FakeLawApiSeniorIdentifierAlias(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        if query in {
            "노인일자리법",
            "노인일자리법 시행령",
            "노인일자리법 시행규칙",
        }:
            return {"LawSearch": {"law": [], "totalCnt": "0"}}
        if query in {
            "노인 일자리 및 사회활동 지원에 관한 법률 시행령",
            "노인 일자리 및 사회활동 지원에 관한 법률 시행령 고유식별정보의 처리",
            "노인 일자리 및 사회활동 지원에 관한 법률 시행령 민감정보 및 고유식별정보의 처리",
        }:
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "014765",
                            "법령명한글": "노인 일자리 및 사회활동 지원에 관한 법률 시행령",
                            "법령일련번호": "14765",
                        }
                    ]
                }
            }
        if query in {
            "노인 일자리 및 사회활동 지원에 관한 법률",
            "노인 일자리 및 사회활동 지원에 관한 법률 시행규칙",
        }:
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "014764",
                            "법령명한글": "노인 일자리 및 사회활동 지원에 관한 법률",
                            "법령일련번호": "14764",
                        }
                    ]
                }
            }
        return super().search_law(query)

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제24조",
                "article_base_no": "제24조",
                "article_text": "제24조(고유식별정보의 처리) 개인정보처리자는 법령에서 허용하는 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        if law_id == "014765":
            return {
                "law_id": "014765",
                "article_no": "제14조",
                "article_base_no": "제14조",
                "article_text": "제14조(민감정보 및 고유식별정보의 처리) 수행기관 등은 법령상 사무 수행에 필요한 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        return None


class FakeLawApiAliasNormalization(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        if query == "전자상거래법":
            return {"LawSearch": {"law": [], "totalCnt": "0"}}
        if query in {"전자상거래", "전자상거래 법률"}:
            return {
                "LawSearch": {
                    "law": [
                        {
                            "법령ID": "009908",
                            "법령명한글": "전자상거래등에서의 소비자보호에 관한 법률",
                            "법령약칭명": "전자상거래법",
                            "법령일련번호": "9908",
                        }
                    ]
                }
            }
        return super().search_law(query)


class FakeLawApiQuestionScopeFallback(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
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


class FakeLawApiApartmentContextPriority(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011358",
                        "법령명한글": "개인정보 보호법 시행령",
                        "법령일련번호": "270352",
                    },
                    {
                        "법령ID": "012345",
                        "법령명한글": "공동주택관리법",
                        "법령일련번호": "280069",
                    },
                    {
                        "법령ID": "011357",
                        "법령명한글": "개인정보 보호법",
                        "법령일련번호": "270351",
                    },
                ]
            }
        }

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011358":
            return {
                "law_id": "011358",
                "article_no": "제62조의2",
                "article_base_no": "제62조의2",
                "article_text": "제62조의2(민감정보 및 고유식별정보의 처리) 보호위원회, 분쟁조정위원회, 정보전송자 및 중계전문기관은 해당 사무 수행을 위하여 불가피한 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        if law_id == "012345":
            return {
                "law_id": "012345",
                "article_no": "제11조 제3항",
                "article_base_no": "제11조",
                "article_text": "제11조 제3항 입주자대표회의는 공동주택 관리방법을 결정할 때 위탁관리인 경우 주택관리업자 선정을 포함하여 의결한다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제26조",
                "article_base_no": "제26조",
                "article_text": "제26조(업무위탁에 따른 개인정보의 처리 제한) 개인정보처리자는 업무위탁 시 수탁자를 관리·감독하여야 한다.",
                "matched_via": "service:law:keyword_scan",
                "score": 7,
            }
        return None


class FakeLawApiRrnGeneralLawFallback(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011358",
                        "법령명한글": "개인정보 보호법 시행령",
                        "법령일련번호": "270352",
                    },
                    {
                        "법령ID": "011357",
                        "법령명한글": "개인정보 보호법",
                        "법령일련번호": "270351",
                    },
                ]
            }
        }

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011358":
            return {
                "law_id": "011358",
                "article_no": "제62조의2",
                "article_base_no": "제62조의2",
                "article_text": "제62조의2(민감정보 및 고유식별정보의 처리) 보호위원회 등은 일정한 사무를 위하여 주민등록번호 등을 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        return None

    def get_article(self, law_id, article_no):
        self.article_calls.append((law_id, article_no))
        if law_id == "011357" and article_no == "제24조의2":
            return {
                "law_id": law_id,
                "article_no": article_no,
                "found": True,
                "matched_via": "service:law",
                "article_text": "제24조의2(주민등록번호 처리의 제한) 주민등록번호는 법령에서 구체적으로 요구하거나 허용한 경우 등 예외가 아니면 처리할 수 없다.",
            }
        return super().get_article(law_id, article_no)


class FakeLawApiRrnImpactAssessmentFallback(FakeLawApiRrnGeneralLawFallback):
    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011358":
            return {
                "law_id": "011358",
                "article_no": "제35조",
                "article_base_no": "제35조",
                "article_text": "제35조(개인정보 영향평가의 대상) 일정 규모 이상의 개인정보파일을 대상으로 한다.",
                "matched_clauses": [
                    {
                        "article_no": "제35조 제1호",
                        "article_base_no": "제35조",
                        "article_text": "1. 구축ㆍ운용 또는 변경하려는 개인정보파일로서 5만명 이상의 정보주체에 관한 민감정보 또는 고유식별정보의 처리가 수반되는 개인정보파일",
                        "score": 11,
                    }
                ],
                "matched_via": "service:law:keyword_scan",
                "score": 11,
            }
        return None


class FakeLawApiSensitiveInfoImpactAssessmentFallback(FakeLawApiOk):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011358",
                        "법령명한글": "개인정보 보호법 시행령",
                        "법령일련번호": "270352",
                    },
                    {
                        "법령ID": "011357",
                        "법령명한글": "개인정보 보호법",
                        "법령일련번호": "270351",
                    },
                ]
            }
        }

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011358":
            return {
                "law_id": "011358",
                "article_no": "제35조",
                "article_base_no": "제35조",
                "article_text": "제35조(개인정보 영향평가의 대상) 일정 규모 이상의 개인정보파일을 대상으로 한다.",
                "matched_clauses": [
                    {
                        "article_no": "제35조 제1호",
                        "article_base_no": "제35조",
                        "article_text": "1. 구축ㆍ운용 또는 변경하려는 개인정보파일로서 5만명 이상의 정보주체에 관한 민감정보 또는 고유식별정보의 처리가 수반되는 개인정보파일",
                        "score": 11,
                    }
                ],
                "matched_via": "service:law:keyword_scan",
                "score": 11,
            }
        return None

    def get_article(self, law_id, article_no):
        self.article_calls.append((law_id, article_no))
        if law_id == "011357" and article_no == "제23조":
            return {
                "law_id": law_id,
                "article_no": article_no,
                "found": True,
                "matched_via": "service:law",
                "article_text": "제23조(민감정보의 처리 제한) 개인정보처리자는 원칙적으로 민감정보를 처리할 수 없다.",
            }
        return super().get_article(law_id, article_no)


class RequestPipelineTests(unittest.TestCase):
    def test_absolute_link_strips_oc_query_parameter(self):
        raw_link = "https://www.law.go.kr/DRF/lawService.do?OC=secret-value&target=law&MST=270351&type=HTML"

        result = RequestPipeline._absolute_link(raw_link)

        self.assertEqual(
            result,
            "https://www.law.go.kr/DRF/lawService.do?target=law&MST=270351&type=HTML",
        )
        self.assertNotIn("OC=", result)

    def test_service_link_does_not_include_oc_query_parameter(self):
        pipeline = RequestPipeline(law_api=FakeLawApiOk())

        result = pipeline._service_link("011357", "제1조")

        self.assertEqual(
            result,
            "https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&type=HTML&JO=000100",
        )
        self.assertNotIn("OC=", result)

    def test_public_law_link_uses_readable_law_url(self):
        result = RequestPipeline._public_law_link(
            "전자상거래 등에서의 소비자보호에 관한 법률",
            "20260120",
            "21312",
            "제9조",
        )

        self.assertEqual(
            result,
            "https://www.law.go.kr/법령/%EC%A0%84%EC%9E%90%EC%83%81%EA%B1%B0%EB%9E%98%EB%93%B1%EC%97%90%EC%84%9C%EC%9D%98%EC%86%8C%EB%B9%84%EC%9E%90%EB%B3%B4%ED%98%B8%EC%97%90%EA%B4%80%ED%95%9C%EB%B2%95%EB%A5%A0/%EC%A0%9C9%EC%A1%B0",
        )
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

    def test_process_exposes_public_law_links_only(self):
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
            primary_law_link = result.citations["law_context"]["primary_law"]["law_link"]
            article_link = result.citations["law_context"]["article"]["article_link"]
            self.assertTrue(primary_law_link.startswith("https://www.law.go.kr/법령/"))
            self.assertTrue(article_link.startswith("https://www.law.go.kr/법령/"))
            self.assertNotIn("/(", primary_law_link)
            self.assertNotIn("/(", article_link)
            self.assertNotIn("/DRF/", primary_law_link)
            self.assertNotIn("/DRF/", article_link)

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
            self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "공동주택관리법")
            related_laws = result.citations["law_context"]["related_laws"]
            self.assertTrue(any(item["law_name"] == "개인정보 보호법" for item in related_laws))
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
            self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "도서관법")
            self.assertTrue(
                any("개인정보 보호법" == (item.get("law_name")) for item in result.citations["law_context"]["related_laws"])
            )

    def test_process_error_path_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
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
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
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
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
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

    def test_process_expands_related_law_network_for_school_youth_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            law_api = FakeLawApiSchoolYouth()
            pipeline = RequestPipeline(law_api=law_api, logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="학교밖청소년지원센터는 주민등록번호를 수집할 수 있나",
                    context="기준시점: 2026-03-18",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "청소년복지 지원법 시행령")
            self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제18조 제6호")
            related_laws = result.citations["law_context"]["related_laws"]
            self.assertTrue(any(item["law_name"] == "청소년 기본법" for item in related_laws))
            self.assertTrue(any(item["law_name"] == "청소년복지 지원법" for item in related_laws))

    def test_expanded_related_search_queries_prioritize_welfare_law_for_school_youth_question(self):
        queries = RequestPipeline._expanded_related_search_queries(
            [
                {"관련법령명": "아동ㆍ청소년의 성보호에 관한 법률", "법령간관계": "4유형(개별법)"},
                {"관련법령명": "청소년복지 지원법", "법령간관계": "4유형(개별법)"},
                {"관련법령명": "청소년 보호법", "법령간관계": "4유형(개별법)"},
            ],
            user_query="학교밖청소년지원센터는 주민등록번호 수집 가능 함?",
            primary_law_name="학교 밖 청소년 지원에 관한 법률",
        )

        self.assertIn("청소년복지 지원법 시행령", queries)
        self.assertIn("청소년복지 지원법", queries)

    def test_clause_scan_keywords_include_generic_permission_titles(self):
        keywords = RequestPipeline._clause_scan_keywords(
            "노인 일자리 및 사회활동 지원에 관한 법률에 근거해서 노인의 고유식별정보를 수집할 수 있는가"
        )

        self.assertIn("고유식별정보의 처리", keywords)
        self.assertIn("민감정보 및 고유식별정보의 처리", keywords)
        self.assertIn("처리할 수", keywords)
        self.assertIn("불가피", keywords)

    def test_law_search_queries_prioritize_enforcement_decree_for_sensitive_identifier_questions(self):
        queries = RequestPipeline._law_search_queries(
            "노인 일자리 및 사회활동 지원에 관한 법률에 근거해서 노인의 고유식별정보를 수집할 수 있는가",
            related_law_queries=["노인 일자리 및 사회활동 지원에 관한 법률"],
        )

        self.assertLess(
            queries.index("노인 일자리 및 사회활동 지원에 관한 법률 시행령"),
            queries.index("노인 일자리 및 사회활동 지원에 관한 법률"),
        )

    def test_law_search_queries_prioritize_official_decree_over_alias_for_sensitive_identifier_questions(self):
        queries = RequestPipeline._law_search_queries(
            "노인일자리법에 근거해서 노인의 고유식별정보를 수집할 수 있는가",
            related_law_queries=["노인 일자리 및 사회활동 지원에 관한 법률"],
        )

        self.assertLess(
            queries.index("노인 일자리 및 사회활동 지원에 관한 법률 시행령"),
            queries.index("노인일자리법"),
        )
        self.assertLess(
            queries.index("노인 일자리 및 사회활동 지원에 관한 법률 시행령 고유식별정보의 처리"),
            queries.index("노인일자리법"),
        )

    def test_find_keyword_matched_article_prefers_best_sensitive_identifier_match_over_first_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiSeniorIdentifier(), logger=logger)

            matched = pipeline._find_keyword_matched_article(
                user_query="노인 일자리 및 사회활동 지원에 관한 법률에 근거해서 노인의 고유식별정보를 수집할 수 있는가",
                law_items=[
                    {"법령ID": "011357", "법령명한글": "개인정보 보호법"},
                    {"법령ID": "014765", "법령명한글": "노인 일자리 및 사회활동 지원에 관한 법률 시행령"},
                ],
            )

            self.assertIsNotNone(matched)
            self.assertEqual(matched["law_id"], "014765")
            self.assertEqual(matched["article_no"], "제14조")

    def test_process_prefers_official_decree_for_alias_sensitive_identifier_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiSeniorIdentifierAlias(), logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="노인일자리법에 근거해서 노인의 고유식별정보를 수집할 수 있는가",
                    context="기준시점: 2026-03-19",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(
                result.citations["law_context"]["primary_law"]["law_name"],
                "노인 일자리 및 사회활동 지원에 관한 법률 시행령",
            )
            self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제14조")

    def test_process_tracks_question_law_scope_for_alias_sensitive_identifier_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiSeniorIdentifierAlias(), logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="노인일자리법에 근거해서 노인의 고유식별정보를 수집할 수 있는가",
                    context="기준시점: 2026-03-19",
                )
            )

            self.assertIsNone(result.error)
            question_scope = result.citations["law_context"]["question_law_scope"]
            self.assertIn("노인", question_scope["target_law_family"])
            self.assertTrue(question_scope["direct_basis_found"])
            self.assertEqual(question_scope["article"]["article_no"], "제14조")

    def test_law_reference_search_queries_expand_descriptive_alias_without_manual_mapping(self):
        queries = RequestPipeline._law_reference_search_queries("전자상거래법")

        self.assertIn("전자상거래법", queries)
        self.assertIn("전자상거래", queries)
        self.assertIn("전자상거래 법률", queries)

    def test_resolve_official_law_queries_uses_search_results_to_canonicalize_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiAliasNormalization(), logger=logger)

            queries = pipeline._resolve_official_law_queries(
                "전자상거래법에 근거해서 청약철회 기간을 알려줘",
                [],
            )

            self.assertIn("전자상거래등에서의 소비자보호에 관한 법률", queries)
            self.assertIn("전자상거래법", queries)

    def test_process_canonicalizes_descriptive_alias_without_related_law_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            pipeline = RequestPipeline(law_api=FakeLawApiAliasNormalization(), logger=logger)

            result = pipeline.process(
                PipelineRequest(
                    user_query="전자상거래법에 근거해서 청약철회 기간을 설명해줘",
                    context="기준시점: 2026-03-19",
                )
            )

            self.assertIsNone(result.error)
            self.assertEqual(
                result.citations["law_context"]["primary_law"]["law_name"],
                "전자상거래등에서의 소비자보호에 관한 법률",
            )

    def test_candidate_law_references_include_common_alias_expansion(self):
        candidates = RequestPipeline._candidate_law_references("개보법 기준으로 설명해줘")

        self.assertIn("개인정보 보호법", candidates)

    def test_law_search_queries_include_common_alias_expansion(self):
        queries = RequestPipeline._law_search_queries(
            "개보법 기준으로 주민등록번호 처리 제한을 설명해줘",
            related_law_queries=[],
        )

        self.assertIn("개인정보 보호법", queries)

    def test_error_suggestion_records_reason_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
            )
            pipeline = RequestPipeline(
                law_api=FakeLawApiEmpty(),
                logger=logger,
                suggestion_store=suggestion_store,
            )

            result = pipeline.process(PipelineRequest(user_query="테스트"))

            self.assertIsNotNone(result.error)
            suggestions = suggestion_store.list_suggestions()
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0].suggestion_type, "law_search_gap")
            self.assertEqual(suggestions[0].reason_code, "empty_law_data")

    def test_approved_law_hint_override_is_used_for_official_query_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
            )
            suggestion = suggestion_store.create_or_update_suggestion(
                request_id="req-2",
                question_summary="가명처리 기준",
                user_query="가명처리 기준이 궁금해",
                question_intent="explain",
                related_law_queries=["개인정보 보호법"],
                issue_terms=["개인정보"],
                search_queries=["개인정보 보호법 가명처리"],
                proposed_keywords=["가명처리"],
            )
            suggestion_store.approve_suggestion(
                suggestion.id,
                law_name="개인정보 보호법",
                keywords=["가명처리"],
            )
            pipeline = RequestPipeline(
                law_api=FakeLawApiOk(),
                logger=logger,
                suggestion_store=suggestion_store,
            )

            queries = pipeline._resolve_official_law_queries("가명처리 기준을 설명해줘", [])

            self.assertIn("개인정보 보호법", queries)

    def test_process_records_question_scope_gap_suggestion_when_related_basis_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
            suggestion_store = LawHintSuggestionStore(
                suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
                overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
                rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
            )
            law_api = FakeLawApiSchoolYouth()
            pipeline = RequestPipeline(
                law_api=law_api,
                logger=logger,
                suggestion_store=suggestion_store,
            )

            result = pipeline.process(
                PipelineRequest(
                    user_query="학교 밖 청소년 지원에 관한 법률에 근거해서 주민등록번호를 수집할 수 있는가",
                    context="기준시점: 2026-03-18",
                )
            )

            self.assertIsNone(result.error)
            suggestions = suggestion_store.list_suggestions()
            self.assertEqual(len(suggestions), 1, result.citations["law_context"])
            self.assertEqual(suggestions[0].suggestion_type, "question_scope_gap")
            self.assertEqual(suggestions[0].reason_code, "question_scope_missing_direct_basis")
            self.assertIn("학교 밖 청소년", suggestions[0].question_law_family or "")
            self.assertFalse(suggestions[0].question_scope_direct_basis_found)
            self.assertTrue(suggestions[0].supplementary_law_name)
def _patched_test_approved_law_hint_override_is_used_for_related_queries(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        suggestion_store = LawHintSuggestionStore(
            suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
            overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
        )
        suggestion_store.create_override_rule(
            rule_type="law_family_priority",
            name="Prefer Example Tax Law",
            conditions={"trigger_phrases": ["instructor fee"]},
            action={"law_name": "Example Tax Law"},
        )
        pipeline = RequestPipeline(
            law_api=FakeLawApiOk(),
            logger=logger,
            suggestion_store=suggestion_store,
        )

        queries = pipeline._resolved_related_law_queries("How does instructor fee withholding work?")

        self.assertIn("Example Tax Law", queries)


def _patched_test_error_suggestion_records_reason_code(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        suggestion_store = LawHintSuggestionStore(
            suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
            overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
        )
        pipeline = RequestPipeline(
            law_api=FakeLawApiEmpty(),
            logger=logger,
            suggestion_store=suggestion_store,
        )

        result = pipeline.process(PipelineRequest(user_query="test"))

        self.assertIsNotNone(result.error)
        suggestions = suggestion_store.list_suggestions()
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].suggestion_type, "law_search_gap")
        self.assertEqual(suggestions[0].reason_code, "empty_law_data")
        self.assertEqual(suggestions[0].recommended_change_type, "law_search_gap_review")
        self.assertFalse(suggestions[0].runtime_safe)
        self.assertTrue(suggestions[0].approval_effect)


def _patched_test_approved_law_hint_override_is_used_for_official_query_resolution(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        suggestion_store = LawHintSuggestionStore(
            suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
            overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
        )
        suggestion_store.create_override_rule(
            rule_type="alias_normalization",
            name="Alias -> Personal Information Protection Act",
            conditions={"trigger_phrases": ["pipa"]},
            action={"law_name": "Personal Information Protection Act"},
        )
        pipeline = RequestPipeline(
            law_api=FakeLawApiOk(),
            logger=logger,
            suggestion_store=suggestion_store,
        )

        queries = pipeline._resolve_official_law_queries("Explain pipa masking", [])

        self.assertIn("Personal Information Protection Act", queries)


def _patched_test_process_records_question_scope_gap_suggestion_when_related_basis_is_used(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        suggestion_store = LawHintSuggestionStore(
            suggestions_path=str(Path(tmp) / "law_hint_suggestions.json"),
            overrides_path=str(Path(tmp) / "law_hint_overrides.json"),
            rules_path=str(Path(tmp) / "law_hint_override_rules.json"),
        )
        law_api = FakeLawApiSchoolYouth()
        pipeline = RequestPipeline(
            law_api=law_api,
            logger=logger,
            suggestion_store=suggestion_store,
        )

        result = pipeline.process(
            PipelineRequest(
                user_query="학교 밖 청소년 지원에 관한 법률에 근거해서 주민등록번호를 수집할 수 있는가",
                context="기준시점: 2026-03-18",
            )
        )

        self.assertIsNone(result.error)
        suggestions = suggestion_store.list_suggestions()
        self.assertEqual(len(suggestions), 1, result.citations["law_context"])
        self.assertEqual(suggestions[0].suggestion_type, "question_scope_gap")
        self.assertEqual(suggestions[0].reason_code, "question_scope_missing_direct_basis")
        self.assertIn("학교 밖 청소년", suggestions[0].question_law_family or "")
        self.assertFalse(suggestions[0].question_scope_direct_basis_found)
        self.assertTrue(suggestions[0].supplementary_law_name)
        self.assertEqual(suggestions[0].recommended_change_type, "decree_title_priority_review")
        self.assertFalse(suggestions[0].runtime_safe)
        self.assertTrue(suggestions[0].approval_effect)
        self.assertEqual(
            (suggestions[0].recommended_change_payload or {}).get("question_law_family"),
            suggestions[0].question_law_family,
        )


def _patched_test_process_adds_clarification_for_ambiguous_privacy_processing_question(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiOk()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="아파트 관리를 어떤 특정 업체에서 맡아서 할 수 있나? 그리고 그 업체에서는 주민들의 정보를 수집할 수 있어? 적법한 근거가 있는거야?",
                context="기준시점: 2026-03-20",
            )
        )

        self.assertIsNone(result.error)
        self.assertIsNotNone(result.clarification)
        self.assertTrue(result.clarification["clarification_needed"])
        self.assertGreaterEqual(len(result.clarification["clarification_questions"]), 2)
        self.assertIn("법적 지위", " ".join(result.clarification["missing_facts"]))
        self.assertTrue(any("관리주체" in question for question in result.clarification["clarification_questions"]))
        self.assertTrue(any("직접 받는 상황" in question for question in result.clarification["clarification_questions"]))
        self.assertIn("[추가 확인 필요]", result.answer)
        self.assertIsNotNone(result.answer_plan)
        self.assertTrue(result.answer_plan["clarification"]["clarification_needed"])
        self.assertTrue(result.answer_plan["privacy_processing_question"])
        self.assertIn("수집", result.answer_plan["processing_actions"])
        self.assertIsNotNone(result.answer_plan["privacy_analysis"])
        self.assertTrue(result.answer_plan["privacy_analysis"]["clarification_needed"])
        self.assertIn("수집", result.answer_plan["privacy_analysis"]["processing_actions"])
        self.assertTrue(
            any(
                checkpoint.startswith("개인정보 보호법 제15조")
                for checkpoint in result.answer_plan["privacy_analysis"]["legal_basis_checkpoints"]
            )
        )
        self.assertNotIn("제공", result.answer_plan["privacy_analysis"]["processing_actions"])


def _patched_test_process_persists_fallback_question_scope_into_answer_plan(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiQuestionScopeFallback()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="전자상거래법에 근거해서 주민등록번호를 수집할 수 있나?",
                context="기준시점: 2026-03-20",
            )
        )

        self.assertIsNone(result.error)
        self.assertIsNotNone(result.answer_plan)
        self.assertIsNotNone(result.answer_plan["question_law_scope"])
        self.assertEqual(result.answer_plan["question_law_scope"]["target_law_family"], "전자상거래법")
        self.assertEqual(result.answer_plan["question_law_scope"]["status"], "supplementary_basis_used")


def _patched_test_sensitive_identifier_title_queries_include_rrn_title(self):
    queries = RequestPipeline._sensitive_identifier_title_queries("공동주택관리법")

    self.assertIn("공동주택관리법 시행령 고유식별정보의 처리", queries)
    self.assertIn("공동주택관리법 시행령 민감정보 및 고유식별정보의 처리", queries)
    self.assertIn("공동주택관리법 시행령 주민등록번호의 처리", queries)


def _patched_test_contextual_article_priority_avoids_generic_privacy_decree_as_primary(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiApartmentContextPriority()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="공동주택(아파트) 관리에서 관리주체가 외부 특정 업체에 관리업무를 맡길 수 있는지, 그리고 그 업체가 입주민 개인정보를 처리할 수 있는지",
                context="기준시점: 2026-03-20",
            )
        )

        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "공동주택관리법")
        article = result.citations["law_context"].get("article") or {}
        self.assertNotEqual(article.get("article_no"), "제62조의2")
        related_law_names = [item["law_name"] for item in result.citations["law_context"].get("related_laws") or [] if item.get("law_name")]
        self.assertIn("개인정보 보호법", related_law_names)


RequestPipelineTests.test_approved_law_hint_override_is_used_for_related_queries = _patched_test_approved_law_hint_override_is_used_for_related_queries
RequestPipelineTests.test_error_suggestion_records_reason_code = _patched_test_error_suggestion_records_reason_code
RequestPipelineTests.test_approved_law_hint_override_is_used_for_official_query_resolution = _patched_test_approved_law_hint_override_is_used_for_official_query_resolution
RequestPipelineTests.test_process_records_question_scope_gap_suggestion_when_related_basis_is_used = _patched_test_process_records_question_scope_gap_suggestion_when_related_basis_is_used
RequestPipelineTests.test_process_adds_clarification_for_ambiguous_privacy_processing_question = _patched_test_process_adds_clarification_for_ambiguous_privacy_processing_question
RequestPipelineTests.test_process_persists_fallback_question_scope_into_answer_plan = _patched_test_process_persists_fallback_question_scope_into_answer_plan
RequestPipelineTests.test_sensitive_identifier_title_queries_include_rrn_title = _patched_test_sensitive_identifier_title_queries_include_rrn_title
RequestPipelineTests.test_contextual_article_priority_avoids_generic_privacy_decree_as_primary = _patched_test_contextual_article_priority_avoids_generic_privacy_decree_as_primary


def _patched_test_process_promotes_rrn_question_to_general_law_article_24_2(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiRrnGeneralLawFallback()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="주민등록번호 수집할 때 정보주체한테 동의받아서 처리하면 되지?",
                context="기준시점: 2026-03-20",
            )
        )

        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제24조의2")
        self.assertIn("동의만으로 처리할 수 없고", result.answer)
        self.assertIn("제24조의2", result.answer)


RequestPipelineTests.test_process_promotes_rrn_question_to_general_law_article_24_2 = _patched_test_process_promotes_rrn_question_to_general_law_article_24_2


def _patched_test_process_promotes_rrn_question_even_when_decree_article_is_unrelated(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiRrnImpactAssessmentFallback()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="주민등록번호 수집할 때 정보주체한테 동의받아서 처리하면 되지?",
                context="기준시점: 2026-03-23",
            )
        )

        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제24조의2")
        self.assertIn("동의만으로 처리할 수 없고", result.answer)
        self.assertNotIn("개인정보 영향평가의 대상", result.answer)


RequestPipelineTests.test_process_promotes_rrn_question_even_when_decree_article_is_unrelated = _patched_test_process_promotes_rrn_question_even_when_decree_article_is_unrelated


def _patched_test_process_promotes_sensitive_info_question_to_general_law_article_23(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiSensitiveInfoImpactAssessmentFallback()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="민감정보를 동의받아 처리하면 되지?",
                context="기준시점: 2026-03-23",
            )
        )

        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제23조")


RequestPipelineTests.test_process_promotes_sensitive_info_question_to_general_law_article_23 = _patched_test_process_promotes_sensitive_info_question_to_general_law_article_23


def _patched_test_question_law_scope_updates_after_general_privacy_promotion(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        law_api = FakeLawApiRrnImpactAssessmentFallback()
        pipeline = RequestPipeline(law_api=law_api, logger=logger)

        result = pipeline.process(
            PipelineRequest(
                user_query="주민등록번호 수집할 때 정보주체한테 동의받아서 처리하면 되지?",
                context="기준시점: 2026-03-23",
            )
        )

        question_scope = result.answer_plan["question_law_scope"]
        self.assertEqual(question_scope["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(question_scope["article"]["article_no"], "제24조의2")
        self.assertEqual(question_scope["status"], "direct_basis_found")


RequestPipelineTests.test_question_law_scope_updates_after_general_privacy_promotion = _patched_test_question_law_scope_updates_after_general_privacy_promotion


def _patched_test_privacy_question_categories_detect_rights_procedure_and_sanction(self):
    categories = RequestPipeline._privacy_question_categories(
        "동의 철회 방법을 어렵게 하면 과태료가 있나?"
    )

    self.assertEqual(
        categories,
        ["정보주체 권리", "절차/방법", "제재/책임"],
    )


RequestPipelineTests.test_privacy_question_categories_detect_rights_procedure_and_sanction = _patched_test_privacy_question_categories_detect_rights_procedure_and_sanction


def _patched_test_privacy_category_relevance_penalizes_generic_processing_article(self):
    generic_score = RequestPipeline._privacy_category_relevance_adjustment(
        user_query="동의 철회 방법을 어렵게 하면 과태료가 있나?",
        law_name="개인정보 보호법 시행령",
        article_text="제70조의2(고유식별정보의 처리) 보호위원회는 다음 각 호의 사무를 수행하기 위하여 불가피한 경우 ...",
    )
    sanction_score = RequestPipeline._privacy_category_relevance_adjustment(
        user_query="동의 철회 방법을 어렵게 하면 과태료가 있나?",
        law_name="개인정보 보호법",
        article_text="제39조(동의의 철회 등) 정보주체는 동의를 철회할 수 있으며 ... 과태료 ...",
    )

    self.assertLess(generic_score, 0)
    self.assertGreater(sanction_score, generic_score)


RequestPipelineTests.test_privacy_category_relevance_penalizes_generic_processing_article = _patched_test_privacy_category_relevance_penalizes_generic_processing_article


def _patched_test_query_mode_detects_framework_overview(self):
    query_mode = RequestPipeline._query_mode("문자 광고나 온라인 광고에 관련된 법적 근거를 알려줘")
    aspects = RequestPipeline._framework_aspects("문자 광고나 온라인 광고에 관련된 법적 근거를 알려줘")

    self.assertEqual(query_mode, "framework_overview")
    self.assertIn("transmission", aspects)
    self.assertIn("representation", aspects)
    self.assertIn("commerce", aspects)


RequestPipelineTests.test_query_mode_detects_framework_overview = _patched_test_query_mode_detects_framework_overview


def _patched_test_query_mode_keeps_single_basis_for_specific_article_question(self):
    query_mode = RequestPipeline._query_mode("개인정보 보호법 제24조의2가 무슨 뜻이야?")

    self.assertEqual(query_mode, "single_basis")


RequestPipelineTests.test_query_mode_keeps_single_basis_for_specific_article_question = _patched_test_query_mode_keeps_single_basis_for_specific_article_question


def _patched_test_framework_law_profiles_can_load_from_external_file(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "framework_law_profiles.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "axis": "테스트 축",
                        "law_family": "테스트 법률",
                        "aspects": ["processing", "rights"],
                        "article_numbers": ["제1조", "제2조"],
                        "description": "테스트 설명",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        original_path = RequestPipeline._FRAMEWORK_LAW_PROFILES_PATH
        original_cache = RequestPipeline._framework_law_profiles_cache
        try:
            RequestPipeline._FRAMEWORK_LAW_PROFILES_PATH = path
            RequestPipeline._framework_law_profiles_cache = None
            profiles = RequestPipeline._framework_law_profiles()
        finally:
            RequestPipeline._FRAMEWORK_LAW_PROFILES_PATH = original_path
            RequestPipeline._framework_law_profiles_cache = original_cache

    self.assertEqual(len(profiles), 1)
    self.assertEqual(profiles[0]["axis"], "테스트 축")
    self.assertEqual(profiles[0]["law_family"], "테스트 법률")
    self.assertEqual(tuple(profiles[0]["article_numbers"]), ("제1조", "제2조"))


RequestPipelineTests.test_framework_law_profiles_can_load_from_external_file = _patched_test_framework_law_profiles_can_load_from_external_file


def _patched_test_build_framework_axes_uses_multiple_law_families(self):
    with tempfile.TemporaryDirectory() as tmp:
        logger = CostLogger(db_path=str(Path(tmp) / "cost_logs.db"))
        pipeline = RequestPipeline(law_api=FakeLawApiOk(), logger=logger)

        def _fake_fetch_article(_law_id, article_no, _metrics=None):
            return {
                "found": True,
                "article_no": article_no,
                "article_base_no": article_no,
                "article_text": f"{article_no} 관련 조문",
            }

        pipeline._fetch_article = _fake_fetch_article

        law_data = {
            "LawSearch": {
                "law": [
                    {"법령ID": "1", "법령명한글": "정보통신망 이용촉진 및 정보보호 등에 관한 법률"},
                    {"법령ID": "2", "법령명한글": "개인정보 보호법"},
                    {"법령ID": "3", "법령명한글": "표시ㆍ광고의 공정화에 관한 법률"},
                    {"법령ID": "4", "법령명한글": "전자상거래 등에서의 소비자보호에 관한 법률"},
                ]
            }
        }

        axes = pipeline._build_framework_axes(
            user_query="문자 광고나 온라인 광고에 관련된 법적 근거를 알려줘",
            law_data=law_data,
        )

        self.assertGreaterEqual(len(axes), 2)
        self.assertTrue(any(axis["law_name"] == "정보통신망 이용촉진 및 정보보호 등에 관한 법률" for axis in axes))
        self.assertTrue(
            any(
                axis["law_name"] in {"표시ㆍ광고의 공정화에 관한 법률", "전자상거래 등에서의 소비자보호에 관한 법률"}
                for axis in axes
            )
        )


RequestPipelineTests.test_build_framework_axes_uses_multiple_law_families = _patched_test_build_framework_axes_uses_multiple_law_families


if __name__ == "__main__":
    unittest.main()
