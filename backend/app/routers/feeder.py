"""馈线巡检接口：维护馈线，覆盖登记失效、登记超标、安排修复等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.runtime import check_page_size
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.feeder import FeederService

router = APIRouter(prefix="/api/feeder", tags=["馈线巡检"])

service = FeederService()

LIST_FIELDS = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期", "馈线状态"]
STATUSES = ["正常", "防水失效", "接地超标", "已修复"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按馈线编号检索"),
    status: str | None = Query(default=None, description="正常、防水失效、接地超标、已修复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按馈线编号与状态过滤馈线巡检列表；没有数据时返回空页，不报错。"""
    check_page_size(size)
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条馈线明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"馈线 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条馈线，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="馈线已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条馈线执行登记失效、登记超标、安排修复；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出馈线巡检清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "feeder", "total": total, "items": items}
