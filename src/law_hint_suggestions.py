"""Suggestion storage for law-hint diagnostics and typed runtime overrides."""

from __future__ import annotations

import json
import hashlib
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    suggestion_type: str = "law_search_gap"
    reason_code: Optional[str] = None
    question_law_family: Optional[str] = None
    question_scope_direct_basis_found: Optional[bool] = None
    question_scope_article_no: Optional[str] = None
    supplementary_law_name: Optional[str] = None
    supplementary_article_no: Optional[str] = None
    matched_clause_labels: Optional[List[str]] = None
    recommended_change_type: Optional[str] = None
    recommended_change_payload: Optional[Dict[str, Any]] = None
    runtime_safe: bool = False
    approval_effect: Optional[str] = None
    approved_law_name: Optional[str] = None
    approved_keywords: Optional[List[str]] = None
    approved_rule_id: Optional[str] = None
    approved_rule_type: Optional[str] = None


@dataclass
class LawHintOverrideRule:
    id: str
    rule_type: str
    status: str
    source_suggestion_id: Optional[str]
    name: str
    conditions: Dict[str, Any]
    action: Dict[str, Any]
    created_at: str
    updated_at: str


class LawHintSuggestionStore:
    """Persists diagnostic suggestions and typed runtime override rules."""

    def __init__(
        self,
        suggestions_path: str = "data/law_hint_suggestions.json",
        overrides_path: str = "data/law_hint_overrides.json",
        rules_path: str = "data/law_hint_override_rules.json",
    ) -> None:
        self.suggestions_path = Path(suggestions_path)
        self.overrides_path = Path(overrides_path)
        self.rules_path = Path(rules_path)
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)

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
        status_order = {"pending": 0, "approved": 1, "rejected": 2}
        suggestions = sorted(suggestions, key=lambda item: item.updated_at, reverse=True)
        suggestions = sorted(suggestions, key=lambda item: item.occurrence_count, reverse=True)
        suggestions = sorted(suggestions, key=lambda item: status_order.get(item.status, 99))
        return suggestions

    def approved_overrides(self) -> Dict[str, List[str]]:
        """Legacy keyword override format kept for backward-compatibility only."""
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

    def list_override_rules(self, status: Optional[str] = None) -> List[LawHintOverrideRule]:
        raw_items = self._load_json(self.rules_path, [])
        rules = [LawHintOverrideRule(**item) for item in raw_items]
        if status:
            rules = [item for item in rules if item.status == status]
        return sorted(rules, key=lambda item: item.updated_at, reverse=True)

    def active_override_rules(self) -> List[LawHintOverrideRule]:
        return self.list_override_rules(status="active")

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
        suggestion_type: str = "law_search_gap",
        reason_code: Optional[str] = None,
        question_law_family: Optional[str] = None,
        question_scope_direct_basis_found: Optional[bool] = None,
        question_scope_article_no: Optional[str] = None,
        supplementary_law_name: Optional[str] = None,
        supplementary_article_no: Optional[str] = None,
        matched_clause_labels: Optional[List[str]] = None,
        recommended_change_type: Optional[str] = None,
        recommended_change_payload: Optional[Dict[str, Any]] = None,
        runtime_safe: bool = False,
        approval_effect: Optional[str] = None,
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
            suggestion.suggestion_type = (suggestion_type or "law_search_gap").strip() or "law_search_gap"
            suggestion.reason_code = str(reason_code).strip() if reason_code else None
            suggestion.question_law_family = str(question_law_family).strip() if question_law_family else None
            suggestion.question_scope_direct_basis_found = question_scope_direct_basis_found
            suggestion.question_scope_article_no = (
                str(question_scope_article_no).strip() if question_scope_article_no else None
            )
            suggestion.supplementary_law_name = (
                str(supplementary_law_name).strip() if supplementary_law_name else None
            )
            suggestion.supplementary_article_no = (
                str(supplementary_article_no).strip() if supplementary_article_no else None
            )
            suggestion.matched_clause_labels = (
                _dedupe_texts([str(label) for label in (matched_clause_labels or [])]) or None
            )
            suggestion.recommended_change_type = (
                str(recommended_change_type).strip() if recommended_change_type else None
            )
            suggestion.recommended_change_payload = dict(recommended_change_payload or {}) or None
            suggestion.runtime_safe = bool(runtime_safe)
            suggestion.approval_effect = str(approval_effect).strip() if approval_effect else None
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
            suggestion_type=(suggestion_type or "law_search_gap").strip() or "law_search_gap",
            reason_code=str(reason_code).strip() if reason_code else None,
            question_law_family=str(question_law_family).strip() if question_law_family else None,
            question_scope_direct_basis_found=question_scope_direct_basis_found,
            question_scope_article_no=str(question_scope_article_no).strip() if question_scope_article_no else None,
            supplementary_law_name=str(supplementary_law_name).strip() if supplementary_law_name else None,
            supplementary_article_no=str(supplementary_article_no).strip() if supplementary_article_no else None,
            matched_clause_labels=_dedupe_texts([str(label) for label in (matched_clause_labels or [])]) or None,
            recommended_change_type=str(recommended_change_type).strip() if recommended_change_type else None,
            recommended_change_payload=dict(recommended_change_payload or {}) or None,
            runtime_safe=bool(runtime_safe),
            approval_effect=str(approval_effect).strip() if approval_effect else None,
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

        suggestion.status = "approved"
        suggestion.updated_at = _utc_now()
        runtime_rule = self._create_override_rule_from_suggestion(
            suggestion,
            law_name=law_name,
            keywords=keywords,
        )
        if runtime_rule is not None:
            suggestion.approved_law_name = str(runtime_rule.action.get("law_name") or "").strip() or None
            suggestion.approved_keywords = _dedupe_texts(keywords or suggestion.proposed_keywords) or None
            suggestion.approved_rule_id = runtime_rule.id
            suggestion.approved_rule_type = runtime_rule.rule_type
            suggestion.approval_effect = (
                f"runtime rule applied: {runtime_rule.rule_type}"
            )
        elif not suggestion.approval_effect:
            suggestion.approval_effect = "operator review recorded; no runtime override created"
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

    def create_override_rule(
        self,
        *,
        rule_type: str,
        name: str,
        conditions: Dict[str, Any],
        action: Dict[str, Any],
        source_suggestion_id: Optional[str] = None,
    ) -> LawHintOverrideRule:
        rules = self.list_override_rules()
        now = _utc_now()
        normalized_name = str(name or "").strip() or rule_type
        normalized_conditions = dict(conditions or {})
        normalized_action = dict(action or {})

        for rule in rules:
            if (
                rule.rule_type == rule_type
                and rule.conditions == normalized_conditions
                and rule.action == normalized_action
            ):
                rule.status = "active"
                rule.name = normalized_name
                rule.source_suggestion_id = source_suggestion_id or rule.source_suggestion_id
                rule.updated_at = now
                self._save_override_rules(rules)
                return rule

        rule = LawHintOverrideRule(
            id=str(uuid.uuid4()),
            rule_type=rule_type,
            status="active",
            source_suggestion_id=source_suggestion_id,
            name=normalized_name,
            conditions=normalized_conditions,
            action=normalized_action,
            created_at=now,
            updated_at=now,
        )
        rules.append(rule)
        self._save_override_rules(rules)
        return rule

    def _create_override_rule_from_suggestion(
        self,
        suggestion: LawHintSuggestion,
        *,
        law_name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Optional[LawHintOverrideRule]:
        if not suggestion.runtime_safe:
            return None

        change_type = (suggestion.recommended_change_type or "").strip()
        payload = dict(suggestion.recommended_change_payload or {})
        selected_law_name = (
            (law_name or "").strip()
            or str(payload.get("law_name") or "").strip()
            or (suggestion.supplementary_law_name or "").strip()
            or (suggestion.related_law_queries[0] if suggestion.related_law_queries else "")
        )
        selected_keywords = _dedupe_texts(keywords or payload.get("trigger_phrases") or suggestion.proposed_keywords)

        if change_type == "alias_normalization":
            if not selected_law_name or not selected_keywords:
                return None
            return self.create_override_rule(
                rule_type="alias_normalization",
                name=f"Alias -> {selected_law_name}",
                source_suggestion_id=suggestion.id,
                conditions={"trigger_phrases": selected_keywords},
                action={"law_name": selected_law_name},
            )

        if change_type == "law_family_priority":
            if not selected_law_name:
                return None
            trigger_phrases = selected_keywords or _dedupe_texts([suggestion.question_law_family or ""])
            if not trigger_phrases:
                return None
            return self.create_override_rule(
                rule_type="law_family_priority",
                name=f"Law family priority -> {selected_law_name}",
                source_suggestion_id=suggestion.id,
                conditions={
                    "trigger_phrases": trigger_phrases,
                    "question_intent": suggestion.question_intent,
                    "issue_terms": suggestion.issue_terms,
                },
                action={"law_name": selected_law_name},
            )

        return None

    def _save_suggestions(self, suggestions: List[LawHintSuggestion]) -> None:
        payload = [asdict(item) for item in suggestions]
        self._write_json(self.suggestions_path, payload)

    def _save_override_rules(self, rules: List[LawHintOverrideRule]) -> None:
        payload = [asdict(item) for item in rules]
        self._write_json(self.rules_path, payload)
