import unittest

from src.answer_composer import AnswerComposer, AnswerCompositionInput


PROMPT_PAYLOAD = {
    "system": (
        "응답은 법령 원문 근거가 있는 내용만 포함한다. "
        "근거가 없는 문장은 출력하지 않는다. "
        "과장, 추정, 일반화를 금지한다. "
        "기초 사실이 불명확하면 확인 필요 항목을 반환한다. "
        "근거-주장 매핑을 통과한 문장만 최종 답변으로 구성한다."
    ),
    "user": "테스트 사용자 질의",
}


class AnswerComposerTests(unittest.TestCase):
    def setUp(self):
        self.composer = AnswerComposer()

    def test_compose_article_answer_for_purpose_article(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제1조 설명",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "article": {
                        "found": True,
                        "article_no": "제1조",
                        "article_text": "제1조(목적) 이 법은 개인정보의 처리 및 보호에 관한 사항을 정한다.",
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("개인정보 보호법 제1조는 목적에 관한 규정입니다.", result)
        self.assertIn("현재 확인한 조문은 다음과 같습니다.", result)
        self.assertIn("이 조문은 개인정보 보호법이 왜 존재하는지", result)
        self.assertIn("[근거]", result)
        self.assertIn("- 법령: 개인정보 보호법", result)
        self.assertIn("- 조문: 제1조", result)

    def test_compose_article_answer_for_high_risk_sanction_article(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="벌칙 조항 위법 여부 설명",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제75조",
                        "article_text": "제75조(과태료) 다음 각 호의 어느 하나에 해당하는 자에게 과태료를 부과한다.",
                    },
                },
                risk_level="HIGH",
                fallback_answer="",
            )
        )

        self.assertIn("위법 여부를 판단할 때 참고해야 할 기준 중 하나", result)
        self.assertIn("제재 기준을 정한 조문", result)
        self.assertIn("[판단 순서]", result)
        self.assertIn("선행 의무조항이나 금지조항 위반이 있는지 먼저 확인", result)
        self.assertIn("주체, 시점, 예외 사유", result)

    def test_compose_illegality_answer_for_non_sanction_article(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제15조가 위법 판단 기준인지 설명해줘",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제15조",
                        "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 수집할 수 있다.",
                    },
                    "related_articles": [
                        {
                            "found": True,
                            "article_no": "제17조",
                            "article_text": "제17조(개인정보의 제공) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 제공할 수 있다.",
                        }
                    ],
                },
                risk_level="HIGH",
                fallback_answer="",
            )
        )

        self.assertIn("[판단 순서]", result)
        self.assertIn("대상과 상황에 해당하는지 먼저 봅니다", result)
        self.assertIn("[추가 확인 포인트]", result)
        self.assertIn("제17조(개인정보의 제공)", result)

    def test_compose_applicability_answer_adds_scope_checklist(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="이 경우에도 개인정보 보호법 제3조가 적용되는지 설명해줘",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제3조",
                        "article_text": "제3조(적용범위) 이 법은 공공기관과 사업자에게 적용한다.",
                    },
                    "related_articles": [
                        {
                            "found": True,
                            "article_no": "제8조",
                            "article_text": "제8조(적용의 일부 제외) 이 법의 일부 규정은 다음 각 호의 경우에는 적용하지 아니한다.",
                        }
                    ],
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("[적용 판단 포인트]", result)
        self.assertIn("주체나 기관에 포함되는지", result)
        self.assertIn("적용 범위를 직접 정하고 있으므로", result)
        self.assertIn("[함께 볼 조문]", result)
        self.assertIn("제8조(적용의 일부 제외)", result)
        self.assertIn("[적용 참고 조문]", result)

    def test_compose_high_risk_answer_adds_precedent_block_and_summary(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제15조가 위법 판단 기준인지 설명하고 관련 판례도 보여줘",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "article": {
                        "found": True,
                        "article_no": "제15조",
                        "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 수집할 수 있다.",
                    },
                    "primary_precedent": {
                        "사건명": "개인정보 보호법 사건",
                        "사건번호": "2025두2345",
                        "법원명": "대법원",
                        "선고일자": "20250101",
                    },
                    "precedent_detail": {
                        "판결요지": "동의 없는 개인정보 수집이 허용되는지 여부는 법정 요건 충족 여부를 엄격하게 본다."
                    },
                    "used_precedent_query": "개인정보 보호법 제15조 판례",
                    "review_summary": {"precedent_relevance_note": "제15조와 직접 연결된 검색"},
                },
                risk_level="HIGH",
                fallback_answer="",
            )
        )

        self.assertIn("[참고 판례]", result)
        self.assertIn("개인정보 보호법 사건", result)
        self.assertIn("- 판례 검색 기준: 개인정보 보호법 제15조 판례", result)
        self.assertIn("- 판례 요지: 동의 없는 개인정보 수집이 허용되는지 여부는", result)
        self.assertIn("- 해석상 의미: 이 판례는", result)

    def test_compose_fallback_for_related_law_without_article(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 처리 위법 여부",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "used_search_query": "개인정보 보호법",
                },
                risk_level="HIGH",
                fallback_answer="",
            )
        )

        self.assertIn("질문과 가장 관련된 법령은 개인정보 보호법입니다.", result)
        self.assertIn("현재 확인한 시행일자는 20251002입니다.", result)
        self.assertIn("단정적으로 결론내리기보다", result)
        self.assertIn("- 검색 기준: 개인정보 보호법", result)

    def test_compose_article_answer_for_scope_article(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="적용범위 조항 설명",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "가상 법령"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제3조",
                        "article_text": "제3조(적용범위) 이 법은 국가기관과 공공기관에 적용한다.",
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("어떤 대상이나 상황에 적용되는지 가늠할 때 기준이 되는 조문", result)
        self.assertIn("범위를 정해주는 조문", result)

    def test_compose_high_risk_fallback_without_version_is_cautious(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="위법 여부 판단",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={"primary_law": {"law_name": "가상 법령"}},
                risk_level="HIGH",
                fallback_answer="",
            )
        )

        self.assertIn("시행일자를 특정하지 못했습니다.", result)
        self.assertIn("단정적으로 결론내리기보다", result)

    def test_compose_difference_question_adds_related_articles(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제1조와 제2조 차이를 설명해줘",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제1조",
                        "article_text": "제1조(목적) 이 법의 목적을 정한다.",
                    },
                    "related_articles": [
                        {
                            "found": True,
                            "article_no": "제2조",
                            "article_text": "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.",
                        }
                    ],
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("다른 조문과 비교할 때 기준점이 되는 조문", result)
        self.assertIn("[비교 요약]", result)
        self.assertIn("제1조가 목적에 초점을 둔다면 제2조는 정의 쪽에 무게가 실려 있습니다.", result)
        self.assertIn("[비교 참고 조문]", result)
        self.assertIn("제2조(정의)", result)

    def test_compose_procedure_question_adds_staged_steps(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제34조와 제34조의2 절차를 설명해줘",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법"},
                    "version": {"version_fields": {}},
                    "article": {
                        "found": True,
                        "article_no": "제34조",
                        "article_text": "제34조(개인정보 유출 통지) 개인정보 유출 시 정보주체에게 통지해야 한다.",
                    },
                    "related_articles": [
                        {
                            "found": True,
                            "article_no": "제34조의2",
                            "article_text": "제34조의2(유출 신고) 개인정보 유출 시 감독기관에 신고해야 한다.",
                        }
                    ],
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("절차나 처리 순서를 이해할 때 먼저 확인할 조문", result)
        self.assertIn("[절차 정리]", result)
        self.assertIn("1. 먼저 제34조의 기본 의무나 출발 절차를 확인합니다.", result)
        self.assertIn("2. 이어서 제34조의2(유출 신고)", result)
        self.assertIn("[연관 조문]", result)

    def test_compose_prompt_rules_force_cautious_fallback(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="애매한 질문",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={},
                risk_level="LOW",
                fallback_answer="어떤 식으로든 대답합니다.",
            )
        )

        self.assertIn("단정적으로 답하기 어렵습니다", result)


    def test_compose_includes_law_and_article_links_in_evidence_block(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제1조 설명",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {
                        "law_name": "개인정보 보호법",
                        "law_link": "https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&type=HTML",
                    },
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "article": {
                        "found": True,
                        "law_id": "011357",
                        "article_no": "제1조",
                        "article_link": "https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&JO=000100&type=HTML",
                        "article_text": "제1조(목적) 테스트 조문 본문",
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("- 법령 링크: https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&type=HTML", result)
        self.assertIn(
            "- 조문 링크: https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&JO=000100&type=HTML",
            result,
        )

    def test_compose_strips_oc_from_link_fields(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="개인정보 보호법 제1조 설명",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {
                        "law_name": "개인정보 보호법",
                        "law_link": "https://www.law.go.kr/DRF/lawService.do?OC=secret-value&target=law&ID=011357&type=HTML",
                    },
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "article": {
                        "found": True,
                        "law_id": "011357",
                        "article_no": "제1조",
                        "article_link": "https://www.law.go.kr/DRF/lawService.do?OC=secret-value&target=law&ID=011357&JO=000100&type=HTML",
                        "article_text": "제1조(목적) 테스트 조문 본문",
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertNotIn("OC=", result)
        self.assertIn(
            "- 법령 링크: https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&type=HTML",
            result,
        )
        self.assertIn(
            "- 조문 링크: https://www.law.go.kr/DRF/lawService.do?target=law&ID=011357&JO=000100&type=HTML",
            result,
        )


    def test_compose_includes_directly_related_clauses_block(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="학교밖청소년지원센터는 주민등록번호 수집 가능 함?",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "청소년복지 지원법 시행령"},
                    "version": {"version_fields": {"?쒗뻾?쇱옄": "20251118"}},
                    "article": {
                        "found": True,
                        "law_id": "009908",
                        "article_no": "제18조",
                        "article_text": "제18조(민감정보 및 고유식별정보의 처리) ...",
                        "matched_clauses": [
                            {
                                "article_no": "제18조 제3호의2",
                                "article_text": "법 제12조의2에 따른 통합정보시스템의 구축ㆍ운영 등에 관한 사무",
                            },
                            {
                                "article_no": "제18조 제6호",
                                "article_text": "법 제16조에 따른 가정 밖 청소년의 발생 예방 및 보호ㆍ지원에 관한 사무",
                            },
                        ],
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("[결론]", result)
        self.assertIn("[조문]", result)
        self.assertIn("[직접 관련 항목]", result)
        self.assertIn("[근거]", result)
        self.assertIn("제18조 제3호의2", result)
        self.assertIn("제18조 제6호", result)

    def test_compose_separates_question_law_scope_from_supplementary_basis(self):
        result = self.composer.compose(
            AnswerCompositionInput(
                user_query="노인일자리법에 근거해서 노인의 고유식별정보를 수집할 수 있는가?",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {"law_name": "개인정보 보호법 시행령"},
                    "question_law_scope": {
                        "target_law_family": "노인 일자리 및 사회활동 지원에 관한 법률",
                        "matched_laws": [
                            {"law_name": "노인 일자리 및 사회활동 지원에 관한 법률"},
                            {"law_name": "노인 일자리 및 사회활동 지원에 관한 법률 시행령"},
                        ],
                        "direct_basis_found": False,
                    },
                    "version": {"version_fields": {"시행일자": "20251002"}},
                    "article": {
                        "found": True,
                        "article_no": "제24조",
                        "article_text": "제24조(고유식별정보의 처리) 개인정보처리자는 법령에서 허용하는 경우 처리할 수 있다.",
                    },
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("[질문 기준 법령 검토]", result)
        self.assertIn("노인 일자리 및 사회활동 지원에 관한 법률 및 같은 법 시행령/시행규칙에서 직접 근거 조항을 우선 확인했지만", result)
        self.assertIn("[관련 법령 참고]", result)
        self.assertIn("개인정보 보호법 시행령 제24조", result)
        self.assertIn("[결론]", result)

def _patched_test_compose_privacy_processing_question_adds_practical_frame(self):
    result = self.composer.compose(
        AnswerCompositionInput(
            user_query="아파트 관리업체가 입주민 정보를 수집하거나 제3자 제공해도 되는지 판단해줘",
            prompt_payload=PROMPT_PAYLOAD,
            law_enrichment={
                "primary_law": {"law_name": "공동주택관리법"},
                "version": {"version_fields": {}},
                "article": {
                    "found": True,
                    "article_no": "제7조",
                    "article_text": "제7조(관리방법의 결정 및 변경) 입주자등은 공동주택의 관리방법을 결정할 수 있다.",
                },
                "related_articles": [
                    {
                        "found": True,
                        "article_no": "제15조",
                        "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 수집할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제17조",
                        "article_text": "제17조(개인정보의 제공) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 제공할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제18조",
                        "article_text": "제18조(개인정보의 목적 외 이용ㆍ제공 제한) 개인정보처리자는 목적 외로 이용하거나 제공하여서는 아니 된다.",
                    },
                ],
            },
            risk_level="HIGH",
            fallback_answer="",
        )
    )

    self.assertIn("[실무 판단 구조]", result)
    self.assertIn("누가 정보를 처리하는지", result)
    self.assertIn("수집, 이용, 제공, 위탁, 목적 외 이용·제공", result)
    self.assertIn("제3자 제공 요건", result)
    self.assertIn("목적 외 이용·제공", result)


AnswerComposerTests.test_compose_privacy_processing_question_adds_practical_frame = _patched_test_compose_privacy_processing_question_adds_practical_frame


def _patched_test_compose_privacy_processing_question_adds_practical_frame_v2(self):
    result = self.composer.compose(
        AnswerCompositionInput(
            user_query="아파트 관리업체가 입주민 정보를 수집하거나 제공받아도 되는지 판단해줘",
            prompt_payload=PROMPT_PAYLOAD,
            law_enrichment={
                "primary_law": {"law_name": "공동주택관리법"},
                "version": {"version_fields": {}},
                "article": {
                    "found": True,
                    "article_no": "제7조",
                    "article_text": "제7조(관리방법의 결정 및 변경) 입주자등은 공동주택의 관리방법을 결정할 수 있다.",
                },
                "related_articles": [
                    {
                        "found": True,
                        "article_no": "제15조",
                        "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 수집할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제17조",
                        "article_text": "제17조(개인정보의 제공) 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우 개인정보를 제공할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제18조",
                        "article_text": "제18조(개인정보의 목적 외 이용ㆍ제공 제한) 개인정보처리자는 목적 외로 이용하거나 제공하여서는 아니 된다.",
                    },
                ],
            },
            risk_level="HIGH",
            fallback_answer="",
        )
    )

    self.assertIn("[실무 판단 구조]", result)
    self.assertIn("누가 정보를 처리하는지", result)
    self.assertIn("수집, 제공, 위탁", result)
    self.assertIn("제3자 제공 요건", result)
    self.assertIn("목적 외 이용·제공", result)


AnswerComposerTests.test_compose_privacy_processing_question_adds_practical_frame = _patched_test_compose_privacy_processing_question_adds_practical_frame_v2


def _patched_test_build_plan_exposes_structured_privacy_analysis(self):
    plan = self.composer.build_plan(
        AnswerCompositionInput(
            user_query="아파트 관리업체가 입주민 정보를 수집하거나 제공받아도 되는지 판단해줘",
            prompt_payload=PROMPT_PAYLOAD,
            law_enrichment={
                "primary_law": {"law_name": "공동주택관리법"},
                "version": {"version_fields": {}},
                "article": {
                    "found": True,
                    "article_no": "제7조",
                    "article_text": "제7조(관리방법의 결정 및 변경) 입주자등은 공동주택의 관리방법을 결정할 수 있다.",
                },
                "question_law_scope": {
                    "target_law_family": "공동주택관리법",
                    "matched_laws": [{"law_name": "공동주택관리법"}],
                    "direct_basis_found": False,
                },
                "related_articles": [
                    {
                        "found": True,
                        "article_no": "제15조",
                        "article_text": "제15조(개인정보의 수집·이용) 개인정보처리자는 법적 근거가 있는 경우 개인정보를 수집·이용할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제26조",
                        "article_text": "제26조(업무위탁에 따른 개인정보의 처리 제한) 개인정보 처리업무를 위탁하는 경우 수탁자를 관리·감독하여야 한다.",
                    },
                ],
            },
            risk_level="HIGH",
            fallback_answer="",
            clarification={
                "clarification_needed": True,
                "clarification_questions": [
                    "그 업체가 관리주체인지, 위탁을 받은 외부 업체인지 알 수 있나요?"
                ],
            },
        )
    )

    self.assertIsNotNone(plan.privacy_analysis)
    self.assertEqual(plan.privacy_analysis["data_scope"], "general")
    self.assertIn("수집", plan.privacy_analysis["processing_actions"])
    self.assertIn("제공", plan.privacy_analysis["processing_actions"])
    self.assertTrue(
        any(
            checkpoint.startswith("개인정보 보호법 제15조")
            for checkpoint in plan.privacy_analysis["legal_basis_checkpoints"]
        )
    )
    payload = self.composer.plan_as_dict(plan)
    self.assertEqual(payload["question_law_scope"]["status"], "direct_basis_not_found")
    self.assertTrue(payload["privacy_analysis"]["clarification_needed"])


AnswerComposerTests.test_build_plan_exposes_structured_privacy_analysis = _patched_test_build_plan_exposes_structured_privacy_analysis


def _patched_test_privacy_analysis_ignores_related_article_false_positive_signals(self):
    plan = self.composer.build_plan(
        AnswerCompositionInput(
            user_query="관리주체가 입주민 연락처를 수집할 수 있나",
            prompt_payload=PROMPT_PAYLOAD,
            law_enrichment={
                "primary_law": {"law_name": "공동주택관리법"},
                "version": {"version_fields": {}},
                "article": {
                    "found": True,
                    "article_no": "제7조",
                    "article_text": "제7조(관리방법의 결정 및 변경) 입주자등은 공동주택의 관리방법을 결정할 수 있다.",
                },
                "related_articles": [
                    {
                        "found": True,
                        "article_no": "제17조",
                        "article_text": "제17조(개인정보의 제공) 개인정보처리자는 일정한 경우 개인정보를 제공할 수 있다.",
                    },
                    {
                        "found": True,
                        "article_no": "제24조의2",
                        "article_text": "제24조의2(주민등록번호 처리의 제한) 주민등록번호는 법령상 근거가 있는 경우에만 처리할 수 있다.",
                    },
                ],
            },
            risk_level="HIGH",
            fallback_answer="",
            clarification=None,
        )
    )

    self.assertIsNotNone(plan.privacy_analysis)
    self.assertEqual(plan.privacy_analysis["data_scope"], "general")
    self.assertIn("수집", plan.privacy_analysis["processing_actions"])
    self.assertNotIn("제공", plan.privacy_analysis["processing_actions"])
    self.assertFalse(
        any("제24조의2" in checkpoint for checkpoint in plan.privacy_analysis["legal_basis_checkpoints"])
    )


AnswerComposerTests.test_privacy_analysis_ignores_related_article_false_positive_signals = _patched_test_privacy_analysis_ignores_related_article_false_positive_signals


if __name__ == "__main__":
    unittest.main()
