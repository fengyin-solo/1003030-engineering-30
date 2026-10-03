#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
# 监听地址以仓库根 runtime.json 为准；老的环境变量（APP_PORT 等）仍可覆盖，
# 老的命令 `uvicorn app.main:app --port 8000` 也仍然可用
exec .venv/bin/python -m app.serve
