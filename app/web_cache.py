"""前端静态缓存。

Vite 产物文件名带内容哈希，可以长期缓存。
index.html 只是入口，必须每次向服务器核对，否则发版后浏览器还拿旧脚本名。
"""
from __future__ import annotations

from starlette.staticfiles import StaticFiles

# 一年。文件名变了就是新资源，旧 URL 不会再被引用。
ASSET_CACHE = "public, max-age=31536000, immutable"
# 允许存一份，但每次使用前都要向服务器确认还是不是这份。
HTML_CACHE = "no-cache"


class HashedAssetFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if getattr(response, "status_code", 0) == 200:
            response.headers["Cache-Control"] = ASSET_CACHE
        return response
