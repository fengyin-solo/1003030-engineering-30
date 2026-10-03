#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# 端口等运行参数统一从仓库根目录 .env 读（前后端只维护这一份），
# 老的 APP_PORT 等进程环境变量仍然优先。运行中改了 .env 里的端口时，
# 服务会以约定退出码 75 退出，这里按新的那一份重新拉起。
while true; do
  port="$(.venv/bin/python -c 'from app.config import get_settings; print(get_settings().port)')"
  set +e
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$port"
  code=$?
  set -e
  if [ "$code" -ne 75 ]; then
    exit "$code"
  fi
  echo "[run.sh] 检测到 .env 端口变更，按新的配置重启后端..."
done
