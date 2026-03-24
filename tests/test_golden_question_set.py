import tempfile
import unittest
from pathlib import Path

from src.cost_logger import CostLogger
from src.request_pipeline import PipelineRequest, RequestPipeline


class GoldenBaseLawApi:
    def __init__(self):
        self.search_queries = []
        self.article_calls = []

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

    def get_version(self, law_id):
        return {
            "law_id": law_id,
            "version_fields": {"시행일자": "20251002", "공포일자": "20250923"},
        }

    def get_article(self, law_id, article_no):
        self.article_calls.append((law_id, article_no))
        return {
            "law_id": law_id,
            "article_no": article_no,
            "found": True,
            "matched_via": "service:law",
            "article_text": f"{article_no} 테스트 조문 본문",
        }

    def search_precedent(self, query, reference_law=None):
        return {"PrecSearch": {"prec": []}}

    def search_related_laws(self, query=None, law_id=None):
        return {"lsRltSearch": {"법령": {"관련법령": []}}}

    def find_article_by_keywords(self, law_id, keywords):
        return None


class GoldenRrnLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011468",
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
        if law_id == "011468":
            return {
                "law_id": "011468",
                "article_no": "제35조",
                "article_base_no": "제35조",
                "article_text": "제35조(개인정보 영향평가의 대상) 개인정보파일 규모에 관한 조문",
                "matched_clauses": [
                    {
                        "article_no": "제35조 제1호",
                        "article_base_no": "제35조",
                        "article_text": "민감정보 또는 고유식별정보의 처리가 수반되는 개인정보파일",
                        "score": 11,
                    }
                ],
                "matched_via": "service:law:keyword_scan",
                "score": 11,
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


class GoldenSensitiveInfoLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {
                        "법령ID": "011468",
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
        if law_id == "011468":
            return {
                "law_id": "011468",
                "article_no": "제35조",
                "article_base_no": "제35조",
                "article_text": "제35조(개인정보 영향평가의 대상) 개인정보파일 규모에 관한 조문",
                "matched_clauses": [
                    {
                        "article_no": "제35조 제1호",
                        "article_base_no": "제35조",
                        "article_text": "민감정보 또는 고유식별정보의 처리가 수반되는 개인정보파일",
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


class GoldenIdentifierLawApi(GoldenBaseLawApi):
    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제24조",
                "article_base_no": "제24조",
                "article_text": "제24조(고유식별정보의 처리) 개인정보처리자는 법령에서 허용하는 경우 또는 정보주체의 별도 동의가 있는 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        return None


class GoldenSchoolYouthLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        if query == "청소년복지 지원법 시행령":
            return {
                "LawSearch": {
                    "law": [
                        {"법령ID": "009682", "법령명한글": "청소년복지 지원법 시행령", "법령일련번호": "9682"}
                    ]
                }
            }
        if query == "청소년복지 지원법":
            return {
                "LawSearch": {
                    "law": [
                        {"법령ID": "009681", "법령명한글": "청소년복지 지원법", "법령일련번호": "9681"}
                    ]
                }
            }
        if query == "청소년 기본법 시행령":
            return {
                "LawSearch": {
                    "law": [
                        {"법령ID": "005206", "법령명한글": "청소년 기본법 시행령", "법령일련번호": "5206"}
                    ]
                }
            }
        if query == "청소년 기본법":
            return {
            "LawSearch": {
                    "law": [
                        {"법령ID": "000816", "법령명한글": "청소년 기본법", "법령일련번호": "816"}
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
                                "관련법률ID": "000816",
                                "관련법령명": "청소년 기본법",
                                "관련법령본문링크": "https://www.law.go.kr/법령/청소년기본법",
                                "법령관계구분": "3유형(기본법)",
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
                                "관련법률ID": "009681",
                                "관련법령명": "청소년복지 지원법",
                                "관련법령본문링크": "https://www.law.go.kr/법령/청소년복지지원법",
                                "법령관계구분": "4유형(개별법)",
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
                "article_no": "제18조",
                "article_base_no": "제18조",
                "article_text": "제18조(민감정보 및 고유식별정보의 처리) 법 제6조에 따른 가정 밖 청소년의 발생 예방 및 보호·지원 사무",
                "matched_via": "service:law:keyword_scan",
                "score": 7,
            }
        return None


class GoldenSeniorAliasLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        if query in {"노인일자리법", "노인일자리법 시행령", "노인일자리법 시행규칙"}:
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
        if law_id == "014765":
            return {
                "law_id": "014765",
                "article_no": "제14조",
                "article_base_no": "제14조",
                "article_text": "제14조(민감정보 및 고유식별정보의 처리) 수행기관 등이 법정 사무를 수행하기 위하여 필요한 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제24조",
                "article_base_no": "제24조",
                "article_text": "제24조(고유식별정보의 처리) 개인정보처리자는 법령에서 허용하는 경우 처리할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        return None


class GoldenApartmentLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {"법령ID": "011468", "법령명한글": "개인정보 보호법 시행령", "법령일련번호": "270352"},
                    {"법령ID": "012345", "법령명한글": "공동주택관리법", "법령일련번호": "280069"},
                    {"법령ID": "011357", "법령명한글": "개인정보 보호법", "법령일련번호": "270351"},
                ]
            }
        }

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "011468":
            return {
                "law_id": "011468",
                "article_no": "제62조의2",
                "article_base_no": "제62조의2",
                "article_text": "제62조의2(민감정보 및 고유식별정보의 처리) 보호위원회 등의 사무에 관한 조문",
                "matched_via": "service:law:keyword_scan",
                "score": 9,
            }
        if law_id == "012345":
            return {
                "law_id": "012345",
                "article_no": "제7조",
                "article_base_no": "제7조",
                "article_text": "제7조(관리방법의 결정 및 변경) 입주자대표회의는 위탁관리인 경우 주택관리업자 선정을 포함하여 관리방법을 결정한다.",
                "matched_via": "service:law:keyword_scan",
                "score": 6,
            }
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제26조",
                "article_base_no": "제26조",
                "article_text": "제26조(업무위탁에 따른 개인정보의 처리 제한) 개인정보처리자는 위탁업무 수행 목적 범위에서만 처리하게 하여야 한다.",
                "matched_via": "service:law:keyword_scan",
                "score": 7,
            }
        return None


class GoldenFrameworkLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {"법령ID": "000030", "법령명한글": "정보통신망 이용촉진 및 정보보호 등에 관한 법률"},
                    {"법령ID": "011357", "법령명한글": "개인정보 보호법"},
                    {"법령ID": "000902", "법령명한글": "표시ㆍ광고의 공정화에 관한 법률"},
                    {"법령ID": "009908", "법령명한글": "전자상거래 등에서의 소비자보호에 관한 법률"},
                ]
            }
        }

    def get_article(self, law_id, article_no):
        self.article_calls.append((law_id, article_no))
        return {
            "law_id": law_id,
            "article_no": article_no,
            "found": True,
            "matched_via": "service:law",
            "article_text": f"{article_no} 관련 조문",
        }


class GoldenSmsOptoutLawApi(GoldenBaseLawApi):
    def search_law(self, query):
        self.search_queries.append(query)
        return {
            "LawSearch": {
                "law": [
                    {"법령ID": "000030", "법령명한글": "정보통신망 이용촉진 및 정보보호 등에 관한 법률"},
                    {"법령ID": "011357", "법령명한글": "개인정보 보호법"},
                ]
            }
        }

    def find_article_by_keywords(self, law_id, keywords):
        if law_id == "000030":
            return {
                "law_id": "000030",
                "article_no": "제50조",
                "article_base_no": "제50조",
                "article_text": "제50조(영리목적의 광고성 정보 전송 제한) 수신거부 의사에 반하여 광고성 정보를 전송하여서는 아니 된다.",
                "matched_via": "service:law:keyword_scan",
                "score": 10,
            }
        if law_id == "011357":
            return {
                "law_id": "011357",
                "article_no": "제15조",
                "article_base_no": "제15조",
                "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 수집·이용할 수 있다.",
                "matched_via": "service:law:keyword_scan",
                "score": 4,
            }
        return None


class GoldenQuestionSetTests(unittest.TestCase):
    def _pipeline(self, law_api):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        logger = CostLogger(db_path=str(Path(tmp.name) / "cost_logs.db"))
        return RequestPipeline(law_api=law_api, logger=logger)

    def test_golden_rrn_consent_question(self):
        pipeline = self._pipeline(GoldenRrnLawApi())
        result = pipeline.process(PipelineRequest(user_query="주민등록번호 수집할 때 정보주체한테 동의받아서 처리하면 되지?"))
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제24조의2")
        self.assertIn("동의만으로 처리할 수 없고", result.answer)
        self.assertNotIn("개인정보 영향평가", result.answer)

    def test_golden_sensitive_info_consent_question(self):
        pipeline = self._pipeline(GoldenSensitiveInfoLawApi())
        result = pipeline.process(PipelineRequest(user_query="민감정보는 동의받으면 처리할 수 있나?"))
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "개인정보 보호법")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제23조")
        self.assertTrue(
            any("제23조" in checkpoint for checkpoint in result.answer_plan["privacy_analysis"]["legal_basis_checkpoints"])
        )

    def test_golden_identifier_consent_question(self):
        pipeline = self._pipeline(GoldenIdentifierLawApi())
        result = pipeline.process(PipelineRequest(user_query="고유식별정보는 동의만 있으면 처리 가능한가?"))
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제24조")
        self.assertIn("주민등록번호 외 고유식별정보", result.answer)

    def test_golden_school_youth_question(self):
        pipeline = self._pipeline(GoldenSchoolYouthLawApi())
        result = pipeline.process(PipelineRequest(user_query="학교밖청소년지원센터는 주민등록번호 수집 가능 함?"))
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "청소년복지 지원법 시행령")
        related_laws = [item["law_name"] for item in result.citations["law_context"]["related_laws"]]
        self.assertIn("청소년 기본법", related_laws)
        self.assertIn("청소년복지 지원법", related_laws)

    def test_golden_senior_identifier_question(self):
        pipeline = self._pipeline(GoldenSeniorAliasLawApi())
        result = pipeline.process(PipelineRequest(user_query="노인일자리법에 근거해서 노인의 고유식별정보를 수집할 수 있는가?"))
        self.assertIsNone(result.error)
        self.assertEqual(
            result.citations["law_context"]["primary_law"]["law_name"],
            "노인 일자리 및 사회활동 지원에 관한 법률 시행령",
        )
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제14조")
        self.assertIn("노인", result.answer_plan["question_law_scope"]["target_law_family"])

    def test_golden_apartment_management_question(self):
        pipeline = self._pipeline(GoldenApartmentLawApi())
        result = pipeline.process(
            PipelineRequest(user_query="아파트 관리를 어떤 특정 업체에서 맡아서 할 수 있나? 그리고 그 업체에서는 주민들의 정보를 수집할 수 있어?")
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "공동주택관리법")
        self.assertNotEqual(result.citations["law_context"]["article"]["article_no"], "제62조의2")
        related_laws = [item["law_name"] for item in result.citations["law_context"]["related_laws"]]
        self.assertIn("개인정보 보호법", related_laws)

    def test_golden_withdrawal_sanction_question_tags(self):
        categories = RequestPipeline._privacy_question_categories("동의 철회 방법을 어렵게 하면 어떤 조항으로 처벌되나?")
        self.assertEqual(categories, ["정보주체 권리", "절차/방법", "제재/책임"])
        generic_score = RequestPipeline._privacy_category_relevance_adjustment(
            user_query="동의 철회 방법을 어렵게 하면 어떤 조항으로 처벌되나?",
            law_name="개인정보 보호법 시행령",
            article_text="제62조의2(고유식별정보의 처리) 처리 기준",
        )
        sanction_score = RequestPipeline._privacy_category_relevance_adjustment(
            user_query="동의 철회 방법을 어렵게 하면 어떤 조항으로 처벌되나?",
            law_name="개인정보 보호법",
            article_text="제39조 동의 철회와 위반 시 과태료",
        )
        self.assertLess(generic_score, sanction_score)

    def test_golden_framework_overview_query(self):
        pipeline = self._pipeline(GoldenFrameworkLawApi())
        result = pipeline.process(PipelineRequest(user_query="문자 광고나 온라인 광고에 관련된 법적 근거를 알려줘"))
        self.assertIsNone(result.error)
        self.assertEqual(result.answer_plan["query_mode"], "framework_overview")
        axis_names = [axis["axis"] for axis in result.answer_plan["framework_axes"]]
        self.assertIn("광고성 정보 전송 규제", axis_names)
        self.assertIn("광고 목적 개인정보 활용", axis_names)

    def test_golden_specific_article_question_stays_single_basis(self):
        self.assertEqual(RequestPipeline._query_mode("개인정보 보호법 제24조의2가 무슨 뜻이야?"), "single_basis")

    def test_golden_sms_optout_question(self):
        pipeline = self._pipeline(GoldenSmsOptoutLawApi())
        result = pipeline.process(PipelineRequest(user_query="문자 광고 수신거부를 했는데 계속 오면 위반이야?"))
        self.assertIsNone(result.error)
        self.assertEqual(result.citations["law_context"]["primary_law"]["law_name"], "정보통신망 이용촉진 및 정보보호 등에 관한 법률")
        self.assertEqual(result.citations["law_context"]["article"]["article_no"], "제50조")


if __name__ == "__main__":
    unittest.main()
