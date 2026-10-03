"""后端启动器：监听地址以仓库根 runtime.json 为准，参数变更时自动重载。

- 端口/地址改动：侦测到后重启监听，按新的一份绑定
- 跨域白名单、页大小上限等：请求路径上热生效，不需要重启
- 老命令 `uvicorn app.main:app --host 127.0.0.1 --port 8000` 仍然可用
  （显式指定、静态，不跟随 runtime.json）
"""
from __future__ import annotations

import argparse
import logging
import threading
import time

import uvicorn

# 先配好日志格式再导入 app.runtime：首次加载的报错也要带时间戳
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from app.runtime import runtime_store

logger = logging.getLogger("app.serve")

POLL_INTERVAL_SECONDS = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通信基站运维管理平台 后端启动器")
    parser.add_argument("--host", default=None, help="监听地址（缺省读 runtime.json 的 backend.host）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（缺省读 runtime.json 的 backend.port）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # 显式指定了地址就按显式的跑（和老命令一致），不再跟随 runtime.json
    follow_file = args.host is None and args.port is None

    while True:
        settings = runtime_store.get()
        host = args.host or settings.host
        port = args.port or settings.port
        logger.info("后端监听 %s:%s（运行参数版本 %s）", host, port, settings.config_version)

        config = uvicorn.Config("app.main:app", host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        restart = threading.Event()

        if follow_file:
            def watch_for_move(bound: tuple[str, int] = (host, port)) -> None:
                while not restart.is_set():
                    time.sleep(POLL_INTERVAL_SECONDS)
                    current = runtime_store.get()
                    if (current.host, current.port) != bound:
                        logger.info(
                            "监听地址 %s:%s → %s:%s，按新的一份重启",
                            bound[0], bound[1], current.host, current.port,
                        )
                        restart.set()
                        server.should_exit = True

            threading.Thread(target=watch_for_move, daemon=True).start()

        server.run()
        if not restart.is_set():
            break


if __name__ == "__main__":
    main()
