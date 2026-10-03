"""共享运行参数的单元测试：读取、覆盖、热重载、落盘与冲突。"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from app import runtime
from app.cors import RuntimeCORSMiddleware
from app.runtime import ConflictError, RuntimeStore, version_of


def make_store(values: dict | None = None) -> RuntimeStore:
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / "runtime.json"
    if values is not None:
        path.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    return RuntimeStore(path)


class LoadTest(unittest.TestCase):
    def test_defaults_when_file_missing(self):
        store = make_store()
        settings = store.get()
        self.assertEqual(settings.port, 8000)
        self.assertEqual(settings.frontend_port, 5173)
        self.assertEqual(settings.page_size_max, 200)
        self.assertEqual(settings.allowed_origins, ["http://127.0.0.1:5173", "http://localhost:5173"])

    def test_file_values_win_over_defaults(self):
        store = make_store({"backend": {"port": 9000}, "page_size_max": 50})
        settings = store.get()
        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.page_size_max, 50)
        self.assertEqual(settings.host, "127.0.0.1")  # 未配的键回落到默认值

    def test_proxy_target_derived_from_backend(self):
        store = make_store({"backend": {"host": "127.0.0.1", "port": 9000}})
        self.assertEqual(store.get().proxy_target, "http://127.0.0.1:9000")

    def test_proxy_target_explicit_pinned(self):
        store = make_store({"proxy_target": "http://10.0.0.2:8080", "backend": {"port": 9000}})
        self.assertEqual(store.get().proxy_target, "http://10.0.0.2:8080")

    def test_env_override_wins_and_is_recorded(self):
        with mock.patch.dict(os.environ, {"APP_PORT": "8011", "APP_PAGE_SIZE_MAX": "30"}):
            store = make_store({"backend": {"port": 9000}})
            settings = store.get()
            self.assertEqual(settings.port, 8011)
            self.assertEqual(settings.page_size_max, 30)
            described = store.describe()
            self.assertEqual(described["overridden_by_env"]["backend.port"], "APP_PORT")
            self.assertEqual(described["overridden_by_env"]["page_size_max"], "APP_PAGE_SIZE_MAX")

    def test_invalid_file_keeps_last_good_values(self):
        store = make_store({"backend": {"port": 9000}})
        self.assertEqual(store.get().port, 9000)
        store.path.write_text("{不是合法JSON", encoding="utf-8")
        self.assertEqual(store.get().port, 9000)  # 沿用旧值，不崩

    def test_invalid_values_keep_last_good(self):
        store = make_store({"backend": {"port": 9000}})
        store.path.write_text(json.dumps({"backend": {"port": 99999}}), encoding="utf-8")
        self.assertEqual(store.get().port, 9000)  # 端口越界，沿用旧值

    def test_invalid_first_load_falls_back_to_defaults_with_env(self):
        with mock.patch.dict(os.environ, {"APP_PORT": "8011"}):
            store = make_store({"backend": {"port": 99999}})  # 文件无效
            self.assertEqual(store.get().port, 8011)  # 退回 默认值+环境变量，服务能起

    def test_invalid_file_and_env_falls_back_to_plain_defaults(self):
        # APP_PAGE_SIZE_MAX=15 比默认 page_size_default=20 还小，环境变量组合也无效
        with mock.patch.dict(os.environ, {"APP_PAGE_SIZE_MAX": "15"}):
            store = make_store({"backend": {"port": 99999}})
            self.assertEqual(store.get().port, 8000)  # 纯默认值兜底
            self.assertEqual(store.get().page_size_max, 200)


class ReloadTest(unittest.TestCase):
    def test_hot_reload_on_file_change(self):
        store = make_store({"page_size_max": 200})
        self.assertEqual(store.get().page_size_max, 200)
        store.path.write_text(json.dumps({"page_size_max": 50}), encoding="utf-8")
        self.assertEqual(store.get().page_size_max, 50)  # 不重启即按新值生效

    def test_version_tracks_file_content(self):
        store = make_store({"page_size_max": 200})
        first = store.version
        store.path.write_text(json.dumps({"page_size_max": 50}), encoding="utf-8")
        store.get()
        self.assertNotEqual(store.version, first)
        self.assertEqual(store.version, version_of({"page_size_max": 50}))


class UpdateTest(unittest.TestCase):
    def test_update_persists_and_takes_effect(self):
        store = make_store({"page_size_max": 200})
        base = store.version
        described = store.update({"page_size_max": 80}, base)
        self.assertEqual(described["values"]["page_size_max"], 80)
        self.assertEqual(store.get().page_size_max, 80)
        on_disk = json.loads(store.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["page_size_max"], 80)

    def test_first_to_disk_wins(self):
        """两处同时基于同一版本改写：先落盘的生效，后到的拿到冲突。"""
        store = make_store({"page_size_max": 200})
        base = store.version
        store.update({"page_size_max": 80}, base)  # 先落盘
        with self.assertRaises(ConflictError):
            store.update({"page_size_max": 60}, base)  # 基于旧版本，后到被拒
        self.assertEqual(store.get().page_size_max, 80)  # 以先落盘的那份为准

    def test_manual_edit_between_reads_also_conflicts(self):
        store = make_store({"page_size_max": 200})
        base = store.version
        store.path.write_text(json.dumps({"page_size_max": 90}), encoding="utf-8")  # 另一处先落盘
        with self.assertRaises(ConflictError):
            store.update({"page_size_max": 60}, base)
        self.assertEqual(store.get().page_size_max, 90)

    def test_missing_base_version_rejected(self):
        store = make_store({})
        with self.assertRaises(ValueError):
            store.update({"page_size_max": 80}, None)

    def test_unknown_key_rejected(self):
        store = make_store({})
        with self.assertRaises(ValueError):
            store.update({"page_size_maxx": 80}, store.version)

    def test_invalid_value_rejected_and_file_untouched(self):
        store = make_store({"page_size_max": 200})
        before = store.path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            store.update({"backend": {"port": 70000}}, store.version)
        self.assertEqual(store.path.read_text(encoding="utf-8"), before)

    def test_env_overridden_key_rejected(self):
        with mock.patch.dict(os.environ, {"APP_PORT": "8011"}):
            store = make_store({})
            with self.assertRaises(ValueError):
                store.update({"backend": {"port": 9000}}, store.version)


class PageSizeTest(unittest.TestCase):
    def test_check_page_size_uses_live_limit(self):
        store = make_store({"page_size_max": 40})
        with mock.patch.object(runtime, "runtime_store", store):
            runtime.check_page_size(40)  # 不抛
            with self.assertRaises(HTTPException) as ctx:
                runtime.check_page_size(41)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("40", ctx.exception.detail)
            # 文件改成新上限后，下一次校验就按新值拦（默认页大小得一起调小）
            store.path.write_text(json.dumps({"page_size_max": 10, "page_size_default": 10}), encoding="utf-8")
            with self.assertRaises(HTTPException) as ctx:
                runtime.check_page_size(11)
            self.assertIn("10", ctx.exception.detail)


class CorsTest(unittest.TestCase):
    def run_middleware(self, store: RuntimeStore, scope: dict) -> list[dict]:
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        messages: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request"}

        async def send(message: dict) -> None:
            messages.append(message)

        with mock.patch.object(runtime, "runtime_store", store):
            with mock.patch("app.cors.runtime_store", store):
                asyncio.run(RuntimeCORSMiddleware(app)(scope, receive, send))
        return messages

    def test_preflight_allowed_origin(self):
        store = make_store({"cors_origins": ["http://127.0.0.1:5173"]})
        scope = {
            "type": "http",
            "method": "OPTIONS",
            "headers": [
                (b"origin", b"http://127.0.0.1:5173"),
                (b"access-control-request-method", b"GET"),
            ],
        }
        messages = self.run_middleware(store, scope)
        self.assertEqual(messages[0]["status"], 200)
        headers = dict(messages[0]["headers"])
        self.assertEqual(headers[b"access-control-allow-origin"], b"http://127.0.0.1:5173")
        self.assertEqual(headers[b"access-control-allow-credentials"], b"true")

    def test_preflight_rejected_origin_passes_through(self):
        store = make_store({"cors_origins": ["http://127.0.0.1:5173"]})
        scope = {
            "type": "http",
            "method": "OPTIONS",
            "headers": [
                (b"origin", b"http://evil.example"),
                (b"access-control-request-method", b"GET"),
            ],
        }
        messages = self.run_middleware(store, scope)
        headers = dict(messages[0]["headers"])
        self.assertNotIn(b"access-control-allow-origin", headers)

    def test_simple_response_and_hot_reload(self):
        store = make_store({"cors_origins": ["http://a.example"]})
        scope = {"type": "http", "method": "GET", "headers": [(b"origin", b"http://b.example")]}
        messages = self.run_middleware(store, scope)
        self.assertNotIn(b"access-control-allow-origin", dict(messages[0]["headers"]))
        # 白名单写进文件后，下一个请求就按新名单放行
        store.path.write_text(json.dumps({"cors_origins": ["http://b.example"]}), encoding="utf-8")
        messages = self.run_middleware(store, scope)
        headers = dict(messages[0]["headers"])
        self.assertEqual(headers[b"access-control-allow-origin"], b"http://b.example")


if __name__ == "__main__":
    unittest.main()
