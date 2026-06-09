# interview-vectordb

面经偏好聚合、QuestionCard RAG 与手撕题库检索服务。

- 从非结构化面经中提取公司/岗位的面试风格 Profile，供 Agent 注入系统提示词。
- 导入 RAG QuestionCard，生成 embedding，并提供语义检索 API，供 Agent 按需检索真实面试题参考。
- 导入 CodingProblem，生成 embedding，并提供结构过滤 + 语义排序的手撕题库检索。

## 架构

```
src/interview_vectordb/
  __main__.py     入口              REST + MCP 双模式服务
  cli.py          CLI               import / regen / list / profile 命令
  api.py          REST API          FastAPI
  server.py       MCP Server        FastMCP，4 个工具
  db.py           ProfileDB         JSON 文件存储 + LLM 分层聚合
  question_cards.py QuestionCardStore SQLite 存储 + 向量检索
  coding_problems.py CodingProblemStore SQLite 存储 + 向量检索
  embeddings.py   EmbeddingProvider  deterministic / OpenAI-compatible
  schema.py       数据模型          InterviewExperience + InterviewProfile + QuestionCard + CodingProblem
  config.py       配置               LLMSettings / EmbeddingSettings / MCPServerSettings

data/
  experiences/    面经原始文件        {company}_{position}_{uuid}.json
  profiles/       聚合后的 Profile   {company}_{position}.json
  question_cards/ RAG SQLite         question_cards.sqlite3
  coding_problems/ 手撕题库 SQLite    coding_problems.sqlite3
```

## 数据模型

### InterviewExperience（输入）
```python
company: str       # 公司名
position: str      # 岗位名
raw_text: str      # 非结构化面经文本，任意格式
```

### InterviewProfile（输出）
```python
company: str              # 公司名
position: str             # 岗位名
difficulty_tendency: str  # 难度倾向 junior/mid/senior
focus_areas: list[str]    # 考查重点领域
interview_style: str      # 面试风格描述
question_types: list[str] # 常见问题类型
key_traits: list[str]     # 区分性特征
source_count: int         # 聚合来源面经数量
```

### QuestionCard（RAG 输入）
```python
id: str
domain: list[str]
topic: str
question: str
answer_outline: list[str]
followups: list[str]
tags: list[str]
difficulty: str
source_url: str
source_title: str
```

### CodingProblem（手撕题库输入）
```python
id: str
title: str
difficulty: str          # easy/medium/hard
importance: str          # hot100/high/normal
answer_mode: str         # core/acm
topics: list[str]
tags: list[str]
statement: str
constraints: list[str]
examples: list[dict]     # input/output/explanation
starter_code: dict[str, str]
source_url: str
source_title: str
```

## 聚合策略

LLM 分层聚合，控制单次 token 消耗：

| 面经数量 | 策略 | LLM 调用次数 |
|---|---|---|
| 1 份 | 直接生成 Profile | 1 |
| 2-5 份 | 逐份提取摘要 → 合并生成 | N+1 |
| 6+ 份 | 逐份摘要 → 分组合并 → 最终聚合 | N + ⌈N/5⌉ + 1 |

## 调试

### 基础操作

```bash
cd interview-vectordb
uv sync

# 导入面经（单个 JSON 文件或目录）
uv run interview-vectordb import /path/to/experiences/

# 生成所有 Profile
uv run interview-vectordb regen

# 查看已有 Profile
uv run interview-vectordb list

# 查看指定 Profile
uv run interview-vectordb profile 字节跳动 后端工程师

# 启动服务
uv run interview-vectordb          # REST (9000) + MCP (9000/mcp)
```

### QuestionCard RAG

本地无 key 验证使用 deterministic embedding，不会调用外部 API：

```bash
EMBEDDING_PROVIDER=deterministic EMBEDDING_DIMENSIONS=64 \
  uv run interview-vectordb import-cards ../rag-data-pipeline/data/output/question_cards

EMBEDDING_PROVIDER=deterministic EMBEDDING_DIMENSIONS=64 \
  uv run interview-vectordb search-cards "redis zset 跳表" redis
```

真实导入建议使用 DashScope `text-embedding-v4`：

```bash
EMBEDDING_PROVIDER=dashscope
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=your-dashscope-api-key
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=10
```

然后执行：

```bash
uv run interview-vectordb import-cards ../rag-data-pipeline/data/output/question_cards
uv run interview-vectordb search-cards "redis zset 跳表" redis
```

### CodingProblem 手撕题库

本地无 key 验证使用 deterministic embedding：

```bash
EMBEDDING_PROVIDER=deterministic EMBEDDING_DIMENSIONS=64 \
  uv run interview-vectordb import-coding-problems /path/to/coding-problems

EMBEDDING_PROVIDER=deterministic EMBEDDING_DIMENSIONS=64 \
  uv run interview-vectordb search-coding-problems "链表 指针 反转"
```

真实导入使用同一套 DashScope embedding 配置，然后执行：

```bash
uv run interview-vectordb import-coding-problems /path/to/coding-problems
uv run interview-vectordb search-coding-problems "双指针 边界处理 medium"
```

