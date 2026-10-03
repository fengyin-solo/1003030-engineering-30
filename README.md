# 通信基站运维管理平台

面向通信基站站点入网、动力环境监控、天馈巡检、发电保障与退网拆站的一体化基站运维管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 运行参数（只维护一份）

端口、代理目标、跨域白名单、页大小上限统一维护在仓库根目录的 **`.env`**（已入库），
后端 `run.sh`/uvicorn、前端 vite 代理、docker-compose 都从这一份读：

| 键 | 含义 | 默认值 |
| --- | --- | --- |
| `APP_PORT` | 后端监听端口，前端代理目标默认跟随它 | `8000` |
| `APP_ALLOWED_ORIGINS` | 跨域白名单（逗号分隔） | `http://127.0.0.1:5173,http://localhost:5173` |
| `APP_PAGE_SIZE_MAX` | 列表页大小上限 | `200` |
| `APP_PAGE_SIZE_DEFAULT` | 列表默认页大小 | `20` |
| `VITE_PROXY_TARGET` | 前端代理目标（不填时按 `APP_PORT` 推导） | 注释掉 |

- 覆盖优先级：`.env` < `.env.local`（本机临时覆盖，不入库）< 进程环境变量；
  老的 `APP_ENV`、`VITE_PROXY_TARGET`、`VITE_API_BASE` 环境变量和原有启动命令都继续能用。
- 改完 `.env` 保存后，运行中的服务自动按新值重载：后端的跨域白名单、页大小上限
  热生效；端口变更由后端按约定退出码退出、`run.sh` 自动按新端口重新拉起；前端
  dev server 检测到 `.env` 变化会自动重启。重载只追加新日志，历史日志保留当时的值。
- 也可以通过接口查看/修改：`GET /api/runtime/config` 返回当前生效值和版本号，
  `PUT /api/runtime/config` 带 `values` 与 `base_version` 落盘。两处同时改时
  以先落盘的为准，后到的一次返回 409，需重新读取后再改。

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
│   └── app/store.py          内存数据仓库与示例数据
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

健康检查：`curl http://127.0.0.1:8000/api/health`（端口以 `.env` 的 `APP_PORT` 为准）

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端，目标地址跟随 `.env` 的 `APP_PORT`
（默认 `http://127.0.0.1:8000`）。

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
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
