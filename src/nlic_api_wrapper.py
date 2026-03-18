"""국가법령정보센터(NLIC) API wrapper with in-memory cache.

Implemented features:
- search_law
- search_related_laws
- get_article
- get_version
- validate_article
- search_precedent
- get_precedent
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class CacheEntry:
    value: Dict[str, Any]
    expires_at: float


class NlicApiWrapper:
    """Thin API wrapper for NLIC endpoints with TTL cache support."""

    DEFAULT_BASE_URL = "https://www.law.go.kr/DRF/lawSearch.do"
    DEFAULT_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

    def __init__(
        self,
        oc: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        service_url: str = DEFAULT_SERVICE_URL,
        cache_ttl_seconds: int = 300,
    ) -> None:
        oc_value = oc or os.getenv("NLIC_OC")
        if not oc_value:
            raise ValueError("NLIC_OC is required")
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")

        self.oc = oc_value
        self.base_url = base_url
        self.service_url = service_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], CacheEntry] = {}

    def _cache_key(self, action: str, params: Dict[str, Any]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        normalized = tuple(sorted((k, str(v)) for k, v in params.items()))
        return action, normalized

    def _get_cached(self, key: Tuple[str, Tuple[Tuple[str, str], ...]]) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() > entry.expires_at:
            self._cache.pop(key, None)
            return None
        return entry.value

    def _set_cached(self, key: Tuple[str, Tuple[Tuple[str, str], ...]], value: Dict[str, Any]) -> None:
        self._cache[key] = CacheEntry(
            value=value,
            expires_at=time.time() + self.cache_ttl_seconds,
        )

    def _request(self, params: Dict[str, Any], endpoint_url: Optional[str] = None) -> Dict[str, Any]:
        query = urlencode(params)
        url = f"{endpoint_url or self.base_url}?{query}"
        with urlopen(url, timeout=15) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            # NLIC may return XML/text depending on API options.
            return {"raw": payload}

    def _call(self, action: str, extra_params: Dict[str, Any], endpoint: str = "search") -> Dict[str, Any]:
        params = {"OC": self.oc, "target": action, "type": "JSON"}
        params.update(extra_params)

        endpoint_url = self.service_url if endpoint == "service" else self.base_url
        cache_action = f"{endpoint}:{action}"
        key = self._cache_key(action=cache_action, params=params)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        result = self._request(params, endpoint_url=endpoint_url)
        self._set_cached(key, result)
        return result

    @staticmethod
    def _is_blank_raw(result: Dict[str, Any]) -> bool:
        raw = result.get("raw")
        return isinstance(raw, str) and not raw.strip()

    @staticmethod
    def _has_version_payload(result: Dict[str, Any]) -> bool:
        versions = result.get("versions")
        if isinstance(versions, list) and versions:
            return True

        return any(
            NlicApiWrapper._extract_from_nested(result, (key,)) is not None
            for key in ("시행일자", "공포일자", "제개정구분", "제개정구분명", "개정문")
        )

    @staticmethod
    def _extract_from_nested(obj: Any, key_candidates: Tuple[str, ...]) -> Optional[str]:
        if isinstance(obj, dict):
            for key in key_candidates:
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in obj.values():
                hit = NlicApiWrapper._extract_from_nested(value, key_candidates)
                if hit:
                    return hit
        elif isinstance(obj, list):
            for item in obj:
                hit = NlicApiWrapper._extract_from_nested(item, key_candidates)
                if hit:
                    return hit
        return None

    @staticmethod
    def _normalize_article_no(article_no: str) -> str:
        compact = re.sub(r"\s+", "", article_no)
        return compact

    @classmethod
    def _article_no_candidates(cls, article_no: str) -> Tuple[str, ...]:
        compact = cls._normalize_article_no(article_no)
        candidates = []

        if compact:
            candidates.append(compact)

        match = re.fullmatch(r"(?:제)?(\d+)조(?:의(\d+))?", compact)
        if match:
            main_no = int(match.group(1))
            sub_no = match.group(2)
            if sub_no is not None:
                candidates.append(f"{main_no:04d}{int(sub_no):02d}")
            candidates.append(f"{main_no:04d}00")

        deduped = []
        seen = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return tuple(deduped)

    @staticmethod
    def _contains_article_no(text: str, article_no: str) -> bool:
        return NlicApiWrapper._normalize_article_no(article_no) in NlicApiWrapper._normalize_article_no(text)

    @staticmethod
    def _extract_mst(source: Dict[str, Any]) -> Optional[str]:
        return NlicApiWrapper._extract_from_nested(source, ("법령일련번호", "MST", "mst"))

    def search_law(self, query: str) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("query must not be empty")
        return self._call("law", {"query": query.strip()})

    def search_related_laws(
        self,
        *,
        query: Optional[str] = None,
        law_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        normalized_law_id = (law_id or "").strip()
        if not normalized_query and not normalized_law_id:
            raise ValueError("query or law_id is required")

        params: Dict[str, Any] = {}
        if normalized_law_id:
            params["ID"] = normalized_law_id
        else:
            params["query"] = normalized_query
        return self._call("lsRlt", params)

    def search_precedent(self, query: str, reference_law: Optional[str] = None) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("query must not be empty")

        params: Dict[str, Any] = {"query": query.strip()}
        if reference_law and reference_law.strip():
            params["JO"] = reference_law.strip()
        return self._call("prec", params)

    def get_precedent(self, precedent_id: str) -> Dict[str, Any]:
        if not precedent_id.strip():
            raise ValueError("precedent_id is required")
        normalized_precedent_id = precedent_id.strip()
        return self._call("prec", {"ID": normalized_precedent_id}, endpoint="service")

    def _extract_article_text(self, source: Any, article_no: str) -> Optional[str]:
        article_keys = ("조문내용", "조문", "내용", "본문", "조문단위")
        article_ref_keys = ("조문번호", "조번호", "조문제목", "조문키")

        def _walk(node: Any) -> Optional[str]:
            if isinstance(node, dict):
                # First: strict match by article_no near article-like fields.
                ref_text = " ".join(
                    str(node.get(k, "")) for k in article_ref_keys if isinstance(node.get(k), (str, int))
                )
                for key in article_keys:
                    value = node.get(key)
                    if isinstance(value, str) and value.strip():
                        if self._contains_article_no(value, article_no) or (
                            ref_text and self._contains_article_no(ref_text, article_no)
                        ):
                            return value.strip()
                # Recurse.
                for value in node.values():
                    hit = _walk(value)
                    if hit:
                        return hit
            elif isinstance(node, list):
                for item in node:
                    hit = _walk(item)
                    if hit:
                        return hit
            return None

        # Pass 1: strict by article_no
        hit = _walk(source)
        if hit:
            return hit

        # Pass 2: conservative fallback only for explicit 조문내용 key.
        return self._extract_from_nested(source, ("조문내용",))

    def get_article(self, law_id: str, article_no: str) -> Dict[str, Any]:
        if not law_id.strip() or not article_no.strip():
            raise ValueError("law_id and article_no are required")

        normalized_law_id = law_id.strip()
        normalized_article_no = article_no.strip()
        article_candidates = self._article_no_candidates(normalized_article_no)

        attempts = []
        for jo_value in article_candidates:
            attempts.append(("service", "law", {"ID": normalized_law_id, "JO": jo_value}))
            attempts.append(("service", "lawjosub", {"ID": normalized_law_id, "JO": jo_value}))

        if not normalized_article_no.isdigit():
            attempts.extend(
                [
                    ("search", "law", {"ID": normalized_law_id, "JO": normalized_article_no}),
                    ("service", "jo", {"ID": normalized_law_id, "JO": normalized_article_no}),
                ]
            )

        source: Dict[str, Any] = {}
        article_text: Optional[str] = None
        matched_via: Optional[str] = None
        attempted_queries = []

        for endpoint, target, params in attempts:
            attempted_queries.append({"endpoint": endpoint, "target": target, "params": dict(params)})
            try:
                source = self._call(target, params, endpoint=endpoint)
            except HTTPError as exc:
                attempted_queries[-1]["error"] = f"HTTP {exc.code}"
                continue
            article_text = self._extract_article_text(source, normalized_article_no)
            if article_text:
                matched_via = f"{endpoint}:{target}"
                break

        # fallback via MST/JO when caller provided 법령ID
        if not article_text:
            search_source = self._call("law", {"ID": normalized_law_id})
            mst = self._extract_mst(search_source)
            if mst:
                for jo_value in article_candidates:
                    for target in ("law", "lawjosub"):
                        attempted_queries.append(
                            {
                                "endpoint": "service",
                                "target": target,
                                "params": {"MST": mst, "JO": jo_value},
                            }
                        )
                        try:
                            mst_source = self._call(
                                target,
                                {"MST": mst, "JO": jo_value},
                                endpoint="service",
                            )
                        except HTTPError as exc:
                            attempted_queries[-1]["error"] = f"HTTP {exc.code}"
                            continue
                        mst_text = self._extract_article_text(mst_source, normalized_article_no)
                        if mst_text:
                            source = mst_source
                            article_text = mst_text
                            matched_via = f"service:{target}:mst"
                            break
                    if article_text:
                        break

        return {
            "law_id": normalized_law_id,
            "article_no": normalized_article_no,
            "article_candidates": list(article_candidates),
            "found": bool(article_text),
            "article_text": article_text,
            "matched_via": matched_via,
            "attempted_queries": attempted_queries,
            "source": source,
        }

    @staticmethod
    def _article_no_from_unit(unit: Dict[str, Any]) -> Optional[str]:
        article_no = str(unit.get("조문번호") or "").strip()
        branch_no = str(unit.get("조문가지번호") or "").strip()
        if not article_no:
            content = str(unit.get("조문내용") or "")
            match = re.match(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", content)
            if not match:
                return None
            article_no = match.group(1)
            branch_no = match.group(2) or ""
        if branch_no:
            return f"제{int(article_no)}조의{int(branch_no)}"
        return f"제{int(article_no)}조"

    @staticmethod
    def _unit_search_text(unit: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("조문제목", "조문내용"):
            value = unit.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, str) and node.strip():
                parts.append(node.strip())

        for key in ("항", "호", "목"):
            _walk(unit.get(key))
        return "\n".join(parts)

    @staticmethod
    def _unit_heading_text(unit: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("조문제목", "조문내용", "항내용", "호내용", "목내용"):
            value = unit.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts)

    @staticmethod
    def _match_score(text: str, keywords: List[str]) -> int:
        score = sum(2 if keyword in text else 0 for keyword in keywords)
        if "처리할 수" in text:
            score += 2
        if "불가피" in text:
            score += 1
        return score

    @staticmethod
    def _join_pinpoint(*parts: Optional[str]) -> str:
        return " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())

    @staticmethod
    def _as_list(node: Any) -> List[Any]:
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            return [node]
        return []

    @staticmethod
    def _item_label(number_key: str, branch_key: str, suffix: str, node: Dict[str, Any]) -> str:
        number = str(node.get(number_key) or "").strip()
        branch = str(node.get(branch_key) or "").strip()
        base_number = number.rstrip(".")
        if not base_number:
            return ""
        if not branch:
            return f"제{base_number}{suffix}"
        return f"제{base_number}{suffix}의{branch}"

    def _best_match_in_unit(self, unit: Dict[str, Any], keywords: List[str]) -> Optional[Dict[str, Any]]:
        article_no = self._article_no_from_unit(unit)
        if not article_no:
            return None

        best_match: Optional[Dict[str, Any]] = None
        child_matches: List[Dict[str, Any]] = []

        def _maybe_update(text: str, pinpoint: str, *, depth_bonus: int = 0, prefer_child: bool = False) -> None:
            nonlocal best_match
            score = self._match_score(text, keywords)
            if score <= 0:
                return
            candidate = {
                "article_no": pinpoint,
                "article_base_no": article_no,
                "article_text": text,
                "score": score + depth_bonus,
            }
            if best_match is None or candidate["score"] > best_match["score"]:
                best_match = candidate
            if prefer_child:
                child_matches.append(candidate)

        base_text = self._unit_heading_text(unit)
        if base_text:
            _maybe_update(base_text, article_no)

        paragraphs = self._as_list(unit.get("항"))
        if paragraphs:
            for paragraph in paragraphs:
                if not isinstance(paragraph, dict):
                    continue
                paragraph_no = str(paragraph.get("항번호") or "").strip()
                paragraph_text = self._unit_heading_text(paragraph)
                if paragraph_text and paragraph_no:
                    _maybe_update(
                        paragraph_text,
                        self._join_pinpoint(article_no, paragraph_no),
                        depth_bonus=1,
                        prefer_child=True,
                    )

                items = self._as_list(paragraph.get("호"))
                if items:
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        item_no = self._item_label("호번호", "호가지번호", "호", item)
                        item_text = self._unit_heading_text(item)
                        if item_text:
                            _maybe_update(
                                item_text,
                                self._join_pinpoint(article_no, paragraph_no, item_no),
                                depth_bonus=3,
                                prefer_child=True,
                            )

                        subitems = self._as_list(item.get("목"))
                        if subitems:
                            for subitem in subitems:
                                if not isinstance(subitem, dict):
                                    continue
                                subitem_no = self._item_label("목번호", "목가지번호", "목", subitem)
                                subitem_text = self._unit_heading_text(subitem)
                                if subitem_text:
                                    _maybe_update(
                                        subitem_text,
                                        self._join_pinpoint(article_no, paragraph_no, item_no, subitem_no),
                                        depth_bonus=4,
                                        prefer_child=True,
                                    )

        if child_matches and base_text:
            ordered_children: List[Dict[str, Any]] = []
            seen_child_labels = set()
            for child in sorted(child_matches, key=lambda item: (-item["score"], item["article_no"])):
                label = child["article_no"]
                if label in seen_child_labels:
                    continue
                seen_child_labels.add(label)
                ordered_children.append(child)
            return {
                "article_no": article_no,
                "article_base_no": article_no,
                "article_text": base_text,
                "matched_clauses": ordered_children[:3],
                "score": (ordered_children[0]["score"] if ordered_children else 0) + max(self._match_score(base_text, keywords), 1),
            }

        return best_match

    def find_article_by_keywords(self, law_id: str, keywords: List[str]) -> Optional[Dict[str, Any]]:
        normalized_law_id = law_id.strip()
        normalized_keywords = [keyword.strip() for keyword in keywords if keyword and keyword.strip()]
        if not normalized_law_id or not normalized_keywords:
            return None

        source = self._call("law", {"ID": normalized_law_id}, endpoint="service")
        law = source.get("법령") if isinstance(source, dict) else None
        jo = law.get("조문") if isinstance(law, dict) else None
        units = jo.get("조문단위") if isinstance(jo, dict) else None
        if not isinstance(units, list):
            return None

        best_match: Optional[Dict[str, Any]] = None
        for unit in units:
            if not isinstance(unit, dict) or unit.get("조문여부") != "조문":
                continue
            candidate = self._best_match_in_unit(unit, normalized_keywords)
            if candidate and (best_match is None or candidate["score"] > best_match["score"]):
                best_match = candidate

        if not best_match:
            return None
        return {
            "law_id": normalized_law_id,
            "article_no": best_match["article_no"],
            "article_base_no": best_match["article_base_no"],
            "article_text": best_match["article_text"],
            "matched_clauses": best_match.get("matched_clauses", []),
            "matched_via": "service:law:keyword_scan",
            "score": best_match["score"],
        }

    def get_version(self, law_id: str) -> Dict[str, Any]:
        if not law_id.strip():
            raise ValueError("law_id is required")

        normalized_law_id = law_id.strip()
        history_result = self._call("history", {"ID": normalized_law_id})

        # Some environments return blank raw or structurally empty payload for target=history.
        if history_result and not self._is_blank_raw(history_result) and self._has_version_payload(history_result):
            return {
                "law_id": normalized_law_id,
                "source_target": "history",
                "data": history_result,
            }

        # Fallback: derive version metadata from law target.
        law_result = self._call("law", {"ID": normalized_law_id})
        version_fields = {}
        for key in ("시행일자", "공포일자", "제개정구분", "제개정구분명", "개정문"):
            value = self._extract_from_nested(law_result, (key,))
            if value:
                version_fields[key] = value

        return {
            "law_id": normalized_law_id,
            "source_target": "law_fallback",
            "version_fields": version_fields,
            "data": law_result,
        }

    def validate_article(self, law_id: str, article_no: str) -> Dict[str, Any]:
        """Validate article existence using get_article result."""
        article_result = self.get_article(law_id=law_id, article_no=article_no)

        return {
            "law_id": article_result["law_id"],
            "article_no": article_result["article_no"],
            "is_valid": bool(article_result.get("found")),
            "source": article_result,
        }

    def clear_cache(self) -> None:
        self._cache.clear()
