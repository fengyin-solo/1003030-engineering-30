"""节能改造接口：维护节能项目，覆盖申请立项、开始改造、验收评估等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.pagination import clamp_page_size
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.energyeff import EnergyeffService

router = APIRouter(prefix="/api/energyeff", tags=["节能改造"])

service = EnergyeffService()

LIST_FIELDS = ["项目编号", "所属站点", "改造内容", "预估节电率", "投资金额", "承包单位", "投资回收期", "项目状态"]
STATUSES = ["待立项", "改造中", "评估中", "已验收"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按项目编号检索"),
    status: str | None = Query(default=None, description="待立项、改造中、评估中、已验收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按项目编号与状态过滤节能改造列表；没有数据时返回空页，不报错。"""
    size = clamp_page_size(size)
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条节能项目明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"节能项目 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条节能项目，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="节能项目已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条节能项目执行申请立项、开始改造、验收评估；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出节能改造清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "energyeff", "total": total, "items": items}
