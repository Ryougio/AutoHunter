"""5xx 冷却目标不占搜集水位，连续失败有上限。Issue #73。"""
from __future__ import annotations

import unittest
from datetime import timedelta
from types import SimpleNamespace

from app.orchestrator import (
    QUEUE_TRANSIENT_PREFILTER_MAX_FAILURES,
    TaskRunner,
)
from app.queue_policy import ready_queue_clause, utc_naive_now


class QueueCoolingTests(unittest.TestCase):
    def test_ready_clause_ignores_future_cooldown(self):
        clause = ready_queue_clause(utc_naive_now())
        sql = str(clause.compile(compile_kwargs={"literal_binds": False}))
        self.assertIn("prefilter_retry_at", sql)
        self.assertIn("status", sql)

    def test_defer_then_exhaust_without_marking_no_vuln(self):
        target = SimpleNamespace(
            prefilter_fail_count=0,
            assigned_worker="w",
            heartbeat_at=object(),
            last_error="",
            status="queued",
            verdict="",
            dead_reason="old",
            prefilter_retry_at=None,
        )
        self.assertTrue(TaskRunner._defer_transient_prefilter(target, "服务异常(502)"))
        self.assertEqual(target.status, "queued")
        self.assertEqual(target.verdict, "")
        self.assertIsNotNone(target.prefilter_retry_at)
        self.assertGreater(target.prefilter_retry_at, utc_naive_now())

        target.prefilter_fail_count = QUEUE_TRANSIENT_PREFILTER_MAX_FAILURES - 1
        target.prefilter_retry_at = utc_naive_now() - timedelta(seconds=1)
        self.assertFalse(TaskRunner._defer_transient_prefilter(target, "服务异常(502)"))
        self.assertEqual(target.status, "dead")
        self.assertEqual(target.verdict, "prefilter_retry_exhausted")
        self.assertNotEqual(target.verdict, "no_vuln")
        self.assertIn("未完成漏洞检测", target.dead_reason)
        self.assertIsNone(target.prefilter_retry_at)


if __name__ == "__main__":
    unittest.main()
