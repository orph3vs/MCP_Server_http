import os
import tempfile
import unittest
from pathlib import Path

from src.cost_logger import CostLogEntry, CostLogger
from src.multi_agent_review import MultiAgentReviewPipeline, RequestMetrics


class CostLoggerTests(unittest.TestCase):
    def test_log_and_get_by_request_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cost_logs.db"
            logger = CostLogger(db_path=str(db_path))
            entry = CostLogEntry(
                request_id="req-1",
                risk_level="HIGH",
                mode="multi_agent",
                tokens_in=120,
                tokens_out=80,
                cost=0.0123,
                latency=210.5,
                score=87.5,
                question_summary="개인정보 제재 기준 질문",
                question_intent="illegality",
                nlic_calls=4,
                law_search_count=2,
                has_precedent=True,
            )
            logger.log_request(entry)

            loaded = logger.get_by_request_id("req-1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.request_id, "req-1")
            self.assertEqual(loaded.risk_level, "HIGH")
            self.assertEqual(loaded.question_summary, "개인정보 제재 기준 질문")
            self.assertEqual(loaded.question_intent, "illegality")
            self.assertEqual(loaded.nlic_calls, 4)
            self.assertTrue(loaded.has_precedent)

    def test_pipeline_run_with_logging(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cost_logs.db"
            logger = CostLogger(db_path=str(db_path))
            pipeline = MultiAgentReviewPipeline()

            pipeline.run_with_logging(
                question="개인정보 위법성과 감독기관 조사 대응 검토",
                context="기준시점: 2025-01-01",
                request_id="req-2",
                metrics=RequestMetrics(
                    risk_level="HIGH",
                    mode="parallel_review",
                    tokens_in=50,
                    tokens_out=60,
                    cost=0.01,
                    score=90.0,
                ),
                cost_logger=logger,
            )

            loaded = logger.get_by_request_id("req-2")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.mode, "parallel_review")
            self.assertEqual(loaded.tokens_in, 50)
            self.assertGreaterEqual(loaded.latency, 0)

    def test_summarize_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cost_logs.db"
            logger = CostLogger(db_path=str(db_path))
            logger.log_request(
                CostLogEntry(
                    request_id="req-a",
                    risk_level="LOW",
                    mode="single_agent",
                    tokens_in=10,
                    tokens_out=20,
                    cost=0.001,
                    latency=30.0,
                    score=80.0,
                    nlic_calls=2,
                )
            )
            logger.log_request(
                CostLogEntry(
                    request_id="req-b",
                    risk_level="HIGH",
                    mode="multi_agent",
                    tokens_in=20,
                    tokens_out=30,
                    cost=0.002,
                    latency=60.0,
                    score=90.0,
                    nlic_calls=5,
                    precedent_search_count=1,
                    error_stage="LawAPI",
                )
            )

            summary = logger.summarize_recent(limit=10)

            self.assertEqual(summary["count"], 2)
            self.assertEqual(summary["multi_agent_count"], 1)
            self.assertEqual(summary["high_risk_count"], 1)
            self.assertEqual(summary["error_count"], 1)
            self.assertEqual(summary["precedent_request_count"], 1)

    def test_summarize_all_is_not_affected_by_pagination(self):
        fd, raw_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db_path = Path(raw_path)
            logger = CostLogger(db_path=str(db_path))
            for idx in range(3):
                logger.log_request(
                    CostLogEntry(
                        request_id=f"req-{idx}",
                        risk_level="LOW",
                        mode="single_agent",
                        tokens_in=0,
                        tokens_out=0,
                        cost=0.001 * (idx + 1),
                        latency=10.0 * (idx + 1),
                        score=80.0,
                        question_summary=f"질문 {idx}",
                        question_intent="explain",
                    )
                )

            paged = logger.summarize_recent(limit=2, offset=1)
            full = logger.summarize_all()

            self.assertEqual(paged["count"], 2)
            self.assertEqual(full["count"], 3)
            self.assertAlmostEqual(full["total_cost"], 0.006, places=6)
        finally:
            pass


if __name__ == "__main__":
    unittest.main()
