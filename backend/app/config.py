"""运行配置：端口、跨域白名单、页大小上限等运行参数。

唯一需要维护的一份在仓库根的 runtime.json；本模块把它整理成 Settings 暴露。
`settings` 是实时视图：属性在访问时读取当前生效值，runtime.json 变更后
不需要重启进程即可生效（监听端口由 app.serve 侦测变更并自动重启监听）。

老的环境变量（APP_ENV、APP_PORT、APP_CORS_ORIGINS、APP_PAGE_SIZE_MAX 等）
仍然生效，优先级高于 runtime.json。
"""
from __future__ import annotations

from typing import Any

from app.runtime import Settings, runtime_store

__all__ = ["Settings", "settings", "runtime_store"]


class _LiveSettings:
    """Settings 的实时代理：每次访问属性都取当前生效值。"""

    def __getattr__(self, name: str) -> Any:
        return getattr(runtime_store.get(), name)

    def __repr__(self) -> str:
        return repr(runtime_store.get())


settings = _LiveSettings()
