"""哈希静态资源长期缓存，缺失文件不缓存。"""
from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web_cache import ASSET_CACHE, HashedAssetFiles


def _client(tmp_path: Path) -> TestClient:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text("console.log(1)\n", encoding="utf-8")
    app = FastAPI()
    app.mount("/assets", HashedAssetFiles(directory=str(assets)), name="assets")
    return TestClient(app)


class WebCacheTests(unittest.TestCase):
    def test_hashed_asset_is_immutable(self):
        with tempfile.TemporaryDirectory() as raw:
            res = _client(Path(raw)).get("/assets/index-abc123.js")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["cache-control"], ASSET_CACHE)
        self.assertIn("console.log", res.text)

    def test_missing_asset_is_not_cached_as_immutable(self):
        with tempfile.TemporaryDirectory() as raw:
            res = _client(Path(raw)).get("/assets/missing.js")
        self.assertEqual(res.status_code, 404)
        self.assertNotEqual(res.headers.get("cache-control"), ASSET_CACHE)


if __name__ == "__main__":
    unittest.main()
