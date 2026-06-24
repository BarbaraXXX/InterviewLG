# 独立管理员监控后台设计

日期：2026-06-24

## 背景

当前 Interview Agent 的普通用户端已经包含登录、面试配置、面试聊天、历史记录、简历信息、语音输入和手撕代码等能力，但系统缺少后台监控能力。站点部署在 2 核 2G、40GB 存储的小型服务器上，不能为了监控引入过重的运行时组件。

现有前端主要通过 React 内部状态切换页面，URL 基本保持在站点根路径。这种方式适合早期快速迭代，但随着功能增加，页面边界、权限边界和刷新恢复会逐渐变弱。后台系统应从这次开始使用更清晰的路由边界，即 `/admin/...` 独立入口。

## 目标

- 建立一个独立的管理员系统，不复用普通用户账号作为管理员身份。
- 提供单独的管理员登录页面和管理员后台页面。
- 使用轻量方式监控用户在线情况和基础使用情况。
- 不新增 Redis、Prometheus、Grafana、ELK、WebSocket 常驻连接或额外 Docker 服务。
- 后台监控只展示运维判断需要的低敏信息，不展示密码、cookie、简历正文、面试全文、音频内容等敏感数据。
- 为后续前端路由规范化保留方向，但第一版不迁移普通用户端现有页面。

## 非目标

- 不做完整后台管理系统，不支持管理员编辑用户数据、查看用户密码、重置用户密码或代替用户操作。
- 不做全量行为埋点，不记录每一次点击和页面停留明细。
- 不做实时强一致在线状态，在线判断允许有 1-5 分钟误差。
- 不在第一版引入图表库；趋势展示可以先用简单卡片、表格和轻量 CSS 条形图。
- 不在本阶段改造普通用户端为 `/login`、`/dashboard`、`/history` 等完整前端路由。

## 路由设计

管理员前端使用独立路径：

- `/admin/login`：管理员登录页。
- `/admin`：管理员监控首页。

后端继续服务同一个 SPA 构建产物，但前端需要根据 `window.location.pathname` 判断是否进入管理员应用壳。普通用户系统暂时保持现状。

成熟路由方向应保留在后续规划中：

- 普通用户端后续可逐步迁移到 `/login`、`/dashboard`、`/setup`、`/interview/:sessionId`、`/history`、`/profile`、`/insights`。
- 管理端从第一版开始使用 `/admin/...`，避免后续后台功能继续堆在普通 Dashboard 里。

## 管理员账号模型

新增 SQLite 表 `admin_users`：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `username TEXT NOT NULL UNIQUE`
- `password_hash TEXT NOT NULL`
- `disabled INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT NOT NULL DEFAULT (datetime('now'))`
- `last_login_at TEXT`

管理员账号不开放网页注册。第一版通过命令行创建：

```bash
uv run interview-agent-admin create-user <username>
```

命令行交互式输入密码，后端使用与普通用户相同强度的 bcrypt 哈希存储。后续如需禁用管理员，可以再增加命令行 `disable-user`，第一版可只预留数据库字段。

## 管理员认证

管理员认证和普通用户认证分离。

新增配置：

- `ADMIN_AUTH_SECRET_KEY`
- `ADMIN_AUTH_COOKIE_NAME=interviewlg_admin_token`
- `ADMIN_AUTH_TOKEN_EXPIRE_HOURS=8`

新增 API：

- `POST /api/admin/auth/login`
- `POST /api/admin/auth/logout`
- `GET /api/admin/auth/me`

管理员 JWT 使用 `ADMIN_AUTH_SECRET_KEY`，cookie 使用独立名称。普通用户 cookie 不能访问管理员接口，管理员 cookie 也不用于普通用户接口。

所有 `/api/admin/...` 监控接口必须依赖 `get_current_admin`。未登录返回 `401`，登录但账号禁用返回 `403`。

## 在线状态模型

新增 SQLite 表 `user_presence`：

- `user_id INTEGER PRIMARY KEY`
- `username TEXT NOT NULL`
- `current_view TEXT NOT NULL DEFAULT ''`
- `active_session_id TEXT NOT NULL DEFAULT ''`
- `last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))`
- `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`

普通用户登录后，前端每 90 秒左右调用：

```http
POST /api/presence/heartbeat
```

请求体：

```json
{
  "current_view": "dashboard",
  "active_session_id": ""
}
```

后端只接受有限长度字符串，不保存 URL 查询参数、IP、UA 或页面详细行为。

在线状态判断：

- `last_seen_at` 在 5 分钟内：在线。
- `last_seen_at` 在 15 分钟内：最近活跃。
- 超过 15 分钟：不在默认在线列表展示。

