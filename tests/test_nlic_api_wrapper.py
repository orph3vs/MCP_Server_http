import json
import unittest
from pathlib import Path
from urllib.error import HTTPError

from src.nlic_api_wrapper import NlicApiWrapper


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nlic"


class FakeNlicApiWrapper(NlicApiWrapper):
    def __init__(self):
        super().__init__(oc="test_oc", cache_ttl_seconds=300)
        self.calls = []

    def _request(self, params, endpoint_url=None):
        self.calls.append({"params": params, "endpoint_url": endpoint_url})
        target = params.get("target")

        if target == "law" and params.get("query"):
            return {"law": [{"id": "L1", "name": params["query"]}]}

        if target == "lsRlt":
            if params.get("ID") == "L1":
                return {
                    "lsRltSearch": {
                        "법령": {
                            "관련법령": [
                                {
                                    "관련법령ID": "B1",
                                    "관련법령명": "기본법",
                                    "관련법령본문조회": "https://www.law.go.kr/법령/기본법",
                                }
                            ]
                        }
                    }
                }
            return {"lsRltSearch": {"법령": {"관련법령": []}}}

        if target == "prec" and params.get("query"):
            return {
                "PrecSearch": {
                    "prec": [
                        {"판례일련번호": "P1", "사건명": "테스트 판례", "사건번호": "2025다12345"},
                    ]
                }
            }

        if endpoint_url == self.service_url and target == "prec" and params.get("ID"):
            return {"판례": {"판례일련번호": params["ID"], "사건명": "테스트 판례"}}

        if target == "law" and params.get("ID") and not params.get("JO"):
            return {
                "LawSearch": {
                    "law": {
                        "법령일련번호": "270351",
                        "시행일자": "2025-01-01",
                        "공포일자": "2024-12-01",
                        "제개정구분명": "일부개정",
                    }
                }
            }

        if endpoint_url == self.service_url and params.get("MST") and params.get("JO") and target in ("law", "lawjosub"):
            if params.get("JO") == "000100":
                return {
                    "조문": {
                        "조문단위": [
                            {
                                "조문번호": "제1조",
                                "조문내용": "제1조(목적) 이 법은 개인정보의 처리 및 보호에 관한 사항을 정한다.",
                            }
                        ]
                    }
                }
            return {"raw": "   "}

        if params.get("ID") and params.get("JO"):
            return {"법령": {"기본정보": {"소관부처": {"content": "개인정보보호위원회"}}}}

        if target == "history":
            return {"versions": [{"id": params.get("ID"), "ver": "2025-01-01"}]}

        return {}


class BlankHistoryFakeNlicApiWrapper(FakeNlicApiWrapper):
    def _request(self, params, endpoint_url=None):
        if params.get("target") == "history":
            return {"raw": "   "}
        return super()._request(params, endpoint_url=endpoint_url)


class EmptyHistoryFakeNlicApiWrapper(FakeNlicApiWrapper):
    def _request(self, params, endpoint_url=None):
        if params.get("target") == "history":
            return {"versions": []}
        return super()._request(params, endpoint_url=endpoint_url)


class LiveFixtureNlicApiWrapper(NlicApiWrapper):
    def __init__(self):
        super().__init__(oc="test_oc", cache_ttl_seconds=300)

    @staticmethod
    def _load_fixture(name: str):
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    def _request(self, params, endpoint_url=None):
        target = params.get("target")

        if target == "law" and params.get("query") == "개인정보보호법":
            return self._load_fixture("search_law_privacy_act.json")

        if target == "history" and params.get("ID") == "011357":
            return {"raw": "   "}

        if target == "law" and params.get("ID") == "011357" and not params.get("JO"):
            return self._load_fixture("get_version_011357_law.json")

        if (
            endpoint_url == self.service_url
            and target == "law"
            and params.get("ID") == "011357"
            and params.get("JO") in ("제1조", "000100")
        ):
            return self._load_fixture("get_article_011357_제1조.json")

        if (
            endpoint_url == self.service_url
            and target == "lawjosub"
            and params.get("ID") == "011357"
            and params.get("JO") == "제1조"
        ):
            return {"raw": "   "}

        return {}


class RetryOnHttp404FakeNlicApiWrapper(FakeNlicApiWrapper):
    def _request(self, params, endpoint_url=None):
        if (
            endpoint_url == self.service_url
            and params.get("target") == "law"
            and params.get("ID") == "L1"
            and params.get("JO") == "제1조"
        ):
            raise HTTPError(
                url="https://example.test",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            )
        return super()._request(params, endpoint_url=endpoint_url)


