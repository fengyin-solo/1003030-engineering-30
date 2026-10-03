"""通信基站运维管理平台 后端服务入口。

启动：./run.sh（端口等运行参数统一读仓库根目录 .env；老的 uvicorn 直启命令也还能用）
健康检查：GET /api/health
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings, start_config_watcher, stop_config_watcher
from app.routers import ROUTERS
from app.store import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class ReloadableCORSMiddleware:
    """跨域白名单跟随共享配置：.env 改了，下一个请求就按新白名单走，不用重启。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._origins: tuple[str, ...] | None = None
        self._inner: CORSMiddleware | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        origins = get_settings().allowed_origins
        if origins != self._origins:
            self._inner = CORSMiddleware(
                self.app,
                allow_origins=list(origins),
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            self._origins = origins
        await self._inner(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()  # 配置有问题时启动就报错，不等到第一个请求
    start_config_watcher()
    yield
    stop_config_watcher()


app = FastAPI(title="通信基站运维管理平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(ReloadableCORSMiddleware)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    settings = get_settings()
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
