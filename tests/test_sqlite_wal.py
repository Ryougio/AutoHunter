"""SQLite WAL 截断：模式白名单，以及 checkpoint 能在临时库上跑完。"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import app.db.session as session


class SqliteWalTests(unittest.TestCase):
    def test_journal_size_limit_is_configured(self):
        self.assertTrue(any("journal_size_limit=268435456" in item for item in session._CONNECT_PRAGMAS))
        self.assertTrue(any("busy_timeout=5000" in item for item in session._CONNECT_PRAGMAS))

    def test_checkpoint_mode_is_whitelisted(self):
        with self.assertRaises(ValueError):
            asyncio.run(session.checkpoint_wal("TRUNCATE; DROP TABLE x"))

    def test_checkpoint_truncate_on_temp_db(self):
        async def _run(path: str):
            import aiosqlite

            old = session.DB_PATH
            session.DB_PATH = path
            try:
                conn = await aiosqlite.connect(path)
                await conn.execute("CREATE TABLE t (id INTEGER)")
                await conn.commit()
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("INSERT INTO t VALUES (1)")
                await conn.commit()
                await conn.close()
                return await session.checkpoint_wal("TRUNCATE")
            finally:
                session.DB_PATH = old

        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(_run(str(Path(tmp) / "autohunter.db")))
        self.assertIsNotNone(result)
        self.assertEqual(result["busy"], 0)
        self.assertIn("checkpointed", result)


if __name__ == "__main__":
    unittest.main()
