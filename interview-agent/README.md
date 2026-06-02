# interview-agent

LangGraph 面试 Agent，支持 JD 注入、面经偏好注入、JWT 认证、SSE 流式输出。

## 架构

```
web/src/                          # React 前端
  App.tsx                           LoginView / SetupView / ChatView
  api.ts                            API 调用 + SSE 流
  index.css                         暗色主题样式

src/interview_agent/
  server.py       FastAPI 入口      路由、认证、SSE、vectordb 代理
  agent.py        LangGraph 图      StateGraph(MessagesState) + MCP 工具
  prompts.py      系统提示词         build_system_prompt(domain, difficulty, jd, profile)
  session.py      会话管理          内存 Agent + SQLite 会话/消息，支持重启后重建
  db.py           SQLite 存储        users / sessions / messages
  auth.py         JWT 认证          bcrypt + HttpOnly Cookie
  config.py       配置               LLMSettings / MCPSettings / AuthSettings / VectorDBSettings
  jd_parser.py    JD 结构化          LLM 提取 StructuredJD，注入提示词
  mcp_client.py   MCP 客户端         连接外部 MCP Server
  main.py         CLI 入口          交互式命令行面试
```

## 系统提示词注入

`build_system_prompt(domain, difficulty, structured_jd, structured_profile)` 按顺序拼接：

1. **领域描述** — 预设 8 个领域或自定义
2. **难度描述** — junior/mid/senior
3. **JD 信息** — 可选，LLM 从原始 JD 提取的结构化信息
4. **面试偏好** — 可选，从 interview-vectordb 获取的 Profile
5. **面试规则 + 注意事项** — 固定模板

## 调试

### 后端

```bash
cd interview-agent
uv sync

# 启动服务（前端已构建时）
uv run interview-agent-server

# CLI 模式
uv run interview-agent

# 检查导入
uv run python -c "from interview_agent.server import app; print('OK')"

# 检查 LLM 配置
uv run python -c "from interview_agent.config import llm_settings; p=llm_settings.get_provider(); print(f'{p.model} @ {p.base_url}')"
```

### 前端

```bash
cd interview-agent/web
npm install
npm run dev          # Vite 开发服务器 (端口 5173，代理 API 到 8000)
npm run build        # 生产构建到 dist/
```

开发时用 `npm run dev`，修改前端代码实时热更新。生产模式用 `npm run build` 后由 FastAPI 静态文件服务。

### .env 关键配置

```bash
# LLM（必填）
LLM_DEFAULT_PROVIDER=deepseek
LLM_PROVIDERS={"local":{"base_url":"http://10.2.133.86:10087/v1","api_key":"","model":"Qwen_Qwen3.6-27B-Q6_K_M.gguf"},"deepseek":{"base_url":"https://api.deepseek.com/v1","api_key":"sk-xxx","model":"deepseek-chat"}}

# Profile 代理（可选，连接 vectordb REST API）
VECTORDB_BASE_URL=http://localhost:9000
VECTORDB_ADMIN_TOKEN=change-me-too

# QuestionCard RAG（可选，vectordb 不可用时自动降级）
RAG_ENABLED=true
RAG_TOP_K=3
RAG_MIN_SCORE=0.0
RAG_TIMEOUT_SECONDS=3
RAG_MAX_CONTEXT_CHARS=1800

# 认证（生产必须改）
AUTH_SECRET_KEY=change-me-in-production
AUTH_COOKIE_SECURE=false
```

### QuestionCard RAG 联调

先在 `interview-vectordb` 导入 QuestionCard：

```bash
cd interview-vectordb
uv run interview-vectordb import-cards ../rag-data-pipeline/data/output/question_cards
uv run interview-vectordb
```

再启动 Agent：

```bash
cd interview-agent
VECTORDB_BASE_URL=http://localhost:9000 RAG_ENABLED=true uv run interview-agent-server
```

面试对话中每轮最多检索 `RAG_TOP_K` 条真实面试题参考，并临时注入本轮模型上下文；这些 RAG 内容不会写入会话历史。

### 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 前端没显示新功能 | 浏览器缓存 | Cmd+Shift+R 硬刷新 |
| LLM 502 错误 | .env 未加载或 API 不可达 | 检查 `llm_settings.get_provider()` 输出 |
| 面试偏好下拉为空 | vectordb 未启动或未生成 Profile | 先启动 vectordb，运行 `regen` |
| RAG 没生效 | vectordb 未导入 QuestionCard 或 `RAG_ENABLED=false` | 检查 `GET /api/question-cards/stats` 和 app 日志 |
| 旧账号无法登录 | 用户存储已迁移到 SQLite，启动时会从旧 users.json 一次性导入 | 确认 `data/interview.db` 可写，查看启动日志 |

## Docker 部署

```bash
cd interview-agent/deploy
# 编辑 .env: LLM_DEFAULT_PROVIDER, LLM_PROVIDERS, AUTH_SECRET_KEY, SSL_DOMAIN
bash deploy.sh
```

Nginx 反代 app → 80/443，自动 Let's Encrypt 证书；vectordb 只在 Docker 内网暴露，不映射公网端口。

## 测试

### 运行

```bash
cd interview-agent
uv sync --group dev

# 运行全部测试
uv run pytest tests/ -v

# 带覆盖率
uv run pytest tests/ --cov=interview_agent --cov-report=term-missing

# Lint
uv run ruff check src tests
```

### 测试结构

```
tests/
├── conftest.py          # 环境隔离：自动注入测试用 env vars + tmp_path
├── test_auth.py         # 12 tests — 注册/登录/JWT签发/验证/过期/删除用户
├── test_session.py      # 12 tests — 会话过期/trim/CRUD/淘汰/max限制
├── test_prompts.py      # 12 tests — 领域/难度/JD/Profile注入/格式转义/注入防护
├── test_jd_parser.py    # 10 tests — 空输入/截断/LLM成功/失败/非法JSON/模型
├── test_config.py       # 10 tests — 环境变量解析/默认/命名/fallback provider
├── test_server.py       # 16 tests — 注册登录端点/域名列表/路径消毒/格式化
└── test_mcp_client.py   #  5 tests — 服务配置构建/工具获取降级
```

### 隔离策略

所有测试通过 `conftest.py` 的 `autouse` fixture 实现完全隔离：

- **环境变量**：覆盖 `LLM_PROVIDERS`/`AUTH_SECRET_KEY` 等，确保不读真实 `.env`
- **文件系统**：SQLite 测试库写入 `tmp_path`，不碰生产数据
- **LLM 调用**：mock `ChatOpenAI`，不发起真实 API 请求
- **MCP 连接**：空 `MCP_SERVER_URLS`，跳过真实连接

### 关键模块覆盖率

| 模块 | 覆盖率 | 说明 |
|---|---|---|
| `auth.py` | 97% | JWT 签发验证、bcrypt 哈希、token 过期 |
| `session.py` | 100% | 会话全生命周期：创建/获取/过期/淘汰/删除 |
| `prompts.py` | 100% | 提示词构建、转义、注入防护 |
| `jd_parser.py` | 100% | JD 结构化解析（mock LLM） |
| `logging_config.py` | 100% | 日志初始化 |
| `mcp_client.py` | 93% | MCP 工具获取降级 |
| `config.py` | 97% | 多 provider 配置解析 |
| `server.py` | 61% | SSE 流和静态文件服务需集成测试覆盖 |
