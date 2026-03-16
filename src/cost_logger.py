"""SQLite-based request cost logger."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass(frozen=True)
class CostLogEntry:
    request_id: str
    risk_level: str
    mode: str
    tokens_in: int
    tokens_out: int
    cost: float
    latency: float
    score: float
    question_intent: str = "explain"
    error_stage: Optional[str] = None
    tool_calls: int = 0
    nlic_calls: int = 0
    law_search_count: int = 0
    version_fetch_count: int = 0
    article_fetch_count: int = 0
    related_article_count: int = 0
    related_law_count: int = 0
    precedent_search_count: int = 0
    precedent_fetch_count: int = 0
    has_precedent: bool = False
    has_related_laws: bool = False


class CostLogger:
    """Persists cost logs for all requests into SQLite."""

    def __init__(self, db_path: str = "data/cost_logs.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Provide a connection that is always closed.

        Note: sqlite3 connection context manager commits/rolls back transactions,
        but does not guarantee connection close on all runtimes.
        """
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS request_cost_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    tokens_in INTEGER NOT NULL,
                    tokens_out INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    latency REAL NOT NULL,
                    score REAL NOT NULL,
                    question_intent TEXT NOT NULL DEFAULT 'explain',
                    error_stage TEXT,
                    tool_calls INTEGER NOT NULL DEFAULT 0,
                    nlic_calls INTEGER NOT NULL DEFAULT 0,
                    law_search_count INTEGER NOT NULL DEFAULT 0,
                    version_fetch_count INTEGER NOT NULL DEFAULT 0,
                    article_fetch_count INTEGER NOT NULL DEFAULT 0,
                    related_article_count INTEGER NOT NULL DEFAULT 0,
                    related_law_count INTEGER NOT NULL DEFAULT 0,
                    precedent_search_count INTEGER NOT NULL DEFAULT 0,
                    precedent_fetch_count INTEGER NOT NULL DEFAULT 0,
                    has_precedent INTEGER NOT NULL DEFAULT 0,
                    has_related_laws INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._migrate_schema(conn)
            conn.commit()

    @staticmethod
    def _column_defs() -> dict[str, str]:
        return {
            "question_intent": "TEXT NOT NULL DEFAULT 'explain'",
            "error_stage": "TEXT",
            "tool_calls": "INTEGER NOT NULL DEFAULT 0",
            "nlic_calls": "INTEGER NOT NULL DEFAULT 0",
            "law_search_count": "INTEGER NOT NULL DEFAULT 0",
            "version_fetch_count": "INTEGER NOT NULL DEFAULT 0",
            "article_fetch_count": "INTEGER NOT NULL DEFAULT 0",
            "related_article_count": "INTEGER NOT NULL DEFAULT 0",
            "related_law_count": "INTEGER NOT NULL DEFAULT 0",
            "precedent_search_count": "INTEGER NOT NULL DEFAULT 0",
            "precedent_fetch_count": "INTEGER NOT NULL DEFAULT 0",
            "has_precedent": "INTEGER NOT NULL DEFAULT 0",
            "has_related_laws": "INTEGER NOT NULL DEFAULT 0",
        }

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(request_cost_logs)").fetchall()
        }
        for column_name, column_def in self._column_defs().items():
            if column_name not in existing:
                conn.execute(
                    f"ALTER TABLE request_cost_logs ADD COLUMN {column_name} {column_def}"
                )

    def log_request(self, entry: CostLogEntry) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO request_cost_logs (
                    request_id, risk_level, mode, tokens_in, tokens_out, cost, latency, score,
                    question_intent, error_stage, tool_calls, nlic_calls, law_search_count,
                    version_fetch_count, article_fetch_count, related_article_count, related_law_count,
                    precedent_search_count, precedent_fetch_count, has_precedent, has_related_laws
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.request_id,
                    entry.risk_level,
                    entry.mode,
                    entry.tokens_in,
                    entry.tokens_out,
                    entry.cost,
                    entry.latency,
                    entry.score,
                    entry.question_intent,
                    entry.error_stage,
                    entry.tool_calls,
                    entry.nlic_calls,
                    entry.law_search_count,
                    entry.version_fetch_count,
                    entry.article_fetch_count,
                    entry.related_article_count,
                    entry.related_law_count,
                    entry.precedent_search_count,
                    entry.precedent_fetch_count,
                    int(entry.has_precedent),
                    int(entry.has_related_laws),
                ),
            )
            conn.commit()

    def list_recent(self, limit: int = 50) -> List[CostLogEntry]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    request_id, risk_level, mode, tokens_in, tokens_out, cost, latency, score,
                    question_intent, error_stage, tool_calls, nlic_calls, law_search_count,
                    version_fetch_count, article_fetch_count, related_article_count, related_law_count,
                    precedent_search_count, precedent_fetch_count, has_precedent, has_related_laws
                FROM request_cost_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            CostLogEntry(
                request_id=row[0],
                risk_level=row[1],
                mode=row[2],
                tokens_in=row[3],
                tokens_out=row[4],
                cost=row[5],
                latency=row[6],
                score=row[7],
                question_intent=row[8],
                error_stage=row[9],
                tool_calls=row[10],
                nlic_calls=row[11],
                law_search_count=row[12],
                version_fetch_count=row[13],
                article_fetch_count=row[14],
                related_article_count=row[15],
                related_law_count=row[16],
                precedent_search_count=row[17],
                precedent_fetch_count=row[18],
                has_precedent=bool(row[19]),
                has_related_laws=bool(row[20]),
            )
            for row in rows
        ]

    def get_by_request_id(self, request_id: str) -> Optional[CostLogEntry]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    request_id, risk_level, mode, tokens_in, tokens_out, cost, latency, score,
                    question_intent, error_stage, tool_calls, nlic_calls, law_search_count,
                    version_fetch_count, article_fetch_count, related_article_count, related_law_count,
                    precedent_search_count, precedent_fetch_count, has_precedent, has_related_laws
                FROM request_cost_logs
                WHERE request_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (request_id,),
            ).fetchone()

        if row is None:
            return None

        return CostLogEntry(
            request_id=row[0],
            risk_level=row[1],
            mode=row[2],
            tokens_in=row[3],
            tokens_out=row[4],
            cost=row[5],
            latency=row[6],
            score=row[7],
            question_intent=row[8],
            error_stage=row[9],
            tool_calls=row[10],
            nlic_calls=row[11],
            law_search_count=row[12],
            version_fetch_count=row[13],
            article_fetch_count=row[14],
            related_article_count=row[15],
            related_law_count=row[16],
            precedent_search_count=row[17],
            precedent_fetch_count=row[18],
            has_precedent=bool(row[19]),
            has_related_laws=bool(row[20]),
        )

    def summarize_recent(self, limit: int = 50) -> dict[str, float | int]:
        rows = self.list_recent(limit=limit)
        if not rows:
            return {
                "count": 0,
                "total_cost": 0.0,
                "avg_cost": 0.0,
                "avg_latency": 0.0,
                "avg_nlic_calls": 0.0,
                "multi_agent_count": 0,
                "high_risk_count": 0,
                "error_count": 0,
                "precedent_request_count": 0,
            }

        count = len(rows)
        total_cost = round(sum(row.cost for row in rows), 6)
        return {
            "count": count,
            "total_cost": total_cost,
            "avg_cost": round(total_cost / count, 6),
            "avg_latency": round(sum(row.latency for row in rows) / count, 3),
            "avg_nlic_calls": round(sum(row.nlic_calls for row in rows) / count, 3),
            "multi_agent_count": sum(1 for row in rows if row.mode == "multi_agent"),
            "high_risk_count": sum(1 for row in rows if row.risk_level == "HIGH"),
            "error_count": sum(1 for row in rows if row.error_stage),
            "precedent_request_count": sum(1 for row in rows if row.precedent_search_count > 0),
        }
