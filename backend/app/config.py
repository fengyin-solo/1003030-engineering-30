"""运行配置：端口、跨域白名单、页大小上限，全部只维护仓库根目录 .env 这一份。

读取优先级（后者覆盖前者）：内置默认值 < .env < .env.local < 进程环境变量，
所以老的 APP_ENV、VITE_PROXY_TARGET 等环境变量写法继续有效。

- 热重载：.env 的 mtime 一变，下一次 get_settings() 就按新值返回，并追加一条
  变更日志；日志只追加不回改，历史日志保留当时的值。
- 并发写：update_env_file 先拿排他文件锁再比对内容版本，两处同时改时先落盘的
  那份生效，后到的抛 ConfigConflictError。
- 端口变更：进程内没法换绑监听端口，watcher 检测到端口变化后按约定退出码退出，
  由 run.sh 按新端口重新拉起。
"""
from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("runtime_config")

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
ENV_LOCAL_FILE = REPO_ROOT / ".env.local"
ENV_LOCK_FILE = REPO_ROOT / ".env.lock"

# 端口变更后进程以这个退出码退出，run.sh 认得它并按新配置重启
RESTART_EXIT_CODE = 75

# 受管运行参数的兜底默认值（.env 缺失时兜底，正常部署以 .env 为准）
DEFAULTS: dict[str, str] = {
    "APP_ENV": "local",
    "APP_PORT": "8000",
    "APP_ALLOWED_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
    "APP_PAGE_SIZE_MAX": "200",
    "APP_PAGE_SIZE_DEFAULT": "20",
}

# 允许通过接口改写的 key；VITE_PROXY_TARGET 不填时前端按 APP_PORT 推导
WRITABLE_KEYS: tuple[str, ...] = tuple(DEFAULTS) + ("VITE_PROXY_TARGET",)


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            raw = raw[1:-1]
        if key:
            values[key] = raw
    return values


