# 通信基站运维管理平台

面向通信基站站点入网、动力环境监控、天馈巡检、发电保障与退网拆站的一体化基站运维管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   ├── app/runtime.py        共享运行参数的读取、热重载与落盘
│   └── app/store.py          内存数据仓库与示例数据
├── runtime.json              运行参数唯一来源（端口/代理/跨域/页大小）
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`（端口以 `runtime.json` 为准，默认 8000）

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端，代理目标同样取自 `runtime.json`。

## 运行参数（只维护一份）

端口、代理目标、跨域白名单、页大小上限的唯一来源是仓库根的
[`runtime.json`](runtime.json)，后端和前端读的都是这一份：

```json
{
  "backend": { "host": "127.0.0.1", "port": 8000 },
  "frontend": { "host": "127.0.0.1", "port": 5173 },
  "cors_origins": ["http://127.0.0.1:5173", "http://localhost:5173"],
  "page_size_max": 200,
  "page_size_default": 20
}
```

- **改完两边同时生效**：后端在请求路径上感知文件变更（跨域白名单、页大小
  上限立即按新值执行；`./run.sh` 启动时换端口会自动重启监听），前端 dev
  server 侦测到 `runtime.json` 变更会自动重启并换上新端口/代理目标。
  每次生效都会追加一条带时间戳的日志，历史日志保留当时的值。
- **代理目标派生**：不配置 `proxy_target` 时自动取
  `http://{backend.host}:{backend.port}`，换端口后各入口读到的一致；
  需要钉死时可在 `runtime.json` 里显式写 `proxy_target`。
- **读写接口**：`GET /api/runtime` 返回当前生效值和版本号；
  `PUT /api/runtime` 携带 `base_version` 改写并原子落盘。两处同时改写时
  以先落盘的那份为准，后到的收到 409，重新读取版本后再改即可。
  被环境变量覆盖的键不允许写入（会返回 400 说明原因）。
- **老的环境变量继续能用**，优先级高于 `runtime.json`：`APP_ENV`、
  `APP_HOST`、`APP_PORT`、`APP_FRONTEND_PORT`、`APP_CORS_ORIGINS`、
  `APP_PAGE_SIZE_MAX`、`APP_PAGE_SIZE_DEFAULT`、`APP_PROXY_TARGET`、
  `VITE_PROXY_TARGET`（见 `.env.example`）。
- **老的启动命令继续能用**：`./run.sh`、`make backend`、`npm run dev`，以及
  显式指定地址的 `uvicorn app.main:app --host 127.0.0.1 --port 8000`
  （显式参数为静态值，不跟随 `runtime.json`）。
- **docker compose**：宿主机改 `runtime.json` 容器内立即可见；compose 场景下
  换端口用 `.env` 里的 `APP_PORT`（同时驱动端口映射和容器内监听，
  与 `runtime.json` 是同一参数的环境变量覆盖通道）。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 基站台账 | `site` | 基站 | 基站编号、基站名称、基站类型 |
| 铁塔管理 | `tower` | 铁塔 | 铁塔编号、铁塔类型、设计高度 |
| 动力配套 | `power` | 电源设备 | 设备编号、设备类型、额定功率 |
| 蓄电池组 | `battery` | 蓄电池组 | 电池组编号、电池类型、额定容量 |
| 发电机组 | `genset` | 发电机组 | 机组编号、机组型号、额定功率 |
| 开关电源 | `rectifier` | 开关电源 | 电源编号、额定功率、所属站点 |
| 空调管理 | `ac` | 空调 | 空调编号、空调类型、制冷量 |
| 天馈系统 | `antenna` | 天馈设备 | 天馈编号、天线类型、工作频段 |
| 传输设备 | `transmission` | 传输设备 | 设备编号、传输类型、带宽容量 |
| 馈线巡检 | `feeder` | 馈线 | 馈线编号、所属站点、馈线长度 |
| 防雷接地 | `lightningprot` | 防雷装置 | 装置编号、所属站点、接地电阻 |
| 消防设施 | `firealarm` | 消防设施 | 设施编号、设施类型、所属站点 |
| 门禁管理 | `dooraccess` | 门禁记录 | 门禁编号、所属站点、开门方式 |
| 巡检作业 | `patrol` | 巡检任务 | 任务编号、巡检站点、巡检人员 |
| 油料管理 | `fuel` | 油料记录 | 记录编号、所属站点、油料类型 |
| 场租合同 | `rental` | 场租合同 | 合同编号、站点名称、出租方 |
| 电费管理 | `electricbill` | 电费记录 | 记录编号、所属站点、电表读数 |
| 拆站管理 | `demolition` | 拆站任务 | 任务编号、拆除站点、拆除原因 |
| 应急通信 | `emergency` | 应急保障 | 保障编号、保障类型、保障地点 |
| 节能改造 | `energyeff` | 节能项目 | 项目编号、所属站点、改造内容 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 列表的页大小上限统一走 `app.runtime.check_page_size`，上限值只认 `runtime.json`
  的 `page_size_max`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
