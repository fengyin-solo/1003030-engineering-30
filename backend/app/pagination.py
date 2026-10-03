"""分页校验：页大小上限只认共享运行配置（仓库根目录 .env）里的那一份。"""
from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def clamp_page_size(size: int) -> int:
    """页大小超过上限时拒绝并说明当前上限；上限改配置后无需重启即可生效。"""
    limit = get_settings().page_size_max
    if size > limit:
        raise HTTPException(status_code=400, detail=f"每页最多 {limit} 条，请缩小分页范围")
    return size
