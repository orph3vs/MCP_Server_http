"""End-to-end request pipeline."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from src.answer_composer import AnswerComposer, AnswerCompositionInput
from src.confidence_scoring import ConfidenceInput, ConfidenceScoringEngine
from src.cost_logger import CostLogEntry, CostLogger
from src.law_hint_suggestions import LawHintSuggestionStore
from src.multi_agent_review import MultiAgentReviewPipeline
from src.nlic_api_wrapper import NlicApiWrapper
from src.prompt_loader import build_request_prompt, extract_prompt_policy
from src.risk_classifier import RiskClassifier


@dataclass(frozen=True)
class PipelineRequest:
    user_query: str
    context: Optional[str] = None
    request_id: Optional[str] = None


@dataclass(frozen=True)
class PipelineResponse:
    request_id: str
    risk_level: str
    mode: str
    answer: str
    citations: Dict[str, Any]
    score: float
    latency_ms: float
    error: Optional[Dict[str, str]] = None


class PipelineStageError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass(frozen=True)
class LawSearchAnalysis:
    question_intent: str
    issue_terms: List[str]
    related_law_queries: List[str]
    search_queries: List[str]
    proposed_keywords: List[str]


class RequestPipeline:
    """Coordinates all modules into one deterministic processing flow."""

    _SENSITIVE_IDENTIFIER_TITLE_KEYWORDS = (
        "고유식별정보의 처리",
        "민감정보 및 고유식별정보의 처리",
        "민감정보의 처리",
        "주민등록번호의 처리",
    )

    _RELATED_LAW_HINTS = {
        "개인정보 보호법": ("개인정보", "개인정보처리", "정보주체"),
        "개인정보의 안전성 확보조치 기준": ("안전성 확보조치", "안전조치", "접근권한", "접속기록", "암호화", "내부관리계획"),
        "공동주택관리법": ("공동주택", "아파트", "입주자", "관리사무소", "입주자대표회의"),
        "주차장법": ("주차장", "주차", "주차관제", "차량번호", "주차관리"),
        "위치정보의 보호 및 이용 등에 관한 법률": ("위치정보", "위치기반", "gps", "지오펜싱"),
        "정보통신망 이용촉진 및 정보보호 등에 관한 법률": ("정보통신망", "온라인서비스", "통신망", "게시판", "서비스제공자"),
        "신용정보의 이용 및 보호에 관한 법률": ("신용정보", "cb", "kcb", "nice", "금융거래정보", "개인신용정보"),
        "클라우드컴퓨팅 발전 및 이용자 보호에 관한 법률": ("클라우드", "saas", "paas", "iaas", "클라우드서비스", "클라우드컴퓨팅"),
        "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법": ("인공지능", "ai", "생성형 ai", "알고리즘", "모델", "신뢰 기반"),
        "통신비밀보호법": ("통신비밀", "감청", "통화내역", "통신사실확인자료", "압수수색"),
        "전자금융거래법": ("전자금융", "전자지급", "간편결제", "핀테크", "pg", "결제대행"),
        "전자금융감독규정": ("전자금융감독규정", "금융보안", "이상거래탐지", "접근통제", "망분리"),
        "전자상거래 등에서의 소비자보호에 관한 법률": ("전자상거래", "이커머스", "통신판매", "청약철회", "플랫폼", "오투오"),
        "의료법": ("의료", "병원", "의원", "진료기록", "환자", "의료기관"),
        "생명윤리 및 안전에 관한 법률": ("생명윤리", "유전자", "인체유래물", "irb", "연구대상자"),
        "약사법": ("약사법", "약국", "의약품", "처방전", "복약", "약사"),
        "소득세법": ("소득세", "원천징수", "지급명세서", "연말정산", "종합소득"),
        "근로기준법": ("근로", "임금", "연차", "해고", "근로시간", "직장"),
        "고용보험법": ("고용보험", "실업급여", "피보험자", "고용안정", "육아휴직급여"),
        "채용절차의 공정화에 관한 법률": ("채용", "입사지원서", "채용절차", "면접", "구직자"),
        "초ㆍ중등교육법": ("초중등교육", "학교생활기록부", "학생", "교사", "학부모", "중학교", "고등학교"),
        "고등교육법": ("고등교육", "대학교", "대학", "전문대", "휴학", "학칙"),
        "평생교육법": ("평생교육", "평생학습", "평생교육기관", "학습자"),
        "장애인 등에 대한 특수교육법": ("특수교육", "장애학생", "개별화교육", "통합교육"),
        "교육공무원법": ("교육공무원", "교원", "교사징계", "교원인사"),
        "대학 등록금에 관한 규칙": ("등록금", "등록금심의", "수업료", "입학금"),
        "학원의 설립ㆍ운영 및 과외교습에 관한 법률": ("학원", "과외", "교습비", "강사", "수강생"),
        "청소년 기본법": ("청소년", "청소년정책", "청소년활동"),
        "청소년 보호법": ("청소년 보호", "유해매체", "유해환경", "연령확인"),
        "청소년복지 지원법": ("청소년복지", "위기청소년", "청소년지원"),
        "아동ㆍ청소년의 성보호에 관한 법률": ("아동청소년 성보호", "성착취", "그루밍", "디지털성범죄"),
        "학교 밖 청소년 지원에 관한 법률": ("학교 밖 청소년", "학교밖청소년", "꿈드림"),
        "노인복지법": ("노인복지", "요양", "경로당", "노인학대", "노인시설"),
        "노인 일자리 및 사회활동 지원에 관한 법률": ("노인일자리", "사회활동 지원", "시니어일자리"),
        "공공기록물 관리에 관한 법률": ("공공기록물", "기록물", "문서보존", "행정기록", "아카이브"),
    }

    _RELATED_LAW_HINTS["도서관법"] = (
        "도서관",
        "작은도서관",
        "사서",
        "열람",
        "도서관 프로그램",
        "독서문화",
    )

    _QUESTION_INTENT_KEYWORDS = {
        "difference": ("차이", "구분", "비교", "다른 점"),
        "requirements": ("요건", "조건", "기준", "해당", "충족"),
        "procedure": ("절차", "방법", "순서", "어떻게", "진행"),
        "illegality": ("위법", "불법", "허용", "가능한지", "문제되는지", "판단"),
        "applicability": ("적용", "대상", "포함", "제외"),
    }
    _PRECEDENT_REQUEST_KEYWORDS = (
        "판례",
        "대법원",
        "법원은",
        "유사 사례",
        "관련 사례",
        "사례도",
        "판결",
    )
    _PRECEDENT_SUFFIX = "\ud310\ub840"

    def __init__(
        self,
        risk_classifier: Optional[RiskClassifier] = None,
        law_api: Optional[NlicApiWrapper] = None,
        agent_engine: Optional[MultiAgentReviewPipeline] = None,
        scorer: Optional[ConfidenceScoringEngine] = None,
        logger: Optional[CostLogger] = None,
        suggestion_store: Optional[LawHintSuggestionStore] = None,
    ) -> None:
        self.risk_classifier = risk_classifier or RiskClassifier()
        self.law_api = law_api or NlicApiWrapper()
        self.agent_engine = agent_engine or MultiAgentReviewPipeline()
        self.answer_composer = AnswerComposer()
        self.scorer = scorer or ConfidenceScoringEngine()
        self.logger = logger or CostLogger()
        self.suggestion_store = suggestion_store or LawHintSuggestionStore()

    def _validate(self, answer: str, citations: Dict[str, Any]) -> None:
        if not answer.strip():
            raise PipelineStageError("Validator", "empty_answer")
        if not citations:
            raise PipelineStageError("Validator", "missing_citations")
        prompt_policy = citations.get("prompt_policy") or {}
        if prompt_policy.get("require_evidence_mapping"):
            law_context = citations.get("law_context") or {}
            has_primary_law = bool((law_context.get("primary_law") or {}).get("law_name"))
            has_article = bool(law_context.get("article"))
            if not (has_primary_law or has_article):
                raise PipelineStageError("Validator", "missing_grounded_context")

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.0000015) + (tokens_out * 0.000002), 6)

    @staticmethod
    def _increment_metric(metrics: Dict[str, int], key: str, amount: int = 1) -> None:
        metrics[key] = metrics.get(key, 0) + amount

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 140) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3].rstrip() + "..."

    @classmethod
    def _question_summary(cls, user_query: str, max_chars: int = 60) -> str:
        return cls._truncate_text(user_query, max_chars=max_chars)

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _extract_law_items(law_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(law_data, dict):
            return []

        items = law_data.get("law")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        if isinstance(items, dict):
            return [items]

        nested = law_data.get("LawSearch")
        if isinstance(nested, dict):
            nested_items = nested.get("law")
            if isinstance(nested_items, list):
                return [item for item in nested_items if isinstance(item, dict)]
            if isinstance(nested_items, dict):
                return [nested_items]

        return []

    @staticmethod
    def _extract_related_law_items(related_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(related_data, dict):
            return []

        nested = related_data.get("lsRltSearch")
        if isinstance(nested, dict):
            law = nested.get("법령")
            if isinstance(law, dict):
                items = law.get("관련법령")
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
                if isinstance(items, dict):
                    return [items]
        return []

    @staticmethod
    def _extract_precedent_items(precedent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(precedent_data, dict):
            return []

        items = precedent_data.get("prec")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        if isinstance(items, dict):
            return [items]

        nested = precedent_data.get("PrecSearch")
        if isinstance(nested, dict):
            nested_items = nested.get("prec")
            if isinstance(nested_items, list):
                return [item for item in nested_items if isinstance(item, dict)]
            if isinstance(nested_items, dict):
                return [nested_items]

        return []

    @staticmethod
    def _absolute_link(raw_link: Optional[str]) -> Optional[str]:
        if not raw_link:
            return None
        raw_link = str(raw_link).strip()
        if not raw_link:
            return None
        if raw_link.startswith("http://") or raw_link.startswith("https://"):
            return RequestPipeline._sanitize_link(raw_link)
        if raw_link.startswith("/"):
            return RequestPipeline._sanitize_link(f"https://www.law.go.kr{raw_link}")
        return None

    @staticmethod
    def _sanitize_link(raw_link: str) -> str:
        parsed = urlsplit(raw_link)
        sanitized_query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.upper() != "OC"
            ]
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, sanitized_query, parsed.fragment))

    @staticmethod
    def _public_law_link(
        law_name: Optional[str],
        effective_date: Optional[str],
        promulgation_no: Optional[str],
        article_no: Optional[str] = None,
    ) -> Optional[str]:
        normalized_law_name = re.sub(r"\s+", "", RequestPipeline._clean_text(str(law_name or "")))
        if not normalized_law_name:
            return None

        path_parts = [quote(normalized_law_name, safe="")]
        normalized_article_no = re.sub(r"\s+", "", RequestPipeline._clean_text(str(article_no or "")))
        if normalized_article_no:
            path_parts.append(quote(normalized_article_no, safe=""))

        return f"https://www.law.go.kr/법령/{'/'.join(path_parts)}"

    def _service_link(self, law_id: Optional[str], article_no: Optional[str] = None) -> Optional[str]:
        normalized_law_id = self._clean_text(str(law_id or ""))
        if not normalized_law_id:
            return None

        service_url = getattr(self.law_api, "service_url", NlicApiWrapper.DEFAULT_SERVICE_URL)
        params: Dict[str, str] = {"target": "law", "ID": normalized_law_id, "type": "HTML"}
        if article_no:
            jo_value = self._article_link_jo(article_no)
            if jo_value:
                params["JO"] = jo_value
        return self._sanitize_link(f"{service_url}?{urlencode(params)}")

    @staticmethod
    def _article_link_jo(article_no: str) -> Optional[str]:
        article_candidates = NlicApiWrapper._article_no_candidates(article_no)
        for candidate in article_candidates:
            if str(candidate).isdigit():
                return str(candidate)

        normalized = RequestPipeline._clean_text(str(article_no))
        match = re.search(r"(\d+)\s*조(?:\s*의\s*(\d+))?", normalized)
        if not match:
            return None

        main_no = int(match.group(1))
        sub_no = match.group(2)
        if sub_no is not None:
            return f"{main_no:04d}{int(sub_no):02d}"
        return f"{main_no:04d}00"

    @staticmethod
    def _item_public_law_link(item: Dict[str, Any], article_no: Optional[str] = None) -> Optional[str]:
        if not isinstance(item, dict):
            return None
        return RequestPipeline._public_law_link(
            item.get("법령명한글") or item.get("법령명한자") or item.get("law_name"),
            item.get("시행일자") or item.get("effective_date"),
            item.get("공포번호") or item.get("promulgation_no"),
            article_no=article_no,
        )

    @staticmethod
    def _pick_primary_law(law_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        items = RequestPipeline._extract_law_items(law_data)
        if not items:
            return None

        primary = items[0]
        law_id = primary.get("법령ID") or primary.get("법령일련번호") or primary.get("id")
        law_name = primary.get("법령명한글") or primary.get("법령명_한글") or primary.get("name")
        return {
            "law_id": str(law_id).strip() if law_id is not None else None,
            "law_name": str(law_name).strip() if law_name is not None else None,
            "raw": primary,
        }

    @classmethod
    def _question_intent(cls, user_query: str) -> str:
        normalized = cls._clean_text(user_query)
        for intent in ("difference", "illegality", "requirements", "procedure", "applicability"):
            if any(keyword in normalized for keyword in cls._QUESTION_INTENT_KEYWORDS[intent]):
                return intent
        return "explain"

    @classmethod
    def _wants_precedents(cls, user_query: str) -> bool:
        normalized = cls._clean_text(user_query)
        return any(keyword in normalized for keyword in cls._PRECEDENT_REQUEST_KEYWORDS)

    @classmethod
    def _extract_issue_query_terms(cls, user_query: str) -> List[str]:
        normalized = cls._clean_text(user_query)
        issue_hints = {
            "개인정보": ("개인정보", "성명", "이름", "연락처", "휴대폰", "핸드폰", "전화번호"),
            "출석부": ("출석부", "출석 명단", "참석자 명단", "명단", "참가자 명단"),
            "마스킹": ("마스킹", "가림", "익명화", "비식별", "수정테이프", "홍**"),
            "증빙서류": ("증빙서류", "정산서류", "정산 증빙", "첨부서류", "사본"),
            "보관": ("보관", "보유", "파기", "제출"),
            "동의고지": ("동의", "고지", "안내", "제공"),
        }
        found_terms: List[str] = []
        for canonical, hints in issue_hints.items():
            if any(hint in normalized for hint in hints):
                found_terms.append(canonical)
        return found_terms

    @classmethod
    def _is_sensitive_identifier_question(cls, user_query: str) -> bool:
        normalized = cls._clean_text(user_query)
        keywords = ("주민등록번호", "고유식별정보", "민감정보")
        return any(keyword in normalized for keyword in keywords)

    @classmethod
    def _sensitive_identifier_keywords(cls, user_query: str) -> List[str]:
        normalized = cls._clean_text(user_query)
        keywords = [
            "주민등록번호",
            "고유식별정보",
            "민감정보",
            "처리할 수",
            "불가피",
            *cls._SENSITIVE_IDENTIFIER_TITLE_KEYWORDS,
        ]
        if "동의" in normalized:
            keywords.append("동의")
        if "학교밖청소년" in normalized or "학교 밖 청소년" in normalized:
            keywords.extend(
                [
                    "학교밖청소년지원센터",
                    "학교 밖 청소년",
                    "가정 밖 청소년",
                    "청소년상담복지센터",
                    "통합정보시스템",
                ]
            )
        if "통합정보시스템" in normalized or "시스템" in normalized:
            keywords.append("통합정보시스템")

        deduped: List[str] = []
        seen = set()
        for keyword in keywords:
            if keyword not in seen:
                seen.add(keyword)
                deduped.append(keyword)
        return deduped

    @classmethod
    def _law_family_name(cls, law_name: str) -> str:
        clean_name = cls._clean_text(law_name)
        return clean_name.replace(" 시행령", "").replace(" 시행규칙", "").strip()

    @classmethod
    def _extract_precedent_issue_terms(cls, user_query: str) -> List[str]:
        normalized = cls._clean_text(user_query)
        precedent_hints = {
            "청소년 도박": ("청소년 도박", "청소년도박"),
            "온라인 도박": ("온라인 도박", "인터넷 도박", "사이버 도박"),
            "형사처벌": ("형사처벌", "처벌", "벌칙"),
            "플랫폼 책임": ("플랫폼 책임", "플랫폼", "중개 플랫폼"),
            "업주 책임": ("업주 책임", "업주", "운영자 책임"),
            "방조": ("방조",),
            "도박 개설": ("도박장 개설", "도박 개설", "개설", "개장"),
            "개인정보": ("개인정보", "이름", "연락처", "주소"),
            "동의": ("동의", "고지", "안내"),
            "보관기간": ("보관기간", "보관", "파기"),
            "제3자 제공": ("제3자 제공", "제삼자 제공", "제공"),
        }
        found_terms: List[str] = []
        for canonical, hints in precedent_hints.items():
            if any(hint in normalized for hint in hints):
                found_terms.append(canonical)
        return found_terms[:5]

    @classmethod
    def _extract_hint_candidate_keywords(cls, user_query: str) -> List[str]:
        normalized = cls._clean_text(user_query)
        stopwords = {
            "설명",
            "알려줘",
            "알려주세요",
            "문의",
            "경우",
            "관련",
            "기준",
            "질문",
            "프로그램",
            "진행",
            "대상",
            "처리",
            "제출",
            "작성",
        }
        candidates = re.findall(r"[가-힣A-Za-z]{2,12}", normalized)
        filtered = [
            candidate
            for candidate in candidates
            if candidate not in stopwords and not candidate.endswith("합니다")
        ]
        return filtered[:8]

    def _resolved_related_law_queries(self, user_query: str) -> List[str]:
        queries = self._related_law_queries(user_query)
        normalized = self._clean_text(user_query).lower()
        for law_name, hints in self.suggestion_store.approved_overrides().items():
            if any(hint.lower() in normalized for hint in hints):
                queries.append(law_name)
        deduped: List[str] = []
        seen = set()
        for query in queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    def _analyze_law_search(self, user_query: str) -> LawSearchAnalysis:
        issue_terms = self._extract_issue_query_terms(user_query)
        related_law_queries = self._resolved_related_law_queries(user_query)
        search_queries = self._law_search_queries(
            user_query,
            related_law_queries=related_law_queries,
        )
        proposed_keywords = issue_terms + self._extract_hint_candidate_keywords(user_query)
        return LawSearchAnalysis(
            question_intent=self._question_intent(user_query),
            issue_terms=issue_terms,
            related_law_queries=related_law_queries,
            search_queries=search_queries,
            proposed_keywords=proposed_keywords,
        )

    def _record_law_hint_suggestion(
        self,
        *,
        request_id: str,
        req: PipelineRequest,
        analysis: LawSearchAnalysis,
        question_summary: str,
    ) -> None:
        if analysis.related_law_queries or analysis.issue_terms or analysis.proposed_keywords:
            self.suggestion_store.create_or_update_suggestion(
                request_id=request_id,
                question_summary=question_summary,
                user_query=req.user_query,
                question_intent=analysis.question_intent,
                related_law_queries=analysis.related_law_queries,
                issue_terms=analysis.issue_terms,
                search_queries=analysis.search_queries,
                proposed_keywords=analysis.proposed_keywords,
            )

    @staticmethod
    def _extract_article_numbers(question: str) -> List[str]:
        matches = re.findall(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", question)
        results: List[str] = []
        seen = set()
        for main_no, sub_no in matches:
            article_no = f"제{int(main_no)}조"
            if sub_no:
                article_no = f"{article_no}의{int(sub_no)}"
            if article_no not in seen:
                seen.add(article_no)
                results.append(article_no)
        return results

    @staticmethod
    def _merge_context(base_context: Optional[str], lines: List[str]) -> Optional[str]:
        extra = "\n".join(line for line in lines if line)
        if base_context and extra:
            return f"{base_context.strip()}\n\n[LAW_CONTEXT]\n{extra}"
        if extra:
            return f"[LAW_CONTEXT]\n{extra}"
        return base_context

    @classmethod
    def _law_search_queries(
        cls,
        user_query: str,
        related_law_queries: Optional[List[str]] = None,
    ) -> List[str]:
        normalized = re.sub(r"\s+", " ", user_query).strip()
        if not normalized:
            return []

        queries: List[str] = []
        related_law_queries = related_law_queries or []
        issue_terms = cls._extract_issue_query_terms(normalized)
        law_name_match = re.search(
            r"([가-힣A-Za-z0-9 ]+?(?:법 시행규칙|법 시행령|법|시행규칙|시행령))",
            normalized,
        )
        if law_name_match:
            queries.append(re.sub(r"\s+", " ", law_name_match.group(1)).strip())

        if cls._is_sensitive_identifier_question(normalized):
            priority_law_queries: List[str] = []
            seed_queries: List[str] = []
            if law_name_match:
                seed_queries.append(re.sub(r"\s+", " ", law_name_match.group(1)).strip())
            seed_queries.extend(related_law_queries[:4])

            seen_priority = set()
            for seed in seed_queries:
                if not seed or seed in seen_priority:
                    continue
                seen_priority.add(seed)
                if not seed.endswith("시행령") and not seed.endswith("시행규칙"):
                    priority_law_queries.append(f"{seed} 시행령")
                    priority_law_queries.append(f"{seed} 시행규칙")
                priority_law_queries.append(seed)
            queries.extend(priority_law_queries)

        simplified = re.sub(r"제\s*\d+\s*조(?:의\s*\d+)?", "", normalized)
        simplified = re.sub(r"\b(설명|해설|알려줘|알려 주세요|알려주세요|보여줘|요약|해석|뜻|뭐야)\b", "", simplified)
        simplified = re.sub(r"\s+", " ", simplified).strip(" ,")
        if simplified:
            queries.append(simplified)

        for related_law in related_law_queries[:4]:
            queries.append(related_law)
            for issue_term in issue_terms[:4]:
                queries.append(f"{related_law} {issue_term}")

        for issue_term in issue_terms[:4]:
            queries.append(issue_term)

        queries.append(normalized)

        deduped: List[str] = []
        seen = set()
        for query in queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    @classmethod
    def _related_law_queries(cls, user_query: str) -> List[str]:
        normalized = cls._clean_text(user_query).lower()
        queries: List[str] = []
        for law_name, hints in cls._RELATED_LAW_HINTS.items():
            if any(hint.lower() in normalized for hint in hints):
                queries.append(law_name)
        return queries

    @classmethod
    def _merge_law_results(cls, datasets: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged_items: List[Dict[str, Any]] = []
        seen_ids = set()
        for dataset in datasets:
            for item in cls._extract_law_items(dataset):
                law_id = item.get("법령ID") or item.get("법령일련번호") or item.get("id")
                key = str(law_id).strip() if law_id is not None else cls._clean_text(str(item))
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                merged_items.append(item)
        return {"LawSearch": {"law": merged_items}}

    @classmethod
    def _merge_related_law_items(
        cls,
        law_data: Dict[str, Any],
        related_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged_items = list(cls._extract_law_items(law_data))
        seen_ids = set()
        for item in merged_items:
            law_id = item.get("법령ID") or item.get("법령일련번호") or item.get("id")
            if law_id is not None:
                seen_ids.add(str(law_id).strip())

        for item in related_items:
            law_id = item.get("관련법령ID") or item.get("법령ID") or item.get("id")
            law_name = item.get("관련법령명") or item.get("법령명한글") or item.get("name")
            key = str(law_id).strip() if law_id is not None else cls._clean_text(str(law_name or item))
            if not key or key in seen_ids:
                continue
            seen_ids.add(key)
            merged_items.append(
                {
                    "법령ID": str(law_id).strip() if law_id is not None else None,
                    "법령명한글": str(law_name).strip() if law_name is not None else None,
                    "법령상세링크": item.get("관련법령본문조회"),
                    "법령일련번호": str(law_id).strip() if law_id is not None else None,
                }
            )

        return {"LawSearch": {"law": merged_items}}

    @classmethod
    def _related_law_priority(cls, item: Dict[str, Any]) -> int:
        relation = cls._clean_text(str(item.get("법령간관계") or ""))
        if "개별법" in relation:
            return 0
        if "기본법" in relation:
            return 1
        if "하위법" in relation:
            return 2
        return 3

    @classmethod
    def _law_name_tokens(cls, text: str) -> List[str]:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", cls._clean_text(text))
        stopwords = {
            "법",
            "시행령",
            "시행규칙",
            "관한",
            "위한",
            "대한",
            "등",
            "청소년",
            "지원",
        }
        return [token for token in tokens if len(token) >= 2 and token not in stopwords]

    @classmethod
    def _related_law_relevance(
        cls,
        item: Dict[str, Any],
        *,
        user_query: str,
        primary_law_name: str,
    ) -> int:
        law_name = cls._clean_text(str(item.get("관련법령명") or ""))
        if not law_name:
            return 0

        relation = cls._clean_text(str(item.get("법령간관계") or ""))
        query_tokens = set(cls._law_name_tokens(user_query))
        primary_tokens = set(cls._law_name_tokens(primary_law_name))
        law_tokens = set(cls._law_name_tokens(law_name))

        overlap_score = len(query_tokens & law_tokens) * 3
        overlap_score += len(primary_tokens & law_tokens) * 2
        if "개별법" in relation:
            overlap_score += 6
        elif "기본법" in relation:
            overlap_score += 2
        elif "하위법" in relation:
            overlap_score -= 2

        normalized_query = cls._clean_text(user_query)
        if "학교밖청소년" in normalized_query or "학교 밖 청소년" in normalized_query:
            if "학교 밖 청소년" in law_name:
                overlap_score += 2
            if "복지" in law_name or "지원" in law_name:
                overlap_score += 4
            if "성보호" in law_name:
                overlap_score -= 6
            if "지원센터" in normalized_query or "센터" in normalized_query:
                if "복지" in law_name:
                    overlap_score += 8
                if "학교 밖 청소년 지원에 관한 법률" in law_name:
                    overlap_score -= 3

        if "주민등록번호" in normalized_query or "고유식별정보" in normalized_query:
            if "복지" in law_name or "지원" in law_name:
                overlap_score += 2
            if "하위법" in relation and "학교 밖 청소년" in law_name:
                overlap_score -= 6

        return overlap_score

    @classmethod
    def _expanded_related_search_queries(
        cls,
        related_items: List[Dict[str, Any]],
        *,
        user_query: str,
        primary_law_name: str,
    ) -> List[str]:
        queries: List[str] = []
        normalized_query = cls._clean_text(user_query)
        base_primary_name = primary_law_name.replace(" 시행령", "").replace(" 시행규칙", "").strip()
        ordered_items = sorted(
            [item for item in related_items if isinstance(item, dict)],
            key=lambda item: (
                -cls._related_law_relevance(item, user_query=user_query, primary_law_name=primary_law_name),
                cls._related_law_priority(item),
                cls._clean_text(str(item.get("관련법령명") or "")),
            ),
        )
        for item in ordered_items[:6]:
            law_name = cls._clean_text(str(item.get("관련법령명") or ""))
            relation = cls._clean_text(str(item.get("법령간관계") or ""))
            if not law_name:
                continue
            if (
                ("주민등록번호" in normalized_query or "고유식별정보" in normalized_query or "민감정보" in normalized_query)
                and "하위법" in relation
                and base_primary_name
                and base_primary_name in law_name
            ):
                continue
            if not law_name.endswith("시행령") and not law_name.endswith("시행규칙"):
                queries.append(f"{law_name} 시행령")
            queries.append(law_name)

        deduped: List[str] = []
        seen = set()
        for query in queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    @classmethod
    def _sensitive_identifier_follow_up_queries(
        cls,
        user_query: str,
        law_data: Dict[str, Any],
    ) -> List[str]:
        if not cls._is_sensitive_identifier_question(user_query):
            return []

        queries: List[str] = []
        seen_families = set()
        for item in cls._extract_law_items(law_data)[:8]:
            law_name = cls._clean_text(
                str(item.get("법령명한글") or item.get("법령명") or item.get("name") or "")
            )
            family = cls._law_family_name(law_name)
            if not family or family in seen_families:
                continue
            seen_families.add(family)
            queries.append(f"{family} 시행령")
            queries.append(f"{family} 시행규칙")

        deduped: List[str] = []
        seen = set()
        for query in queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    def _expand_related_law_network(
        self,
        law_data: Dict[str, Any],
        metrics: Optional[Dict[str, int]] = None,
        max_hops: int = 2,
    ) -> List[Dict[str, Any]]:
        if not hasattr(self.law_api, "search_related_laws"):
            return []

        primary_law = self._pick_primary_law(law_data)
        if not primary_law:
            return []

        seed_ids: List[str] = []
        primary_law_id = primary_law.get("law_id")
        if primary_law_id:
            seed_ids.append(str(primary_law_id))

        expanded: List[Dict[str, Any]] = []
        seen_ids = set(seed_ids)
        frontier = seed_ids[:]

        for _ in range(max_hops):
            if not frontier:
                break
            next_frontier: List[str] = []
            for law_id in frontier:
                if metrics is not None:
                    self._increment_metric(metrics, "law_search_count")
                    self._increment_metric(metrics, "nlic_calls")
                try:
                    related_data = self.law_api.search_related_laws(law_id=law_id)
                except Exception:
                    continue
                for item in self._extract_related_law_items(related_data):
                    related_law_id = item.get("관련법령ID") or item.get("법령ID") or item.get("id")
                    key = str(related_law_id).strip() if related_law_id is not None else self._clean_text(str(item))
                    if not key or key in seen_ids:
                        continue
                    seen_ids.add(key)
                    expanded.append(item)
                    next_frontier.append(key)
            frontier = next_frontier

        return expanded

    @classmethod
    def _precedent_search_queries_refined(
        cls,
        user_query: str,
        used_search_query: Optional[str],
        article_numbers: List[str],
    ) -> List[str]:
        queries: List[str] = []
        issue_terms = cls._extract_precedent_issue_terms(user_query)
        normalized = cls._clean_text(user_query)
        anchor = issue_terms[0] if issue_terms else (cls._clean_text(used_search_query) if used_search_query else normalized)

        if used_search_query and article_numbers:
            for article_no in article_numbers[:2]:
                queries.append(f"{used_search_query} {article_no}")
                queries.append(f"{used_search_query} {article_no} {cls._PRECEDENT_SUFFIX}")

        if anchor:
            queries.append(f"{anchor} {cls._PRECEDENT_SUFFIX}")
            for term in issue_terms[:3]:
                if term == anchor:
                    continue
                queries.append(f"{anchor} {term}")
                queries.append(f"{anchor} {term} {cls._PRECEDENT_SUFFIX}")

        if used_search_query:
            queries.append(f"{used_search_query} {cls._PRECEDENT_SUFFIX}")

        queries.append(user_query)

        deduped: List[str] = []
        seen = set()
        for query in queries:
            normalized_query = cls._clean_text(query)
            if normalized_query and normalized_query not in seen:
                seen.add(normalized_query)
                deduped.append(normalized_query)
        return deduped

    def _fetch_article(
        self,
        law_id: str,
        article_no: str,
        metrics: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        if not hasattr(self.law_api, "get_article"):
            return {}
        if metrics is not None:
            self._increment_metric(metrics, "article_fetch_count")
            self._increment_metric(metrics, "nlic_calls")
        return self.law_api.get_article(law_id=law_id, article_no=article_no)

    def _find_keyword_matched_article(
        self,
        *,
        user_query: str,
        law_items: List[Dict[str, Any]],
        metrics: Optional[Dict[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._is_sensitive_identifier_question(user_query):
            return None
        if not hasattr(self.law_api, "find_article_by_keywords"):
            return None

        keywords = self._sensitive_identifier_keywords(user_query)
        explicit_law_match = re.search(
            r"([가-힣A-Za-z0-9 ]+?(?:법 시행규칙|법 시행령|법|시행규칙|시행령))",
            self._clean_text(user_query),
        )
        explicit_law_family = self._law_family_name(explicit_law_match.group(1)) if explicit_law_match else ""
        related_law_families = {
            self._law_family_name(query)
            for query in self._resolved_related_law_queries(user_query)
            if self._law_family_name(query)
        }
        best_match: Optional[Dict[str, Any]] = None
        best_total_score = -1
        for item in law_items:
            if not isinstance(item, dict):
                continue
            law_id = item.get("법령ID") or item.get("법령일련번호") or item.get("id")
            law_name = self._clean_text(
                str(item.get("법령명한글") or item.get("법령명") or item.get("name") or "")
            )
            if not law_id:
                continue
            if metrics is not None:
                self._increment_metric(metrics, "article_fetch_count")
                self._increment_metric(metrics, "nlic_calls")
            try:
                matched = self.law_api.find_article_by_keywords(str(law_id), keywords)
            except Exception:
                continue
            if matched and matched.get("article_no"):
                matched["law_name"] = law_name
                total_score = int(matched.get("score") or 0)
                law_family = self._law_family_name(law_name)
                if law_name.endswith("시행령"):
                    total_score += 4
                elif law_name.endswith("시행규칙"):
                    total_score += 2
                if explicit_law_family and explicit_law_family == law_family:
                    total_score += 8
                if law_family and law_family in related_law_families:
                    total_score += 6
                if total_score > best_total_score:
                    best_total_score = total_score
                    best_match = matched
        return best_match

    def _build_law_enrichment(
        self,
        user_query: str,
        law_data: Dict[str, Any],
        used_search_query: Optional[str] = None,
        risk_level: str = "LOW",
        metrics: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        all_laws = self._extract_law_items(law_data)
        keyword_matched_article = self._find_keyword_matched_article(
            user_query=user_query,
            law_items=all_laws,
            metrics=metrics,
        )
        if keyword_matched_article:
            matched_law_id = keyword_matched_article.get("law_id")
            matched_item = next(
                (
                    item
                    for item in all_laws
                    if str(item.get("법령ID") or item.get("법령일련번호") or item.get("id") or "").strip()
                    == str(matched_law_id).strip()
                ),
                None,
            )
            if matched_item:
                reordered = [matched_item] + [item for item in all_laws if item is not matched_item]
                law_data = {"LawSearch": {"law": reordered}}
                all_laws = reordered

        primary_law = self._pick_primary_law(law_data)
        enrichment: Dict[str, Any] = {
            "search_hit_count": len(all_laws),
            "primary_law": primary_law,
        }
        related_laws = []
        for item in all_laws[1:6]:
            law_id = item.get("법령ID") or item.get("법령일련번호") or item.get("id")
            law_name = item.get("법령명한글") or item.get("법령명_한글") or item.get("name")
            related_laws.append(
                {
                    "law_id": str(law_id).strip() if law_id is not None else None,
                    "law_name": str(law_name).strip() if law_name is not None else None,
                }
            )
        if related_laws:
            enrichment["related_laws"] = related_laws
        if not primary_law or not primary_law.get("law_id"):
            return enrichment

        law_id = primary_law["law_id"]
        article_numbers = self._extract_article_numbers(user_query)
        intent = self._question_intent(user_query)

        if hasattr(self.law_api, "get_version"):
            try:
                if metrics is not None:
                    self._increment_metric(metrics, "version_fetch_count")
                    self._increment_metric(metrics, "nlic_calls")
                enrichment["version"] = self.law_api.get_version(law_id)
            except Exception as exc:
                enrichment["version_error"] = str(exc)

        if keyword_matched_article:
            version_fields = (enrichment.get("version") or {}).get("version_fields") or {}
            effective_date = version_fields.get("시행일자")
            promulgation_no = (primary_law.get("raw") or {}).get("공포번호")
            enrichment["article"] = {
                "law_id": keyword_matched_article.get("law_id"),
                "article_no": keyword_matched_article.get("article_no"),
                "article_base_no": keyword_matched_article.get("article_base_no"),
                "found": True,
                "matched_via": keyword_matched_article.get("matched_via"),
                "article_text": keyword_matched_article.get("article_text"),
                "matched_clauses": [
                    {
                        **clause,
                        "article_link": self._public_law_link(
                            primary_law.get("law_name"),
                            effective_date,
                            promulgation_no,
                            clause.get("article_no"),
                        ),
                    }
                    for clause in keyword_matched_article.get("matched_clauses", [])
                    if isinstance(clause, dict)
                ],
            }
        elif article_numbers:
            try:
                enrichment["article"] = self._fetch_article(
                    law_id=law_id,
                    article_no=article_numbers[0],
                    metrics=metrics,
                )
            except Exception as exc:
                enrichment["article_error"] = str(exc)

        related_articles: List[Dict[str, Any]] = []
        should_fetch_related = intent in {"difference", "procedure", "applicability"} or len(article_numbers) > 1
        if should_fetch_related:
            for related_article_no in article_numbers[1:4]:
                try:
                    related_article = self._fetch_article(
                        law_id=law_id,
                        article_no=related_article_no,
                        metrics=metrics,
                    )
                except Exception as exc:
                    related_articles.append({"article_no": related_article_no, "found": False, "error": str(exc)})
                    continue
                related_articles.append(related_article)
        if related_articles:
            enrichment["related_articles"] = related_articles
            if metrics is not None:
                self._increment_metric(metrics, "related_article_count", len(related_articles))

        should_search_precedent = (
            risk_level == "HIGH"
            or intent in {"illegality", "applicability"}
            or self._wants_precedents(user_query)
        )
        if should_search_precedent and hasattr(self.law_api, "search_precedent"):
            precedent_queries = self._precedent_search_queries_refined(
                user_query,
                used_search_query,
                article_numbers,
            )
            reference_law = primary_law.get("law_name")
            precedent_data: Dict[str, Any] = {}
            used_precedent_query: Optional[str] = None
            for precedent_query in precedent_queries:
                try:
                    if metrics is not None:
                        self._increment_metric(metrics, "precedent_search_count")
                        self._increment_metric(metrics, "nlic_calls")
                    precedent_data = self.law_api.search_precedent(precedent_query, reference_law=reference_law)
                except TypeError:
                    if metrics is not None:
                        self._increment_metric(metrics, "precedent_search_count")
                        self._increment_metric(metrics, "nlic_calls")
                    precedent_data = self.law_api.search_precedent(precedent_query)
                except Exception as exc:
                    enrichment["precedent_error"] = str(exc)
                    precedent_data = {}
                    break
                if precedent_data and self._extract_precedent_items(precedent_data):
                    used_precedent_query = precedent_query
                    break

            if precedent_data and self._extract_precedent_items(precedent_data):
                enrichment["precedent_search"] = precedent_data
                enrichment["precedent_search_queries"] = precedent_queries
                enrichment["used_precedent_query"] = used_precedent_query
                primary_precedent = self._extract_precedent_items(precedent_data)[0]
                enrichment["primary_precedent"] = primary_precedent
                precedent_id = (
                    primary_precedent.get("판례일련번호")
                    or primary_precedent.get("사건번호")
                    or primary_precedent.get("id")
                )
                if precedent_id and hasattr(self.law_api, "get_precedent"):
                    try:
                        if metrics is not None:
                            self._increment_metric(metrics, "precedent_fetch_count")
                            self._increment_metric(metrics, "nlic_calls")
                        enrichment["precedent_detail"] = self.law_api.get_precedent(str(precedent_id))
                    except Exception as exc:
                        enrichment["precedent_detail_error"] = str(exc)

        return enrichment

    @staticmethod
    def _law_context_lines(enrichment: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        primary_law = enrichment.get("primary_law") or {}
        if primary_law.get("law_name"):
            lines.append(f"대표 법령: {primary_law['law_name']}")
        if primary_law.get("law_id"):
            lines.append(f"법령ID: {primary_law['law_id']}")
        related_laws = enrichment.get("related_laws") or []
        if related_laws:
            labels = [law["law_name"] for law in related_laws if isinstance(law, dict) and law.get("law_name")]
            if labels:
                lines.append("관련 법령: " + ", ".join(labels[:3]))

        version = enrichment.get("version")
        if isinstance(version, dict):
            version_fields = version.get("version_fields") or {}
            enacted = version_fields.get("시행일자")
            promulgated = version_fields.get("공포일자") or version_fields.get("공포 일자")
            revision_type = version_fields.get("제개정구분명") or version_fields.get("제개정구분")
            if enacted:
                lines.append(f"시행일자: {enacted}")
            if promulgated:
                lines.append(f"공포일자: {promulgated}")
            if revision_type:
                lines.append(f"제개정구분: {revision_type}")

        article = enrichment.get("article")
        if isinstance(article, dict) and article.get("found") and article.get("article_text"):
            lines.append(f"관련 조문: {article['article_no']}")
            lines.append(f"조문 요약: {RequestPipeline._truncate_text(article['article_text'])}")

        valid_related = [
            related
            for related in enrichment.get("related_articles") or []
            if isinstance(related, dict) and related.get("found") and related.get("article_no")
        ]
        if valid_related:
            lines.append("추가 확인 조문: " + ", ".join(str(article["article_no"]) for article in valid_related[:3]))

        primary_precedent = enrichment.get("primary_precedent") or {}
        if primary_precedent:
            precedent_name = (
                primary_precedent.get("사건명")
                or primary_precedent.get("판례명")
                or primary_precedent.get("사건번호")
            )
            if precedent_name:
                lines.append(f"참고 판례: {precedent_name}")

        return lines

    def _summarize_search_results(self, law_data: Dict[str, Any], used_search_query: Optional[str]) -> Dict[str, Any]:
        items = RequestPipeline._extract_law_items(law_data)
        results = []
        for item in items[:5]:
            law_id = item.get("법령ID") or item.get("id")
            results.append(
                {
                    "law_id": law_id,
                    "law_name": item.get("법령명한글") or item.get("법령명_한글"),
                    "law_type": item.get("법령구분명"),
                    "effective_date": item.get("시행일자"),
                    "promulgation_date": item.get("공포일자"),
                    "law_link": self._item_public_law_link(item),
                }
            )
        return {
            "used_search_query": used_search_query,
            "search_hit_count": len(items),
            "results": results,
        }

    def _summarize_article(
        self,
        article: Dict[str, Any],
        *,
        law_name: Optional[str] = None,
        effective_date: Optional[str] = None,
        promulgation_no: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(article, dict) or not article.get("found"):
            return None
        return {
            "article_no": article.get("article_no"),
            "found": True,
            "matched_via": article.get("matched_via"),
            "article_text_excerpt": RequestPipeline._truncate_text(str(article.get("article_text", "")), 180),
            "article_link": self._public_law_link(
                law_name,
                effective_date,
                promulgation_no,
                article.get("article_base_no") or article.get("article_no"),
            ),
            "matched_clauses": [
                {
                    "article_no": clause.get("article_no"),
                    "article_text_excerpt": RequestPipeline._truncate_text(str(clause.get("article_text", "")), 120),
                    "article_link": self._public_law_link(
                        law_name,
                        effective_date,
                        promulgation_no,
                        clause.get("article_no"),
                    ),
                }
                for clause in (article.get("matched_clauses") or [])
                if isinstance(clause, dict) and clause.get("article_no")
            ],
        }

    def _summarize_law_enrichment(self, enrichment: Dict[str, Any]) -> Dict[str, Any]:
        primary_law = enrichment.get("primary_law") or {}
        version = enrichment.get("version") or {}
        version_fields = version.get("version_fields") or {}
        primary_law_name = primary_law.get("law_name")
        primary_effective_date = version_fields.get("시행일자")
        primary_promulgation_no = (primary_law.get("raw") or {}).get("공포번호")
        article_summary = self._summarize_article(
            enrichment.get("article") or {},
            law_name=primary_law_name,
            effective_date=primary_effective_date,
            promulgation_no=primary_promulgation_no,
        )
        related_summaries = [
            summary
            for summary in (
                self._summarize_article(
                    article,
                    law_name=primary_law_name,
                    effective_date=primary_effective_date,
                    promulgation_no=primary_promulgation_no,
                )
                for article in enrichment.get("related_articles") or []
            )
            if summary
        ]
        primary_precedent = enrichment.get("primary_precedent") or {}
        precedent_summary = None
        if primary_precedent:
            precedent_summary = {
                "precedent_id": primary_precedent.get("판례일련번호") or primary_precedent.get("id"),
                "case_no": primary_precedent.get("사건번호"),
                "case_name": primary_precedent.get("사건명") or primary_precedent.get("판례명"),
                "court_name": primary_precedent.get("법원명"),
                "decision_date": primary_precedent.get("선고일자"),
            }

        return {
            "search_queries": enrichment.get("search_queries", []),
            "related_law_queries": enrichment.get("related_law_queries", []),
            "used_search_query": enrichment.get("used_search_query"),
            "precedent_search_queries": enrichment.get("precedent_search_queries", []),
            "used_precedent_query": enrichment.get("used_precedent_query"),
            "primary_law": {
                "law_id": primary_law.get("law_id"),
                "law_name": primary_law.get("law_name"),
                "law_link": self._public_law_link(
                    primary_law_name,
                    primary_effective_date,
                    primary_promulgation_no,
                ),
            }
            if primary_law
            else None,
            "related_laws": enrichment.get("related_laws", []),
            "version": {
                "source_target": version.get("source_target"),
                "effective_date": version_fields.get("시행일자"),
                "promulgation_date": version_fields.get("공포일자") or version_fields.get("공포 일자"),
                "revision_type": version_fields.get("제개정구분명") or version_fields.get("제개정구분"),
            }
            if version
            else None,
            "article": article_summary,
            "related_articles": related_summaries,
            "precedent": precedent_summary,
        }

    def process(self, req: PipelineRequest) -> PipelineResponse:
        request_id = req.request_id or str(uuid.uuid4())
        started = time.perf_counter()

        risk_level = "LOW"
        mode = "single_agent"
        tokens_in = len((req.user_query + " " + (req.context or "")).split())
        tokens_out = 0
        score = 0.0
        intent = self._question_intent(req.user_query)
        search_analysis = self._analyze_law_search(req.user_query)
        question_summary = self._question_summary(req.user_query)
        call_metrics: Dict[str, int] = {
            "law_search_count": 0,
            "version_fetch_count": 0,
            "article_fetch_count": 0,
            "related_article_count": 0,
            "precedent_search_count": 0,
            "precedent_fetch_count": 0,
            "nlic_calls": 0,
        }

        try:
            risk = self.risk_classifier.classify(req.user_query)
            risk_level = risk.risk_level

            prompt_payload = build_request_prompt(user_query=req.user_query, context=req.context)
            if not prompt_payload.get("system") or not prompt_payload.get("user"):
                raise PipelineStageError("PromptBuilder", "invalid_prompt_payload")
            prompt_policy = extract_prompt_policy(prompt_payload)

            mode = "multi_agent" if risk_level == "HIGH" else "single_agent"
            if prompt_policy.prefer_multi_agent_for_risky_queries and (
                risk_level == "HIGH" or intent in {"illegality", "applicability"}
            ):
                mode = "multi_agent"

            related_law_queries = search_analysis.related_law_queries
            search_queries = search_analysis.search_queries
            law_data: Dict[str, Any] = {}
            used_search_query: Optional[str] = None
            search_datasets: List[Dict[str, Any]] = []
            searched_queries = set()
            for search_query in search_queries:
                if search_query in searched_queries:
                    continue
                searched_queries.add(search_query)
                self._increment_metric(call_metrics, "law_search_count")
                self._increment_metric(call_metrics, "nlic_calls")
                result = self.law_api.search_law(search_query)
                if result and self._extract_law_items(result):
                    search_datasets.append(result)
                    law_data = result
                    used_search_query = search_query
                    break
            for related_query in related_law_queries:
                if related_query in searched_queries:
                    continue
                searched_queries.add(related_query)
                self._increment_metric(call_metrics, "law_search_count")
                self._increment_metric(call_metrics, "nlic_calls")
                result = self.law_api.search_law(related_query)
                if result and self._extract_law_items(result):
                    search_datasets.append(result)

            if search_datasets:
                law_data = self._merge_law_results(search_datasets)

            if not law_data or not self._extract_law_items(law_data):
                raise PipelineStageError("LawAPI", "empty_law_data")

            related_network = self._expand_related_law_network(law_data, metrics=call_metrics)
            if related_network:
                follow_up_datasets: List[Dict[str, Any]] = []
                primary_law = self._pick_primary_law(law_data) or {}
                follow_up_queries = self._expanded_related_search_queries(
                    related_network,
                    user_query=req.user_query,
                    primary_law_name=str(primary_law.get("law_name") or ""),
                )
                for follow_up_query in follow_up_queries:
                    if follow_up_query in searched_queries:
                        continue
                    searched_queries.add(follow_up_query)
                    self._increment_metric(call_metrics, "law_search_count")
                    self._increment_metric(call_metrics, "nlic_calls")
                    result = self.law_api.search_law(follow_up_query)
                    if result and self._extract_law_items(result):
                        follow_up_datasets.append(result)
                if follow_up_datasets:
                    law_data = self._merge_law_results(follow_up_datasets + [law_data])
                law_data = self._merge_related_law_items(law_data, related_network)

            sensitive_follow_up_queries = self._sensitive_identifier_follow_up_queries(req.user_query, law_data)
            sensitive_follow_up_datasets: List[Dict[str, Any]] = []
            for follow_up_query in sensitive_follow_up_queries:
                if follow_up_query in searched_queries:
                    continue
                searched_queries.add(follow_up_query)
                self._increment_metric(call_metrics, "law_search_count")
                self._increment_metric(call_metrics, "nlic_calls")
                result = self.law_api.search_law(follow_up_query)
                if result and self._extract_law_items(result):
                    sensitive_follow_up_datasets.append(result)
            if sensitive_follow_up_datasets:
                law_data = self._merge_law_results(sensitive_follow_up_datasets + [law_data])

            law_enrichment = self._build_law_enrichment(
                req.user_query,
                law_data,
                used_search_query=used_search_query,
                risk_level=risk_level,
                metrics=call_metrics,
            )
            law_enrichment["search_queries"] = search_queries
            law_enrichment["related_law_queries"] = related_law_queries
            law_enrichment["used_search_query"] = used_search_query
            law_enrichment["prompt_policy"] = prompt_policy.as_dict()
            enriched_context = self._merge_context(req.context, self._law_context_lines(law_enrichment))

            agent_result = self.agent_engine.run(
                question=req.user_query,
                context=enriched_context,
                risk_level=risk_level,
                law_enrichment=law_enrichment,
            )
            law_enrichment["review_summary"] = agent_result.review_summary
            answer = self.answer_composer.compose(
                AnswerCompositionInput(
                    user_query=req.user_query,
                    prompt_payload=prompt_payload,
                    law_enrichment=law_enrichment,
                    risk_level=risk_level,
                    fallback_answer=agent_result.integrated_review,
                )
            )
            tokens_out = len(answer.split())

            citations = {
                "law_search": self._summarize_search_results(law_data, used_search_query),
                "law_context": self._summarize_law_enrichment(law_enrichment),
                "review_summary": agent_result.review_summary,
                "prompt_policy": prompt_policy.as_dict(),
            }
            self._validate(answer=answer, citations=citations)

            score_result = self.scorer.calculate(
                ConfidenceInput(
                    evidence_fidelity=0.8 if citations else 0.0,
                    risk_control=1.0 if risk_level == "HIGH" else 0.7,
                    procedural_compliance=1.0,
                    reproducibility=0.9,
                )
            )
            score = score_result.total_score

            latency = round((time.perf_counter() - started) * 1000, 3)
            cost = self._estimate_cost(tokens_in=tokens_in, tokens_out=tokens_out)
            related_laws = law_enrichment.get("related_laws") or []
            has_precedent = bool(law_enrichment.get("primary_precedent"))
            self.logger.log_request(
                CostLogEntry(
                    request_id=request_id,
                    risk_level=risk_level,
                    mode=mode,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                    latency=latency,
                    score=score,
                    question_summary=question_summary,
                    question_intent=intent,
                    tool_calls=call_metrics["nlic_calls"],
                    nlic_calls=call_metrics["nlic_calls"],
                    law_search_count=call_metrics["law_search_count"],
                    version_fetch_count=call_metrics["version_fetch_count"],
                    article_fetch_count=call_metrics["article_fetch_count"],
                    related_article_count=call_metrics["related_article_count"],
                    related_law_count=len(related_laws),
                    precedent_search_count=call_metrics["precedent_search_count"],
                    precedent_fetch_count=call_metrics["precedent_fetch_count"],
                    has_precedent=has_precedent,
                    has_related_laws=bool(related_laws),
                )
            )

            return PipelineResponse(
                request_id=request_id,
                risk_level=risk_level,
                mode=mode,
                answer=answer,
                citations=citations,
                score=score,
                latency_ms=latency,
            )

        except PipelineStageError as exc:
            if exc.stage == "LawAPI":
                self._record_law_hint_suggestion(
                    request_id=request_id,
                    req=req,
                    analysis=search_analysis,
                    question_summary=question_summary,
                )
            latency = round((time.perf_counter() - started) * 1000, 3)
            cost = self._estimate_cost(tokens_in=tokens_in, tokens_out=tokens_out)
            self.logger.log_request(
                CostLogEntry(
                    request_id=request_id,
                    risk_level=risk_level,
                    mode=f"error:{exc.stage}",
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                    latency=latency,
                    score=score,
                    question_summary=question_summary,
                    question_intent=intent,
                    error_stage=exc.stage,
                    tool_calls=call_metrics["nlic_calls"],
                    nlic_calls=call_metrics["nlic_calls"],
                    law_search_count=call_metrics["law_search_count"],
                    version_fetch_count=call_metrics["version_fetch_count"],
                    article_fetch_count=call_metrics["article_fetch_count"],
                    related_article_count=call_metrics["related_article_count"],
                    precedent_search_count=call_metrics["precedent_search_count"],
                    precedent_fetch_count=call_metrics["precedent_fetch_count"],
                )
            )
            return PipelineResponse(
                request_id=request_id,
                risk_level=risk_level,
                mode=f"error:{exc.stage}",
                answer="",
                citations={},
                score=score,
                latency_ms=latency,
                error={"stage": exc.stage, "message": exc.message},
            )
        except Exception as exc:
            latency = round((time.perf_counter() - started) * 1000, 3)
            cost = self._estimate_cost(tokens_in=tokens_in, tokens_out=tokens_out)
            self.logger.log_request(
                CostLogEntry(
                    request_id=request_id,
                    risk_level=risk_level,
                    mode="error:Unhandled",
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                    latency=latency,
                    score=score,
                    question_summary=question_summary,
                    question_intent=intent,
                    error_stage="Unhandled",
                    tool_calls=call_metrics["nlic_calls"],
                    nlic_calls=call_metrics["nlic_calls"],
                    law_search_count=call_metrics["law_search_count"],
                    version_fetch_count=call_metrics["version_fetch_count"],
                    article_fetch_count=call_metrics["article_fetch_count"],
                    related_article_count=call_metrics["related_article_count"],
                    precedent_search_count=call_metrics["precedent_search_count"],
                    precedent_fetch_count=call_metrics["precedent_fetch_count"],
                )
            )
            return PipelineResponse(
                request_id=request_id,
                risk_level=risk_level,
                mode="error:Unhandled",
                answer="",
                citations={},
                score=score,
                latency_ms=latency,
                error={"stage": "Unhandled", "message": str(exc)},
            )
