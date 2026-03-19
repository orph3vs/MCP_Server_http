import unittest

from src.answer_composer import AnswerComposer, AnswerCompositionInput


PROMPT_PAYLOAD = {
    "system": "근거-주장 매핑을 포함한 grounded legal answer를 작성하라.",
    "user": "질문에 답하라.",
}


class PublicLinkFormatTests(unittest.TestCase):
    def test_evidence_block_shows_article_links_and_law_link_separately(self):
        composer = AnswerComposer()

        result = composer.compose(
            AnswerCompositionInput(
                user_query="학교밖청소년지원센터는 주민등록번호 수집 가능 함?",
                prompt_payload=PROMPT_PAYLOAD,
                law_enrichment={
                    "primary_law": {
                        "law_name": "청소년복지 지원법 시행령",
                        "law_link": "https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)",
                    },
                    "version": {"version_fields": {"시행일자": "20251118"}},
                    "article": {
                        "found": True,
                        "law_id": "009908",
                        "article_no": "제18조",
                        "article_link": "https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조",
                        "article_text": "제18조(민감정보 및 고유식별정보의 처리) 테스트 조문",
                        "matched_clauses": [
                            {
                                "article_no": "제18조 제3호의2",
                                "article_text": "통합정보시스템 구축·운영",
                                "article_link": "https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조제3호의2",
                            },
                            {
                                "article_no": "제18조 제6호",
                                "article_text": "가정 밖 청소년 보호·지원",
                                "article_link": "https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조제6호",
                            },
                        ],
                    },
                    "related_articles": [],
                    "review_summary": {},
                    "used_search_query": "학교밖청소년지원센터 주민등록번호",
                },
                risk_level="LOW",
                fallback_answer="",
            )
        )

        self.assertIn("[근거 조문]", result)
        self.assertIn("- 제18조: https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조", result)
        self.assertIn("- 제18조 제3호의2: https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조제3호의2", result)
        self.assertIn("- 제18조 제6호: https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)/제18조제6호", result)
        self.assertIn("[근거 법령]", result)
        self.assertIn("- 청소년복지 지원법 시행령: https://www.law.go.kr/법령/청소년복지지원법시행령/(20251118,35780,20251118)", result)


if __name__ == "__main__":
    unittest.main()
