"""运行参数接口：查看/修改前后端共用的那份 .env，改完运行中的服务自动按新值重载。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config as runtime_config
from app.config import ConfigConflictError, get_settings

router = APIRouter(prefix="/api/runtime", tags=["运行参数"])


class RuntimeConfigPayload(BaseModel):
    """修改运行参数：values 是要改的键值，base_version 是调用方上次读到的版本号。"""

    values: dict[str, str] = Field(default_factory=dict)
    base_version: str


def _effective() -> dict[str, object]:
    settings = get_settings()
    return {
        "APP_ENV": settings.env,
        "APP_PORT": settings.port,
        "APP_ALLOWED_ORIGINS": ",".join(settings.allowed_origins),
        "APP_PAGE_SIZE_MAX": settings.page_size_max,
        "APP_PAGE_SIZE_DEFAULT": settings.page_size_default,
        "VITE_PROXY_TARGET": settings.proxy_target,
    }


def _as_int(key: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} 必须是整数，当前值：{raw!r}") from exc


def _validate(values: dict[str, str]) -> None:
    unknown = sorted(set(values) - set(runtime_config.WRITABLE_KEYS))
    if unknown:
        raise ValueError(f"不支持的运行参数：{'、'.join(unknown)}")
    if "APP_PORT" in values:
        if not 1 <= _as_int("APP_PORT", values["APP_PORT"]) <= 65535:
            raise ValueError("APP_PORT 必须在 1-65535 之间")
    current = get_settings()
    merged_max = _as_int("APP_PAGE_SIZE_MAX", values.get("APP_PAGE_SIZE_MAX", str(current.page_size_max)))
    merged_default = _as_int(
        "APP_PAGE_SIZE_DEFAULT", values.get("APP_PAGE_SIZE_DEFAULT", str(current.page_size_default))
    )
    if merged_max < 1 or merged_default < 1:
        raise ValueError("页大小上限/默认值必须是正整数")
    if merged_default > merged_max:
        raise ValueError("页大小默认值不能大于上限")
    if "APP_ALLOWED_ORIGINS" in values:
        origins = [o.strip() for o in values["APP_ALLOWED_ORIGINS"].split(",") if o.strip()]
        if not origins or any(not o.startswith(("http://", "https://")) for o in origins):
            raise ValueError("APP_ALLOWED_ORIGINS 需要是逗号分隔的 http(s) 来源")
    proxy = values.get("VITE_PROXY_TARGET")
    if proxy and not proxy.startswith(("http://", "https://")):
        raise ValueError("VITE_PROXY_TARGET 需要是 http(s) 地址")


@router.get("/config")
def read_config() -> dict[str, object]:
    """读取当前生效的运行参数及版本号；版本号用于修改时的先落盘判定。"""
    return {
        "ok": True,
        "file": str(runtime_config.ENV_FILE),
        "version": runtime_config.current_config_version(),
        "effective": _effective(),
    }


@router.put("/config")
def update_config(payload: RuntimeConfigPayload) -> dict[str, object]:
    """把修改写进 .env；版本不一致说明别处已先落盘，按先落盘为准返回 409。"""
    if not payload.values:
        raise HTTPException(status_code=400, detail="没有要修改的参数")
    try:
        _validate(payload.values)
        version = runtime_config.update_env_file(payload.values, payload.base_version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "version": version,
        "message": "运行参数已落盘，运行中的前后端会按新值自动重载",
        "effective": _effective(),
    }