def _read_env_file(path: Path) -> dict[str, str]:
    try:
        return _parse_env_text(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_env_values() -> dict[str, str]:
    """按优先级合并出当前生效的键值：默认值 < .env < .env.local < 进程环境变量。"""
    values = dict(DEFAULTS)
    for path in (ENV_FILE, ENV_LOCAL_FILE):
        values.update(_read_env_file(path))
    for key in WRITABLE_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


@dataclass(frozen=True)
class Settings:
    app_name: str
    env: str
    host: str
    port: int
    allowed_origins: tuple[str, ...]
    page_size_default: int
    page_size_max: int
    proxy_target: str
    config_version: str


def _build_settings(values: dict[str, str]) -> Settings:
    try:
        port = int(values["APP_PORT"])
        page_size_max = int(values["APP_PAGE_SIZE_MAX"])
        page_size_default = int(values["APP_PAGE_SIZE_DEFAULT"])
    except ValueError as exc:
        raise ValueError(f".env 里的端口号/页大小必须是整数：{exc}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f".env 里 APP_PORT={port} 不在 1-65535 范围内")
    if page_size_max < 1 or page_size_default < 1:
        raise ValueError(".env 里页大小上限/默认值必须是正整数")
    if page_size_default > page_size_max:
        raise ValueError(".env 里页大小默认值不能大于上限")
    origins = tuple(o.strip() for o in values["APP_ALLOWED_ORIGINS"].split(",") if o.strip())
    if not origins:
        raise ValueError(".env 里 APP_ALLOWED_ORIGINS 至少要有一个来源")
    proxy_target = values.get("VITE_PROXY_TARGET") or f"http://127.0.0.1:{port}"
    return Settings(
        app_name="通信基站运维管理平台",
        env=values["APP_ENV"],
        host="127.0.0.1",
        port=port,
        allowed_origins=origins,
        page_size_default=page_size_default,
        page_size_max=page_size_max,
        proxy_target=proxy_target,
        config_version=current_config_version(),
    )


_cache_lock = threading.Lock()
_cached_settings: Settings | None = None
_cached_stamp: tuple[int | None, int | None] | None = None


def _env_stamp() -> tuple[int | None, int | None]:
    stamp: list[int | None] = []
    for path in (ENV_FILE, ENV_LOCAL_FILE):
        try:
            stamp.append(path.stat().st_mtime_ns)
        except FileNotFoundError:
            stamp.append(None)
    return (stamp[0], stamp[1])


def get_settings() -> Settings:
    """读当前生效配置；.env 变更后第一次调用即按新值返回（热重载）。"""
    global _cached_settings, _cached_stamp
    if _cached_settings is not None and _env_stamp() == _cached_stamp:
        return _cached_settings
    with _cache_lock:
        if _cached_settings is not None and _env_stamp() == _cached_stamp:
            return _cached_settings
        try:
            new_settings = _build_settings(load_env_values())
        except ValueError:
            if _cached_settings is None:
                raise
            # 重载失败：记日志、沿用旧值，等下一次文件变更再试
            logger.exception("运行参数重载失败，继续沿用旧值")
            _cached_stamp = _env_stamp()
            return _cached_settings
        if _cached_settings is not None:
            _log_changes(_cached_settings, new_settings)
        _cached_settings = new_settings
        _cached_stamp = _env_stamp()
        return _cached_settings


def _log_changes(old: Settings, new: Settings) -> None:
    fields = (
        ("env", "APP_ENV"),
        ("port", "APP_PORT"),
        ("allowed_origins", "APP_ALLOWED_ORIGINS"),
        ("page_size_max", "APP_PAGE_SIZE_MAX"),
        ("page_size_default", "APP_PAGE_SIZE_DEFAULT"),
        ("proxy_target", "VITE_PROXY_TARGET"),
    )
    for attr, label in fields:
        old_value, new_value = getattr(old, attr), getattr(new, attr)
        if old_value != new_value:
            logger.info("运行参数已按 %s 重载：%s %s -> %s", ENV_FILE, label, old_value, new_value)


def current_config_version() -> str:
    """.env 当前内容的指纹，改配置接口拿它判断有没有别处先落盘。"""
    try:
        data = ENV_FILE.read_bytes()
    except FileNotFoundError:
        data = b""
    return hashlib.sha256(data).hexdigest()[:16]


class ConfigConflictError(RuntimeError):
    """落盘前发现版本已变：别处先写入了，以先落盘的那份为准。"""


def update_env_file(updates: dict[str, str], base_version: str) -> str:
    """把 updates 合并写进 .env，返回新的版本号。

    先拿排他文件锁再比对 base_version：不一致说明等锁期间已有别处先落盘，
    按“先落盘为准”抛 ConfigConflictError，后到的这次不覆盖。写入走临时文件
    + 原子替换，读者不会读到写了一半的文件。
    """
    unknown = sorted(set(updates) - set(WRITABLE_KEYS))
    if unknown:
        raise ValueError(f"不支持的运行参数：{'、'.join(unknown)}")
    ENV_LOCK_FILE.touch(exist_ok=True)
    with ENV_LOCK_FILE.open("r+") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            if current_config_version() != base_version:
                raise ConfigConflictError(
                    "配置已被别处先落盘，本次修改未生效；请重新读取最新配置后再改"
                )
            text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
            _atomic_write(ENV_FILE, _merge_env_text(text, updates))
            return current_config_version()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _merge_env_text(text: str, updates: dict[str, str]) -> str:
    """把 updates 合并进原有文本：已有行原位替换，新 key 追加，注释原样保留。"""
    remaining = dict(updates)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                lines.append(f"{key}={remaining.pop(key)}")
                continue
        lines.append(line)
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
    return "\n".join(lines).rstrip("\n") + "\n"


def _atomic_write(path: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


_watcher_stop = threading.Event()
_watcher_thread: threading.Thread | None = None


def start_config_watcher(interval: float = 1.0) -> None:
    """后台盯 .env：变更即热重载；端口变了进程内换不了绑，按约定退出码退出让 run.sh 重启。"""
    global _watcher_thread
    if _watcher_thread is not None:
        return

    def _watch() -> None:
        last = get_settings()
        while not _watcher_stop.wait(interval):
            try:
                current = get_settings()
            except ValueError:
                continue  # 重载失败已记日志，沿用旧值
            if current is last:
                continue
            if (current.host, current.port) != (last.host, last.port):
                logger.warning(
                    "监听端口 %s -> %s：进程内无法换绑，按退出码 %s 退出，由启动脚本按新端口拉起",
                    last.port,
                    current.port,
                    RESTART_EXIT_CODE,
                )
                os._exit(RESTART_EXIT_CODE)
            last = current

    _watcher_thread = threading.Thread(target=_watch, name="runtime-config-watcher", daemon=True)
    _watcher_thread.start()


def stop_config_watcher() -> None:
    _watcher_stop.set()
