"""Suggestion storage for approved related-law hint expansion."""

from __future__ import annotations

import json
import hashlib
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dedupe_texts(values: List[str]) -> List[str]:
    seen = set()
    deduped: List[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


@dataclass
class LawHintSuggestion:
    id: str
    fingerprint: str
    request_id: str
    question_summary: str
    user_query: str
    question_intent: str
    related_law_queries: List[str]
    issue_terms: List[str]
    search_queries: List[str]
    proposed_keywords: List[str]
    status: str
    occurrence_count: int
    created_at: str
    updated_at: str
    approved_law_name: Optional[str] = None
    approved_keywords: Optional[List[str]] = None


class LawHintSuggestionStore:
    """Persists pending law-hint suggestions and approved overrides."""

    def __init__(
        self,
        suggestions_path: str = "data/law_hint_suggestions.json",
        overrides_path: str = "data/law_hint_overrides.json",
    ) -> None:
        self.suggestions_path = Path(suggestions_path)
        self.overrides_path = Path(overrides_path)
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def fingerprint_for_query(user_query: str) -> str:
        normalized = " ".join((user_query or "").split()).strip().lower()
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def _load_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _write_json(self, path: Path, payload) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_suggestions(self, status: Optional[str] = None) -> List[LawHintSuggestion]:
        raw_items = self._load_json(self.suggestions_path, [])
        suggestions = [LawHintSuggestion(**item) for item in raw_items]
        if status:
            suggestions = [item for item in suggestions if item.status == status]
        return suggestions

    def approved_overrides(self) -> Dict[str, List[str]]:
        raw = self._load_json(self.overrides_path, {})
        cleaned: Dict[str, List[str]] = {}
        for law_name, keywords in raw.items():
            if not isinstance(law_name, str):
                continue
            if not isinstance(keywords, list):
                continue
            deduped = _dedupe_texts([str(keyword) for keyword in keywords])
            if deduped:
                cleaned[law_name] = deduped
        return cleaned

    def create_or_update_suggestion(
        self,
        *,
        request_id: str,
        question_summary: str,
        user_query: str,
        question_intent: str,
        related_law_queries: List[str],
        issue_terms: List[str],
        search_queries: List[str],
        proposed_keywords: List[str],
    ) -> LawHintSuggestion:
        suggestions = self.list_suggestions()
        fingerprint = self.fingerprint_for_query(user_query)
        now = _utc_now()

        for suggestion in suggestions:
            if suggestion.fingerprint != fingerprint:
                continue
            suggestion.request_id = request_id
            suggestion.question_summary = question_summary
            suggestion.user_query = user_query
            suggestion.question_intent = question_intent
            suggestion.related_law_queries = _dedupe_texts(related_law_queries)
            suggestion.issue_terms = _dedupe_texts(issue_terms)
            suggestion.search_queries = _dedupe_texts(search_queries)
            suggestion.proposed_keywords = _dedupe_texts(proposed_keywords)
            suggestion.updated_at = now
            suggestion.occurrence_count += 1
            self._save_suggestions(suggestions)
            return suggestion

        suggestion = LawHintSuggestion(
            id=str(uuid.uuid4()),
            fingerprint=fingerprint,
            request_id=request_id,
            question_summary=question_summary,
            user_query=user_query,
            question_intent=question_intent,
            related_law_queries=_dedupe_texts(related_law_queries),
            issue_terms=_dedupe_texts(issue_terms),
            search_queries=_dedupe_texts(search_queries),
            proposed_keywords=_dedupe_texts(proposed_keywords),
            status="pending",
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        suggestions.append(suggestion)
        self._save_suggestions(suggestions)
        return suggestion

    def approve_suggestion(
        self,
        suggestion_id: str,
        *,
        law_name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> LawHintSuggestion:
        suggestions = self.list_suggestions()
        suggestion = next((item for item in suggestions if item.id == suggestion_id), None)
        if suggestion is None:
            raise ValueError("suggestion_not_found")

        selected_law_name = (law_name or "").strip() or (suggestion.related_law_queries[0] if suggestion.related_law_queries else "")
        selected_keywords = _dedupe_texts(keywords or suggestion.proposed_keywords)
        if not selected_law_name:
            raise ValueError("missing_law_name")
        if not selected_keywords:
            raise ValueError("missing_keywords")

        overrides = self.approved_overrides()
        overrides[selected_law_name] = _dedupe_texts(overrides.get(selected_law_name, []) + selected_keywords)
        self._write_json(self.overrides_path, overrides)

        suggestion.status = "approved"
        suggestion.updated_at = _utc_now()
        suggestion.approved_law_name = selected_law_name
        suggestion.approved_keywords = selected_keywords
        self._save_suggestions(suggestions)
        return suggestion

    def reject_suggestion(self, suggestion_id: str) -> LawHintSuggestion:
        suggestions = self.list_suggestions()
        suggestion = next((item for item in suggestions if item.id == suggestion_id), None)
        if suggestion is None:
            raise ValueError("suggestion_not_found")
        suggestion.status = "rejected"
        suggestion.updated_at = _utc_now()
        self._save_suggestions(suggestions)
        return suggestion

    def _save_suggestions(self, suggestions: List[LawHintSuggestion]) -> None:
        payload = [asdict(item) for item in suggestions]
        self._write_json(self.suggestions_path, payload)
