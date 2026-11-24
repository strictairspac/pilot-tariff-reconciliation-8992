# 鹭汊引航·费率追溯复核

费率补录可以追溯服务日期，按原开账日和追溯日双重口径核算补差及暂缓航次。

## 业务流程

1. 开账交接
2. 航次与费率
3. 双时间复算
4. 港务调账单

MySQL 同时查询业务生效与系统登记两个半开区间，按历史认知核对费差。

鹭汊港引航结算组收到引航作业单与合同补录单，复算后给港务会计。旧账本把费率直接覆盖，旧开账无法回溯、跨生效日计价错误、重叠合同未阻断。

08:40 核对 LC-PILOT-1109 的 5 条航次，08:45 检查航段、吨位和作业日，08:55 导入 11 月 18 日补录费率，09:00 按 11 月 23 日认知运行，09:03 审阅北槽 2 条补差，09:07 处理 2 条暂缓，09:10 把调账证据导出给会计。

两个时间维度都取半开区间，结束留空表示无上限。仅在各自时点命中唯一费率才计价。每千总吨向上取整，费用（分）为计费单位乘费率与最低收费的较大者。默认 3 条可调账、2 条暂缓、净补差 9000 分。此模型已含原认知和现认知的实算，补差不含税，也不发送实际入账指令。

## 启动

```sh
cp -n .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
```

打开 <http://localhost:18253>。OpenAPI 在 <http://localhost:19253/docs>，数据库映射到本机 17753。所有暴露端口只绑定回环地址。Compose 启动 frontend、backend、worker、db、redis，各自通过健康探针检查。数据库、Redis 和共享产物目录各有命名卷；任务状态及导出内容以数据库中的证据为准。

首次启动时幂等载入演示数据。手动载入可运行 `docker compose exec -T backend python -m scripts.seed_demo`。常规停止可用 `docker compose down`。验收环境清理才加 `-v`，它会删除本项目的数据卷。

## 角色与交接

演示账号共用口令 `Demo-DbWorkbench-2026`。

| 登录名 | 角色 | 可执行操作 |
|---|---|---|
| operator | 资料操作员 | 登记业务资料、设置「复核日（11 月 1 日起第几天）」、提交、查看和下载结果 |
| reviewer | 业务复核员 | 查看执行证据、签署单次复核、下载交接单 |
| viewer | 只读观察员 | 查看资料、执行结果及审计，下载证据 |

选用「LC-PILOT-1109」对应的演示资料，保存一份复演资料，再以默认参数 23 提交。worker 保存结果摘要、业务明细和 SHA-256。复核员登录后在「港务调账单」签署。

## 开发说明

| 部分 | 实现 |
|---|---|
| 前端 | 原生 HTML、CSS、JavaScript ES Modules、Nginx |
| 后端 | Python 3.11、FastAPI、SQLAlchemy、JWT |
| 数据库 | MySQL 8.0 |
| 后台执行 | Redis 通知、数据库持久任务队列和行锁、Python worker |

从 `backend/src/domain/scenario.py` 修改业务入口和演示口径，运行 `docker compose up -d --build --wait` 查看变更。数据库表结构在 `backend/src/models` 和 `backend/migrations`，输入模型在 `backend/src/schemas`。业务页和请求接口在 `frontend/src/pages`、`frontend/src/api`。资料、执行、复核三个工作流实体各有独立表和 API；场景输入及结果保留在所属资料和批次中。

角色枚举在 `backend/src/constants/roles.py`、`frontend/src/constants/roles.js`，用于服务端访问控制、账号初始化、前端导航与签署。批次状态在 `backend/src/constants/job_state.py`、`frontend/src/constants/states.js`，用于队列、状态 API、状态标记与轮询。登记、提交、完成和签署事件写入审计表。

`COMPOSE_PROJECT_NAME` 设置栈名，`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 设置端口。通过 `DB_PASSWORD`、`JWT_SECRET`、`DEMO_PASSWORD` 配置本地凭据。设置 `SEED_DEMO=false` 可关闭演示数据载入，此时数据库初始没有演示账号。数据库密码调整后，已有数据卷需在数据库内同步修改用户密码。

## 验收范围

沿用固定 2026 基准日，并按样本合同输入计算人民币分。 当前界面用 JSON 编辑业务资料，以 JSON 下载证据。过程和截图保存在批次的 [验收记录](../../test-artifacts/gb-6104/TESTING.md)。

[MIT License](LICENSE)