前端页面隐藏或浏览器后台时，可以停止 heartbeat 或降低频率。用户退出登录时调用 logout 后无需强制删除 presence，等待超时即可，避免额外复杂度。

## 使用统计模型

新增 SQLite 表 `daily_usage_stats`：

- `stat_date TEXT NOT NULL`
- `metric TEXT NOT NULL`
- `count INTEGER NOT NULL DEFAULT 0`
- `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`
- `PRIMARY KEY (stat_date, metric)`

用聚合计数替代明细日志，控制存储增长。第一版统计这些指标：

- `login_success`
- `session_created`
- `chat_turn`
- `speech_transcribed`
- `coding_submitted`
- `session_completed`
- `session_paused`

更新方式使用 SQLite upsert：

```sql
INSERT INTO daily_usage_stats (stat_date, metric, count, updated_at)
VALUES (date('now'), ?, 1, datetime('now'))
ON CONFLICT(stat_date, metric)
DO UPDATE SET count = count + 1, updated_at = datetime('now');
```

只记录聚合值，不记录用户 ID、消息内容、语音文本或代码内容。

## 管理员监控 API

新增接口：

```http
GET /api/admin/metrics/overview
GET /api/admin/presence
GET /api/admin/usage/daily?days=7
```

`overview` 返回：

- 当前在线用户数。
- 最近活跃用户数。
- active 面试数。
- paused 面试数。
- 今日新增面试数。
- 今日对话轮数。
- 今日语音转写次数。
- 今日手撕提交次数。

`presence` 返回最近 15 分钟内活跃用户：

- `username`
- `status`: `online` 或 `recent`
- `current_view`
- `active_session_id`
- `last_seen_at`

`usage/daily` 返回最近 N 天聚合指标，`days` 限制在 1-30 之间。

## 管理员前端页面

新增管理员应用壳：

- 未登录访问 `/admin` 时展示或跳转到 `/admin/login`。
- 已登录访问 `/admin/login` 时进入 `/admin`。
- 管理员页面与普通用户页面视觉风格保持同一产品气质，但布局更偏运维面板。

监控首页内容：

- 顶部：后台名称、当前管理员、退出按钮。
- 关键指标卡：在线用户、最近活跃、进行中面试、今日对话。
- 在线列表：用户名、状态、所在页面、最近活跃时间。
- 今日使用统计：登录、面试创建、聊天、语音、手撕提交。
- 最近 7 天趋势：先用简洁表格或 CSS 条形展示。

移动端后台第一版只保证可用，不优先深度美化。管理员后台主要面向桌面运维使用。

## 安全边界

- 管理员账号和普通用户账号完全分离。
- 管理员认证使用独立 cookie 和独立 JWT secret。
- `/api/admin/...` 不接受普通用户 token。
- 管理页不展示敏感正文：不展示简历正文、面试消息全文、代码全文、语音文本、cookie、密码哈希。
- 管理员登录接口增加限流，避免暴力尝试。
- 管理员创建命令不在 shell 参数中传入密码，避免进入历史记录。
- 后台页面不暴露单独端口，继续由现有 HTTPS 入口提供。

## 资源影响

运行时资源影响很低：

- 不新增容器和常驻服务。
- heartbeat 默认 90 秒一次，小规模用户下 SQLite 写入压力很低。
- 使用统计只写聚合计数，表增长速度按“天 x 指标数”增长，不随请求数线性增长。
- 管理后台只在管理员访问时读取统计，不持续轮询高频数据。

建议第一版管理页自动刷新间隔不低于 30 秒，也可以先不自动刷新，只提供手动刷新按钮。

## 验证计划

- 创建管理员账号后，可以登录 `/admin/login`。
- 普通用户账号不能登录管理员后台。
- 未登录访问 `/api/admin/metrics/overview` 返回 `401`。
- 普通用户 cookie 访问管理员 API 返回 `401` 或 `403`。
- 管理员登录后可以获取 overview、presence 和 daily usage。
- 普通用户登录后 heartbeat 更新 `user_presence`。
- 用户创建面试、发送消息、语音转写、提交代码后，`daily_usage_stats` 对应指标增加。
- `npm run lint`、`npm run build`、后端测试通过。
- 检查数据库表增长符合预期，没有保存敏感正文。

## 实施顺序建议

1. 后端配置、管理员表、管理员认证和命令行创建账号。
2. 轻量 presence 表、heartbeat API 和前端 heartbeat。
3. daily usage 聚合表和关键业务事件计数。
4. 管理员监控 API。
5. `/admin/login` 和 `/admin` 前端页面。
6. 验证权限隔离、资源消耗和部署影响。

