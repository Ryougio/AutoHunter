"""派发和搜集共用的队列资格。

冷却中的目标仍是 queued，但不算进可派发水位，否则 5xx 会把搜集卡住。
思路来自 1ceS1amese：https://github.com/StanleyNull/AutoHunter/issues/73
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Target


def utc_naive_now() -> datetime:
    """与库存时间一致：UTC、不带时区。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ready_queue_clause(now: datetime | None = None) -> ColumnElement[bool]:
    """冷却未到的目标不占搜集水位，也不进入本轮派发。"""
    now = now or utc_naive_now()
    return (Target.status == "queued") & (
        Target.prefilter_retry_at.is_(None) | (Target.prefilter_retry_at <= now)
    )
