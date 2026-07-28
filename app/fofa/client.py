"""FOFA 官方 API 客户端（移植自项目已有 fofa-team 逻辑）。"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

BASE = "https://fofa.info"
logger = logging.getLogger("autohunter.fofa")

# host -> 是否已因证书问题降级为不校验（进程内记忆）
_INSECURE_TLS_HOSTS: set[str] = set()
_TLS_MARKERS = (
    "certificate verify failed",
    "certificate_verify_failed",
    "self signed certificate",
    "self-signed certificate",
    "sslcertverificationerror",
    "ssl: certificate",
    "unable to get local issuer",
    "cert already expired",
    "certificate has expired",
    "expired certificate",
)


class FofaError(Exception):
    """FOFA 调用错误。account_error=True 表示账号级致命错误（key 无效/过期/无 F 点/
    权限不足等），这类错误重试也没用，上层应据此累计并在连续多次后暂停任务。"""

    def __init__(self, message: str, account_error: bool = False):
        super().__init__(message)
        self.account_error = account_error


# FOFA 账号级致命错误特征（errmsg 命中即视为账号无效，重试无意义）。
_FOFA_ACCOUNT_ERROR_MARKERS = (
    "820000", "820001", "-700", "账号无效", "账号已过期", "账号过期",
    "无效的fofa", "无效的 fofa", "f点不足", "f币不足", "余额不足", "配额",
    "权限不足", "没有权限", "会员", "account invalid", "invalid key",
    "expired", "insufficient", "quota", "permission", "unauthorized", "forbidden",
)


def _is_account_error(errmsg: str) -> bool:
    text = str(errmsg or "").lower()
    return any(m in text for m in _FOFA_ACCOUNT_ERROR_MARKERS)


def _qbase64(query: str) -> str:
    return base64.b64encode(query.encode("utf-8")).decode("ascii")


def _host_of(base: str) -> str:
    try:
        return (urlsplit(base).hostname or base).strip().lower()
    except Exception:
        return str(base or "").strip().lower()


def _is_https(base: str) -> bool:
    return str(base or "").lower().startswith("https://")


def _global_insecure_tls() -> bool:
    return os.environ.get("FOFA_INSECURE_TLS", "").strip().lower() in ("1", "true", "yes", "on")


def _is_tls_error(exc: BaseException) -> bool:
    parts = [str(exc)]
    cur: BaseException | None = exc
    seen = 0
    while cur is not None and seen < 6:
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
        seen += 1
    text = " ".join(parts).lower()
    return any(m in text for m in _TLS_MARKERS)


async def _fofa_get_json(url: str, params: dict[str, str], base: str) -> Any:
    """GET FOFA API；https 证书失败时自动 verify=False 重试一次。"""
    host = _host_of(base)
    force_insecure = _global_insecure_tls() or host in _INSECURE_TLS_HOSTS
    verify = not force_insecure

    async def _once(v: bool):
        async with httpx.AsyncClient(timeout=30, verify=v) as client:
            resp = await client.get(url, params=params)
            try:
                return resp.json()
            except Exception:
                raise FofaError(f"FOFA 返回非 JSON (HTTP {resp.status_code}): {resp.text[:200]}")

    try:
        return await _once(verify)
    except FofaError:
        raise
    except httpx.HTTPError as e:
        if verify and _is_https(base) and _is_tls_error(e):
            _INSECURE_TLS_HOSTS.add(host)
            logger.warning(
                "FOFA HTTPS 证书校验失败(%s)，已自动降级为不校验证书重试（过期/自签/私有镜像常见）",
                host or base,
            )
            try:
                return await _once(False)
            except FofaError:
                raise
            except httpx.HTTPError as e2:
                raise FofaError(f"FOFA 请求失败: {type(e2).__name__}: {e2}") from e2
        # 网络抖动/超时/连接失败等统一包装成 FofaError，避免裸 httpx 异常
        # 一路冒到 orchestrator 主循环（外部 API 不可用是常态，应降级而非告警）。
        raise FofaError(f"FOFA 请求失败: {type(e).__name__}: {e}") from e


async def search(key: str, query: str, page: int = 1, size: int = 100,
                 fields: str = "host,ip,port,title,domain,org",
                 base_url: str | None = None) -> dict[str, Any]:
    """调用 FOFA search/all，返回 {results: [...], size, page}。

    base_url 留空则用官方 https://fofa.info；可传入私有部署/镜像/代理网关地址。
    不再做本地白名单拦截，内网 FOFA 可直接使用。
    http:// 与 https:// 均支持；https 证书过期/自签时自动降级 verify=False。
    """
    if not key:
        raise FofaError("缺少 FOFA key")
    base = (base_url or BASE).rstrip("/")
    params = {
        "key": key, "qbase64": _qbase64(query),
        "fields": fields, "page": str(page), "size": str(size), "full": "false",
    }
    data = await _fofa_get_json(f"{base}/api/v1/search/all", params, base)
    if data.get("error"):
        errmsg = data.get("errmsg")
        raise FofaError(f"FOFA 错误: {errmsg}", account_error=_is_account_error(errmsg))
    return {
        "fields": fields.split(","),
        "results": data.get("results", []),
        "size": data.get("size", 0),
        "page": page,
    }
