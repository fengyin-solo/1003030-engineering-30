"""通信基站运维管理平台 后端服务入口。

启动：./run.sh（等价于 python -m app.serve，监听地址以仓库根 runtime.json 为准）
老的启动命令仍然可用：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import settings
from app.cors import RuntimeCORSMiddleware
from app.routers import ROUTERS
from app.routers.runtime_admin import router as runtime_router
from app.runtime import runtime_store
from app.store import store

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

logger = logging.getLogger("app.main")

app = FastAPI(title="通信基站运维管理平台", version="1.0.0")

app.add_middleware(RuntimeCORSMiddleware)

for module in ROUTERS:
    app.include_router(module.router)

app.include_router(runtime_router)

logger.info("运行参数已生效 %s", runtime_store.describe())


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {
        "ok": True,
        "app": settings.app_name,
        "modules": len(store.module_names()),
        "config_version": settings.config_version,
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
