"""门禁管理接口：维护门禁记录，覆盖续期授权、记录闯入、修复门禁等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.runtime import check_page_size
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.dooraccess import DooraccessService

router = APIRouter(prefix="/api/dooraccess", tags=["门禁管理"])

service = DooraccessService()

LIST_FIELDS = ["门禁编号", "所属站点", "开门方式", "进出人员", "进出时间", "授权状态", "异常记录", "门禁状态"]
STATUSES = ["正常", "授权过期", "非法闯入", "已修复"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按门禁编号检索"),
    status: str | None = Query(default=None, description="正常、授权过期、非法闯入、已修复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按门禁编号与状态过滤门禁管理列表；没有数据时返回空页，不报错。"""
    check_page_size(size)
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条门禁记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"门禁记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条门禁记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="门禁记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条门禁记录执行续期授权、记录闯入、修复门禁；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出门禁管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "dooraccess", "total": total, "items": items}
