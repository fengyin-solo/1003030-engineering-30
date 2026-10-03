"""开关电源接口：维护开关电源，覆盖记录缺失、记录异常、安排更换等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.runtime import check_page_size
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.rectifier import RectifierService

router = APIRouter(prefix="/api/rectifier", tags=["开关电源"])

service = RectifierService()

LIST_FIELDS = ["电源编号", "额定功率", "所属站点", "整流模块数", "负载率", "输出电压", "模块故障", "电源状态"]
STATUSES = ["正常", "模块缺失", "输出异常", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按电源编号检索"),
    status: str | None = Query(default=None, description="正常、模块缺失、输出异常、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按电源编号与状态过滤开关电源列表；没有数据时返回空页，不报错。"""
    check_page_size(size)
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条开关电源明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"开关电源 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条开关电源，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="开关电源已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条开关电源执行记录缺失、记录异常、安排更换；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出开关电源清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "rectifier", "total": total, "items": items}