class NlicApiWrapperTests(unittest.TestCase):
    def test_search_law_and_cache(self):
        api = FakeNlicApiWrapper()
        a = api.search_law("개인정보보호법")
        b = api.search_law("개인정보보호법")

        self.assertEqual(a, b)
        self.assertEqual(len(api.calls), 1)

    def test_search_precedent(self):
        api = FakeNlicApiWrapper()
        result = api.search_precedent("개인정보 보호법 제15조 위법")

        self.assertEqual(result["PrecSearch"]["prec"][0]["판례일련번호"], "P1")

    def test_get_precedent(self):
        api = FakeNlicApiWrapper()
        result = api.get_precedent("P1")

        self.assertEqual(result["판례"]["판례일련번호"], "P1")

    def test_get_article_and_validate_article(self):
        api = FakeNlicApiWrapper()
        article = api.get_article("L1", " 제1조 ")
        validated = api.validate_article(" L1 ", " 제1조 ")

        self.assertEqual(article["law_id"], "L1")
        self.assertEqual(article["article_no"], "제1조")
        self.assertEqual(article["article_candidates"], ["제1조", "000100"])
        self.assertTrue(article["found"])
        self.assertIn("제1조(목적)", article["article_text"])
        self.assertEqual(article["matched_via"], "service:law:mst")
        self.assertGreater(len(article["attempted_queries"]), 0)
        self.assertTrue(validated["is_valid"])
        self.assertEqual(validated["law_id"], "L1")
        self.assertEqual(validated["article_no"], "제1조")

    def test_article_no_candidates_include_official_jo_code(self):
        self.assertEqual(
            NlicApiWrapper._article_no_candidates("제10조의2"),
            ("제10조의2", "001002", "001000"),
        )

    def test_get_article_does_not_pick_unrelated_content_field(self):
        api = FakeNlicApiWrapper()
        article = api.get_article("L1", "제999조")
        self.assertFalse(article["found"])
        self.assertIsNone(article["article_text"])

    def test_get_article_retries_after_http_404(self):
        api = RetryOnHttp404FakeNlicApiWrapper()
        article = api.get_article("L1", "제1조")

        self.assertTrue(article["found"])
        self.assertEqual(article["matched_via"], "service:law:mst")
        self.assertTrue(
            any(query.get("error") == "HTTP 404" for query in article["attempted_queries"])
        )

    def test_get_version(self):
        api = FakeNlicApiWrapper()
        versions = api.get_version("L1")
        self.assertEqual(versions["source_target"], "history")
        self.assertEqual(versions["data"]["versions"][0]["id"], "L1")

    def test_get_version_falls_back_when_history_is_blank(self):
        api = BlankHistoryFakeNlicApiWrapper()
        versions = api.get_version("L1")

        self.assertEqual(versions["source_target"], "law_fallback")
        self.assertEqual(versions["version_fields"]["시행일자"], "2025-01-01")
        self.assertEqual(versions["version_fields"]["공포일자"], "2024-12-01")
        self.assertEqual(versions["version_fields"]["제개정구분명"], "일부개정")

    def test_get_version_falls_back_when_history_versions_is_empty(self):
        api = EmptyHistoryFakeNlicApiWrapper()
        versions = api.get_version("L1")

        self.assertEqual(versions["source_target"], "law_fallback")
        self.assertEqual(versions["version_fields"]["시행일자"], "2025-01-01")

    def test_search_law_with_live_fixture_payload(self):
        api = LiveFixtureNlicApiWrapper()
        result = api.search_law("개인정보보호법")

        self.assertEqual(result["LawSearch"]["resultCode"], "00")
        self.assertEqual(result["LawSearch"]["law"][0]["법령ID"], "011357")
        self.assertEqual(result["LawSearch"]["law"][1]["법령명한글"], "개인정보 보호법 시행령")

    def test_get_article_with_live_fixture_payload(self):
        api = LiveFixtureNlicApiWrapper()
        article = api.get_article("011357", "제1조")

        self.assertTrue(article["found"])
        self.assertEqual(article["matched_via"], "service:law")
        self.assertEqual(article["article_candidates"], ["제1조", "000100"])
        self.assertIn("개인정보의 처리 및 보호", article["article_text"])

    def test_get_version_with_live_fixture_payload(self):
        api = LiveFixtureNlicApiWrapper()
        versions = api.get_version("011357")

        self.assertEqual(versions["source_target"], "law_fallback")
        self.assertEqual(versions["version_fields"]["시행일자"], "20251002")
        self.assertEqual(versions["version_fields"]["공포일자"], "20250401")
        self.assertEqual(versions["version_fields"]["제개정구분명"], "일부개정")


    def test_search_related_laws(self):
        api = FakeNlicApiWrapper()
        result = api.search_related_laws(law_id="L1")

        self.assertEqual(result["lsRltSearch"]["법령"]["관련법령"][0]["관련법령ID"], "B1")

if __name__ == "__main__":
    unittest.main()
