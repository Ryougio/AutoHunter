"""停止不能把已经退出的主循环异常再抛成 500。"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.orchestrator import THREAD_EXHAUST_PAUSE_AFTER, OrchestratorManager, TaskRunner


class _OkSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_args):
        return False


class _BoomSession:
    async def __aenter__(self):
        raise RuntimeError("can't start new thread")

    async def __aexit__(self, *_args):
        return False


class StopDeadRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_swallows_finished_runner_error(self):
        mgr = OrchestratorManager()

        async def die():
            raise RuntimeError("can't start new thread")

        task = asyncio.create_task(die())
        await asyncio.wait({task})
        self.assertIsInstance(task.exception(), RuntimeError)

        mgr._tasks["tid"] = task
        await mgr.stop("tid")
        self.assertNotIn("tid", mgr._tasks)
        self.assertIsInstance(task.exception(), RuntimeError)

    async def test_thread_exhaustion_pauses_instead_of_dying(self):
        runner = TaskRunner("tid")
        ticks = {"n": 0}
        pauses = {"n": 0, "reason": ""}

        async def recover(_session):
            return None

        async def tick():
            ticks["n"] += 1
            raise RuntimeError("can't start new thread")

        async def pause(reason=""):
            pauses["n"] += 1
            pauses["reason"] = reason

        runner.recover = recover
        runner._tick = tick
        runner._pause_after_loop_exit = pause
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return _OkSession() if calls["n"] == 1 else _BoomSession()

        with patch("app.orchestrator.SessionLocal", factory), \
             patch("app.orchestrator.asyncio.sleep", new=AsyncMock()):
            await runner.run_forever()

        self.assertTrue(runner._stop.is_set())
        self.assertEqual(pauses["n"], 1)
        self.assertIn("线程", pauses["reason"])
        self.assertEqual(ticks["n"], THREAD_EXHAUST_PAUSE_AFTER)

    async def test_log_failure_does_not_kill_a_single_tick(self):
        runner = TaskRunner("tid")

        async def recover(_session):
            return None

        async def tick():
            runner._stop.set()
            raise RuntimeError("database is locked")

        runner.recover = recover
        runner._tick = tick
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return _OkSession() if calls["n"] == 1 else _BoomSession()

        with patch("app.orchestrator.SessionLocal", factory), \
             patch("app.orchestrator.asyncio.sleep", new=AsyncMock()):
            await runner.run_forever()

        self.assertTrue(runner._stop.is_set())
        self.assertGreaterEqual(calls["n"], 2)
        self.assertEqual(runner._thread_exhaust_streak, 0)


if __name__ == "__main__":
    unittest.main()
