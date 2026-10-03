"""共享运行参数：读取、热重载、校验与落盘。

仓库根的 runtime.json 是唯一需要维护的一份：后端监听地址、前端代理目标、
跨域白名单、页大小上限都从这里读，前端 vite 配置读的也是这一份。

- 后端在请求路径上按文件 mtime 感知变更，变更后立即按新值生效，并追加一条
  带时间戳的日志；历史日志保留当时的值，不回改。
- 写入一律走 RuntimeStore.update()：先拿文件锁、比对版本号、再原子落盘。
  两处同时改写时先落盘的生效，后到的因版本不匹配拿到 ConflictError。
- 老的环境变量（APP_ENV、APP_PORT、APP_CORS_ORIGINS 等）继续生效，
  优先级高于 runtime.json，低于启动命令显式参数。
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger("app.runtime")

DEFAULTS: dict[str, Any] = {
    "app_name": "通信基站运维管理平台",
    "env": "local",
    "backend": {"host": "127.0.0.1", "port": 8000},
    "frontend": {"host": "127.0.0.1", "port": 5173},
    "cors_origins": ["http://127.0.0.1:5173", "http://localhost:5173"],
    "page_size_max": 200,
    "page_size_default": 20,
    # proxy_target 缺省时由 backend.host:backend.port 派生，保证端口只维护一份
}

KNOWN_KEYS = frozenset(DEFAULTS) | {"proxy_target"}

# 老的环境变量继续生效：优先级高于 runtime.json
ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "APP_ENV": ("env",),
    "APP_HOST": ("backend", "host"),
    "APP_PORT": ("backend", "port"),
    "APP_FRONTEND_HOST": ("frontend", "host"),
    "APP_FRONTEND_PORT": ("frontend", "port"),
    "APP_CORS_ORIGINS": ("cors_origins",),
    "APP_PAGE_SIZE_MAX": ("page_size_max",),
    "APP_PAGE_SIZE_DEFAULT": ("page_size_default",),
    "APP_PROXY_TARGET": ("proxy_target",),
}

_SECTION_KEYS = {"backend": frozenset({"host", "port"}), "frontend": frozenset({"host", "port"})}


@dataclass(frozen=True)
class Settings:
    """某一时刻生效的运行参数快照。"""

    app_name: str = "通信基站运维管理平台"
    env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5173
    proxy_target: str = "http://127.0.0.1:8000"
    allowed_origins: list[str] = field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    page_size_default: int = 20
    page_size_max: int = 200
    config_version: str = ""


class ConflictError(Exception):
    """基于旧版本的写入被拒绝：已有另一份先落盘。"""

    def __init__(self, current_version: str) -> None:
        super().__init__(current_version)
        self.current_version = current_version


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _canonical(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def version_of(file_values: dict[str, Any]) -> str:
    """文件内容的版本号：内容变了版本就变，手工改文件同样生效。"""
    return hashlib.sha256(_canonical(file_values).encode("utf-8")).hexdigest()[:16]


def _parse_env_value(raw: str, path: tuple[str, ...]) -> Any:
    key = path[-1]
    if key in ("port", "page_size_max", "page_size_default"):
        return int(raw)
    if key == "cors_origins":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def _apply_env(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """把生效中的环境变量覆盖叠上去，返回 (合并结果, {键路径: 环境变量名})。"""
    merged = copy.deepcopy(values)
    applied: dict[str, str] = {}
    for env_name, path in ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            continue
        try:
            parsed = _parse_env_value(raw.strip(), path)
        except ValueError:
            logger.warning("环境变量 %s=%r 无法解析，忽略，继续用 runtime.json 里的值", env_name, raw)
            continue
        node = merged
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = parsed
        applied[".".join(path)] = env_name
    return merged, applied


def _derive(values: dict[str, Any]) -> dict[str, Any]:
    """缺省的代理目标跟随后端地址：端口只维护一份，换端口后各入口读到的一致。"""
    if not values.get("proxy_target"):
        backend = values.get("backend") or {}
        values["proxy_target"] = f"http://{backend.get('host', '127.0.0.1')}:{backend.get('port', 8000)}"
    return values


def _validate_effective(values: dict[str, Any]) -> None:
    for section in ("backend", "frontend"):
        node = values.get(section)
        if not isinstance(node, dict):
            raise ValueError(f"{section} 必须是对象（如 {{\"host\": \"127.0.0.1\", \"port\": 8000}}）")
        host = node.get("host")
        if not isinstance(host, str) or not host.strip():
            raise ValueError(f"{section}.host 必须是非空字符串")
        port = node.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError(f"{section}.port 必须是 1-65535 的整数")
    origins = values.get("cors_origins")
    if not isinstance(origins, list) or not all(isinstance(o, str) and o.strip() for o in origins):
        raise ValueError("cors_origins 必须是非空字符串数组")
    size_max = values.get("page_size_max")
    if not isinstance(size_max, int) or isinstance(size_max, bool) or size_max < 1:
        raise ValueError("page_size_max 必须是正整数")
    size_default = values.get("page_size_default")
    if not isinstance(size_default, int) or isinstance(size_default, bool) or size_default < 1:
        raise ValueError("page_size_default 必须是正整数")
    if size_default > size_max:
        raise ValueError("page_size_default 不能大于 page_size_max")
    proxy = values.get("proxy_target")
    if proxy is not None and (not isinstance(proxy, str) or not proxy.startswith(("http://", "https://"))):
        raise ValueError("proxy_target 必须是 http(s):// 开头的地址")


def _to_settings(values: dict[str, Any], version: str) -> Settings:
    backend = values.get("backend") or {}
    frontend = values.get("frontend") or {}
    return Settings(
        app_name=str(values.get("app_name", DEFAULTS["app_name"])),
        env=str(values.get("env", "local")),
        host=str(backend.get("host", "127.0.0.1")),
        port=int(backend.get("port", 8000)),
        frontend_host=str(frontend.get("host", "127.0.0.1")),
        frontend_port=int(frontend.get("port", 5173)),
        proxy_target=str(values.get("proxy_target", "")),
        allowed_origins=[str(origin) for origin in values.get("cors_origins", [])],
        page_size_default=int(values.get("page_size_default", 20)),
        page_size_max=int(values.get("page_size_max", 200)),
        config_version=version,
    )


class RuntimeStore:
    """runtime.json 的实时视图：按 mtime 感知变更，变更即重新生效。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._file_stat: tuple[int, int] | None = None
        self._file_values: dict[str, Any] = {}
        self._settings = Settings()
        self._effective = _derive(_apply_env(copy.deepcopy(DEFAULTS))[0])
        self._version = version_of({})
        self._env_applied: dict[str, str] = {}
        with self._lock:
            if not self._install(self._read_file(), log=False):
                # 首次加载就无效：退回 默认值+环境变量，再退到纯默认值，保证服务能起
                if not self._install({}, log=False):
                    self._install_defaults()

    # ---- 读取 ----

    def get(self) -> Settings:
        """当前生效值；文件有变化时先重载再返回。"""
        if self._stat() != self._file_stat:
            self.reload(log=True)
        return self._settings

    @property
    def version(self) -> str:
        return self._version

    def describe(self) -> dict[str, Any]:
        self.get()
        return {
            "path": str(self.path),
            "version": self._version,
            "values": copy.deepcopy(self._effective),
            "overridden_by_env": dict(self._env_applied),
        }

    def reload(self, log: bool) -> None:
        with self._lock:
            self._install(self._read_file(), log=log)

    # ---- 写入 ----

    def update(self, patch: dict[str, Any], base_version: str | None) -> dict[str, Any]:
        """校验并落盘，返回最新 describe()。

        base_version 必须与落盘前磁盘上的版本一致；不一致说明已有另一份先落盘，
        本次写入抛 ConflictError——两处同时改写时以先落盘的那份为准。
        """
        if not isinstance(patch, dict) or not patch:
            raise ValueError("values 必须是非空对象")
        unknown = set(patch) - KNOWN_KEYS
        if unknown:
            raise ValueError(
                f"未识别的参数键：{'、'.join(sorted(unknown))}（可选：{'、'.join(sorted(KNOWN_KEYS))}）"
            )
        for section, allowed in _SECTION_KEYS.items():
            node = patch.get(section)
            if node is None:
                continue
            if not isinstance(node, dict):
                raise ValueError(f"{section} 必须是对象（如 {{\"port\": 8000}}）")
            unknown_sub = set(node) - allowed
            if unknown_sub:
                raise ValueError(
                    f"{section} 里未识别的键：{'、'.join(sorted(unknown_sub))}（可选：{'、'.join(sorted(allowed))}）"
                )

        with self._lock:
            lock_path = self.path.with_name(self.path.name + ".lock")
            with open(lock_path, "a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    current = self._read_file()
                    current_version = version_of(current)
                    if base_version is None:
                        raise ValueError("缺少 base_version：请先 GET /api/runtime 读取当前版本再改写")
                    if base_version != current_version:
                        raise ConflictError(current_version)
                    blocked = self._env_blocked_keys(patch)
                    if blocked:
                        raise ValueError(
                            "以下参数正被环境变量覆盖，写入不会生效；请先去掉环境变量："
                            + "、".join(f"{key}（{env}）" for key, env in blocked)
                        )
                    merged = _deep_merge(current, patch)
                    _validate_effective(_derive(_apply_env(_deep_merge(DEFAULTS, merged))[0]))
                    self._write_file(merged)
                    self._install(merged, log=False)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        logger.info("运行参数已落盘 version=%s 变更键=%s", self._version, "、".join(sorted(patch)))
        return self.describe()

    # ---- 内部 ----

    def _env_blocked_keys(self, patch: dict[str, Any]) -> list[tuple[str, str]]:
        blocked: list[tuple[str, str]] = []
        for key in patch:
            for path, env_name in self._env_applied.items():
                if path == key or path.startswith(f"{key}."):
                    blocked.append((path, env_name))
        return blocked

    def _install(self, file_values: dict[str, Any], log: bool) -> bool:
        merged, env_applied = _apply_env(_deep_merge(DEFAULTS, file_values))
        merged = _derive(merged)
        try:
            _validate_effective(merged)
        except ValueError as exc:
            logger.error("%s 里的值无效（%s），沿用当前生效值", self.path, exc)
            self._file_stat = self._stat()
            return False
        settings = _to_settings(merged, version_of(file_values))
        previous = self._settings
        self._file_values = file_values
        self._settings = settings
        self._effective = merged
        self._version = settings.config_version
        self._env_applied = env_applied
        self._file_stat = self._stat()
        if log and settings != previous:
            logger.info("运行参数已按新的一份生效 version=%s values=%s", settings.config_version, _canonical(merged))
        return True

    def _install_defaults(self) -> None:
        """连环境变量都凑不出合法值时的最后兜底：纯默认值，保证服务能起。"""
        merged = _derive(copy.deepcopy(DEFAULTS))
        self._settings = _to_settings(merged, self._version)
        self._effective = merged
        self._env_applied = {}

    def _stat(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _read_file(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.error("读取 %s 失败（%s），沿用当前生效值", self.path, exc)
            return self._file_values
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("%s 不是合法 JSON（%s），沿用当前生效值", self.path, exc)
            return self._file_values
        if not isinstance(data, dict):
            logger.error("%s 顶层必须是 JSON 对象，沿用当前生效值", self.path)
            return self._file_values
        unknown = set(data) - KNOWN_KEYS
        if unknown:
            logger.warning("%s 含未识别的键 %s，已忽略", self.path, sorted(unknown))
            data = {key: value for key, value in data.items() if key in KNOWN_KEYS}
        return data

    def _write_file(self, values: dict[str, Any]) -> None:
        text = json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as tmp:
                tmp.write(text)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, self.path)
        except OSError:
            # 单文件 bind mount（compose 把 runtime.json 挂进容器）不允许 rename，
            # 退化为原地写入；此时仍有文件锁保证写者互斥
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            with open(self.path, "w", encoding="utf-8") as target:
                target.write(text)
                target.flush()
                os.fsync(target.fileno())


def check_page_size(size: int) -> None:
    """按当前生效的页大小上限校验；上限改动后下一个请求就按新值拦。"""
    limit = runtime_store.get().page_size_max
    if size > limit:
        raise HTTPException(status_code=400, detail=f"每页最多 {limit} 条，请缩小分页范围")


def _default_config_path() -> Path:
    env_path = os.environ.get("APP_RUNTIME_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "runtime.json"
        if candidate.exists():
            return candidate
    return here.parents[2] / "runtime.json"


runtime_store = RuntimeStore(_default_config_path())
