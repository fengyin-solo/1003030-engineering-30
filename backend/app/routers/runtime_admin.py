"""运行参数接口：读取当前生效值、基于版本号改写共享的 runtime.json。

GET  /api/runtime  当前生效值 + 版本号
PUT  /api/runtime  携带 base_version 改写；两处同时改写时先落盘的生效，
                   后到的因版本不匹配收到 409，需要重新读取后再改。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.runtime import ConflictError, runtime_store

router = APIRouter(prefix="/api/runtime", tags=["运行参数"])


class RuntimeUpdatePayload(BaseModel):
    """改写运行参数时提交的字段集合。"""

    values: dict[str, Any]
    base_version: str | None = None


@router.get("")
def get_runtime() -> dict[str, Any]:
    """读取当前生效的运行参数与版本号（版本号用于改写时的冲突校验）。"""
    return runtime_store.describe()


@router.put("")
def put_runtime(payload: RuntimeUpdatePayload) -> dict[str, Any]:
    """改写共享运行参数：先落盘者为准，版本不匹配返回 409 并说明原因。"""
    try:
        return runtime_store.update(payload.values, payload.base_version)
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"参数已被另一处先落盘（当前版本 {exc.current_version}），请重新读取后再改",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