### .env 配置

```bash
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
MCP_SERVER_PORT=9000
VECTORDB_ADMIN_TOKEN=change-me

EMBEDDING_PROVIDER=dashscope
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=10
```

### REST API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/profiles` | GET | 列出所有 Profile（摘要） |
| `/api/profiles/{company}/{position}` | GET | 获取/生成 Profile |
| `/api/profiles/{company}/{position}` | DELETE | 删除 Profile |
| `/api/profiles/{company}/{position}/generate` | POST | 强制重新生成 |
| `/api/experiences/count` | GET | 按公司/岗位统计面经数 |
| `/api/experiences/import` | POST | 批量导入面经 |
| `/api/question-cards/stats` | GET | QuestionCard 数量和 domain 统计 |
| `/api/question-cards/search` | POST | 语义检索 QuestionCard |
| `/api/coding-problems/stats` | GET | CodingProblem 数量和字段统计 |
| `/api/coding-problems/search` | POST | 检索手撕题库 |
| `/api/coding-problems/{problem_id}` | GET | 获取单道手撕题完整内容 |

QuestionCard search 请求示例：

```json
{
  "query": "Redis zset 跳表底层实现",
  "domain": ["redis"],
  "top_k": 5,
  "min_score": 0.0
}
```

CodingProblem search 请求示例：

```json
{
  "query": "链表 指针 反转",
  "difficulty": ["easy"],
  "importance": ["hot100"],
  "answer_mode": ["core"],
  "topics": ["linked_list"],
  "exclude_ids": [],
  "top_k": 5,
  "min_score": 0.0
}
```

### MCP 工具

| 工具 | 说明 |
|---|---|
| `get_profile(company, position)` | 获取 Profile（不存在则自动生成） |
| `list_profiles()` | 列出所有 Profile |
| `delete_profile(company, position)` | 删除 Profile |
| `batch_generate_profiles()` | 批量重新生成 |

### 验证检查

```bash
# 检查导入
uv run python -c "from interview_vectordb.db import ProfileDB; print('OK')"

# 检查 LLM 配置
uv run python -c "from interview_vectordb.config import llm_settings; print(f'{llm_settings.model} @ {llm_settings.base_url}')"

# 检查 REST API
uv run python -c "
from interview_vectordb.api import api_app
routes = [r.path for r in api_app.routes if hasattr(r, 'path')]
print(routes)
"

# 检查已有数据
uv run python -c "
from interview_vectordb.db import ProfileDB
db = ProfileDB()
exps = db._load_all_experiences()
from collections import Counter
keys = Counter((e.company, e.position) for e in exps)
for (c, p), n in keys.items():
    print(f'  {c}/{p}: {n} experiences')
"
```

### 面经文件格式

每份面经一个 JSON 文件，格式：
```json
{
  "company": "字节跳动",
  "position": "后端工程师",
  "raw_text": "字节后端二面，面官上来问了三个系统设计题..."
}
```

文件命名规则：`{company}_{position}_{uuid}.json`（由系统自动生成，导入时无需关心）。

也支持导入包含数组的 JSON 文件：
```json
[
  {"company": "字节", "position": "后端", "raw_text": "..."},
  {"company": "腾讯", "position": "前端", "raw_text": "..."}
]
```

## 测试

### 运行

```bash
cd interview-vectordb
uv sync --group dev

# 运行全部测试
uv run pytest tests/ -v

# 带覆盖率
uv run pytest tests/ --cov=interview_vectordb --cov-report=term-missing

# Lint
uv run ruff check src tests
```

### 测试结构

```
tests/
├── conftest.py          # 环境隔离：自动注入测试用 env vars + tmp_path 目录
├── test_schema.py       #  6 tests — Pydantic 模型默认值/校验/max_length 约束
├── test_db.py           # 23 tests — CRUD/LLM mock/聚合策略/markdown fence/批量生成
├── test_api.py          # 12 tests — REST 全端点/路径校验/错误处理
└── test_config.py       #  4 tests — 配置默认值/环境覆盖/空 key 强制转换
```

### 隔离策略

- **环境变量**：覆盖 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`，不读真实 `.env`
- **文件系统**：`data/`/`profiles/`/`experiences/` 全部指向 `tmp_path`
- **LLM 调用**：mock `OpenAI.chat.completions.create`，返回预设 JSON，不发起真实 API 请求
- **API 测试**：使用 `httpx.AsyncClient` + `ASGITransport` 直接调 FastAPI，不启动 uvicorn

### 关键模块覆盖率

| 模块 | 覆盖率 | 说明 |
|---|---|---|
| `schema.py` | 100% | 数据模型校验 |
| `api.py` | 97% | REST 端点全覆盖 |
| `db.py` | 84% | ProfileDB CRUD + 聚合策略（mock LLM） |
| `config.py` | 93% | 配置解析 |
| `__main__.py` | 0% | 入口脚本，需集成测试 |
| `cli.py` | 0% | CLI 交互，需集成测试 |
