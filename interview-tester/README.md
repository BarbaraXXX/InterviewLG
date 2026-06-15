# Interview Tester

面试 Agent 自动化测试工具。通过模拟不同行为模式的 AI 候选人与面试 Agent 对话，记录完整面试过程，并从多个维度评估面试 Agent 的表现。支持批量套件测试、JD/Profile 集成验证和候选人行为模式挑战。

## 架构

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  测试 Agent   │────▶│  面试 Agent       │────▶│ interview-vectordb│
│  (Candidate)  │◀────│  (Interviewer)   │◀────│  Profile REST API │
│  5种行为模式   │     │  LangGraph Agent  │     └──────────────────┘
└──────┬───────┘     └──────────────────┘
       │                      │
       ▼                      ▼
┌──────────────┐     ┌──────────────────┐
│  评估 Agent   │     │  面试记录 (JSON)  │
│  (Evaluator)  │     │  data/sessions/  │
│  8维度评分     │     │  套件汇总 JSON    │
└──────────────┘     └──────────────────┘
```

**工作流程**：
1. 配置测试参数（领域、难度、候选人行为模式、JD、Profile）
2. 测试 Agent 以"你好，我准备好面试了"开场
3. 面试 Agent 提问 → 测试 Agent 模拟候选人回答 → 面试 Agent 追问 → 循环
4. 检测到面试结束信号后，评估 Agent 对整场面试进行多维度评估
5. 结果保存为 JSON 文件；套件测试额外生成汇总统计

## 项目结构

```
interview-tester/
├── src/interview_tester/
│   ├── main.py          # CLI 入口，单次测试 + 套件测试
│   ├── server.py        # FastAPI Web 服务，SSE 流式输出
│   ├── candidate.py     # 候选人 Agent，5种行为模式
│   ├── evaluator.py     # 评估 Agent，8维度动态评分
│   ├── suite.py         # 测试套件系统，YAML定义 + 矩阵展开 + 汇总统计
│   ├── utils.py         # 共享工具函数（JD/Profile格式化、结束检测等）
│   ├── recorder.py      # 会话记录器，保存 JSON
│   ├── schemas.py       # 数据模型（TestConfig, Evaluation, TestSuite, SuiteSummary）
│   └── config.py        # 配置管理，读取 .env
├── suites/              # 预置测试套件 YAML
│   ├── quick_coverage.yaml
│   ├── full_coverage.yaml
│   ├── jd_profile_test.yaml
│   └── style_challenge.yaml
├── web/
│   └── index.html       # Web 前端 SPA（单文件，无构建步骤）
├── data/sessions/       # 测试会话 JSON 输出目录
├── pyproject.toml       # 项目依赖和入口
└── .env.example         # 环境变量示例
```

## 快速开始

### 前置条件

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) 包管理器
- 有效的 LLM API Key（配置在 `../interview-agent/.env`）

### 安装

```bash
cd interview-tester
uv sync
```

### 运行

**CLI 单次测试**：

```bash
uv run interview-tester --domain backend --difficulty mid --candidate-level mid
```

**CLI 套件测试**：

```bash
uv run interview-tester --suite suites/quick_coverage.yaml
```

**Web 模式**：

```bash
uv run interview-tester-server
```

浏览器打开 http://localhost:8765

## 使用方式

### CLI

```bash
# 基础测试：后端 + 中级 + 配合型候选人
uv run interview-tester --domain backend --difficulty mid --candidate-level mid

# 行为模式测试：回避型候选人（测试面试官追问能力）
uv run interview-tester --domain backend --difficulty mid --candidate-style evasive

# 特定弱点测试：在分布式系统和消息队列上表现薄弱
uv run interview-tester --domain backend --candidate-style specific_weakness --weaknesses 分布式系统 消息队列

# JD + Profile 集成测试
uv run interview-tester --domain backend --jd "岗位：后端工程师，3-5年，Python/FastAPI/Redis" --profile-company 华为 --profile-position AI应用开发

# 自定义领域
uv run interview-tester --domain "游戏服务端" --difficulty senior --candidate-level senior

# 指定 LLM Provider
uv run interview-tester --domain backend --provider deepseek

# 运行测试套件
uv run interview-tester --suite suites/style_challenge.yaml
uv run interview-tester --suite suites/quick_coverage.yaml
```

**可用参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--domain` | backend | 面试领域（预设8个 + 自定义输入） |
| `--difficulty` | mid | 面试难度：junior/mid/senior |
| `--candidate-level` | mid | 候选人水平：junior/mid/senior |
| `--candidate-style` | cooperative | 候选人行为模式（见下表） |
| `--weaknesses` | [] | 特定弱点领域（仅 specific_weakness 模式） |
| `--max-rounds` | 50 | 最大对话轮次 |
| `--jd` | "" | 岗位JD文本（@file.txt 从文件读取） |
| `--profile-company` | "" | 面试偏好公司名 |
| `--profile-position` | "" | 面试偏好岗位名 |
| `--provider` | "" | LLM Provider 名称（空=默认） |
| `--suite` | "" | 测试套件YAML路径（指定后忽略其他参数） |

### 候选人行为模式

| 模式 | 行为描述 | 测试目的 |
|------|----------|----------|
| `cooperative` | 正常配合回答 | 基线测试 |
| `weak` | 回答浅显、不完整，深入问题含糊 | 测试面试官识别弱点 + 难度降级 |
| `evasive` | 绕弯子、转移话题、不正面回答 | 测试面试官追问能力 + 引导回正题 |
| `overconfident` | 自信地给错误答案、夸大经验 | 测试面试官识破错误 + 纠正能力 |
| `specific_weakness` | 指定领域弱，其余正常 | 测试面试官发现特定薄弱点 |

### Web

1. 打开 http://localhost:8765
2. 选择领域（或输入自定义领域）、难度、候选人水平、行为模式
3. 可选：输入岗位JD、选择面试偏好
4. 点击"开始测试"，实时观看面试对话
5. 面试结束后查看8维度评估结果
6. 或选择"测试套件"→ 选择预置套件 → 点击"运行套件"，批量测试并查看汇总

### 测试套件

套件用 YAML 定义，支持显式测试列表和矩阵展开两种方式：

```yaml
name: my_suite
description: 我的测试套件
pass_threshold: 7  # overall_score >= 7 视为通过

# 方式1：显式测试列表
tests:
  - domain: backend
    difficulty: mid
    candidate_level: mid
    candidate_style: cooperative
    job_description: "后端工程师，Python/Redis"
    profile_company: "华为"
    profile_position: "AI应用开发"

# 方式2：矩阵展开（笛卡尔积）
matrix:
  domains: [backend, frontend, algorithm]
  difficulties: [junior, mid, senior]
  candidate_levels: [junior, mid, senior]
  candidate_styles: [cooperative, weak]
```

**预置套件**：

| 套件 | 文件 | 测试数 | 说明 |
|------|------|--------|------|
| quick_coverage | `quick_coverage.yaml` | 4 | 4领域×mid快速覆盖 |
| full_coverage | `full_coverage.yaml` | 144 | 8领域×3难度×2模式全覆盖 |
| jd_profile_test | `jd_profile_test.yaml` | 2 | JD+Profile集成验证 |
| style_challenge | `style_challenge.yaml` | 5 | 5种行为模式挑战 |

## 测试输出

### 单次测试

每次测试生成 `data/sessions/test_*.json`：

```json
{
  "session_id": "test_20240101_120000_1234",
  "config": {
    "domain": "backend",
    "difficulty": "mid",
    "candidate_level": "mid",
    "candidate_style": "cooperative",
    "job_description": "",
    "profile_company": "",
    "profile_position": "",
    "provider": ""
  },
  "qa_pairs": [
    {
      "round": 1,
      "question": "请介绍一下你的后端开发经验...",
      "answer": "我有大约3-5年的后端开发经验...",
      "question_timestamp": "2024-01-01T12:00:05+00:00",
      "answer_timestamp": "2024-01-01T12:00:15+00:00"
    }
  ],
  "total_rounds": 8,
  "status": "completed",
  "evaluation": {
    "style_naturalness": 7,
    "difficulty_appropriateness": 8,
    "follow_up_quality": 6,
    "topic_coverage": 7,
    "overall_score": 7,
    "jd_relevance": 0,
    "profile_relevance": 0,
    "difficulty_adaptation": 6,
    "strengths": ["追问深入", "话题覆盖广"],
    "weaknesses": ["部分追问缺乏逻辑递进"],
    "summary": "面试 Agent 整体表现良好...",
    "improvement_suggestions": ["增加场景化提问", "优化追问逻辑"]
  }
}
```

### 套件测试

额外生成 `data/sessions/suite_*.json` 汇总文件：

```json
{
  "suite_name": "style_challenge",
  "total_tests": 5,
  "completed": 5,
  "errors": 0,
  "pass_count": 3,
  "fail_count": 2,
  "pass_rate": 0.6,
  "avg_overall_score": 6.8,
  "avg_difficulty_adaptation": 5.2,
  "by_domain": {"backend": {"count": 5, "pass_rate": 0.6, "avg_score": 6.8}},
  "by_difficulty": {"mid": {"count": 5, "pass_rate": 0.6, "avg_score": 6.8}},
  "by_candidate_style": {
    "cooperative": {"count": 1, "pass_rate": 1.0, "avg_score": 8.0},
    "weak": {"count": 1, "pass_rate": 1.0, "avg_score": 7.0},
    "evasive": {"count": 1, "pass_rate": 0.0, "avg_score": 5.0}
  },
  "best_session": "test_20240101_120000_1234",
  "worst_session": "test_20240101_120100_5678"
}
```

## 评估维度

### 基础维度（始终评估）

| 维度 | 字段 | 说明 |
|------|------|------|
| 对话自然度 | `style_naturalness` | 面试官的提问和回应是否自然流畅 |
| 难度适当性 | `difficulty_appropriateness` | 问题难度是否匹配设定难度和候选人水平 |
| 追问质量 | `follow_up_quality` | 面试官根据候选人回答进行追问的质量 |
| 话题覆盖 | `topic_coverage` | 面试涉及的知识面广度 |
| 总体评分 | `overall_score` | 对面试官整体表现的综合评价（1-10 分） |
| 难度调整 | `difficulty_adaptation` | 面试官是否根据候选人表现动态调整难度 |

### 条件维度（按配置启用）

| 维度 | 字段 | 触发条件 | 说明 |
|------|------|----------|------|
| JD关联度 | `jd_relevance` | 提供了 job_description | 面试问题是否紧扣JD要求、技能和侧重 |
| 偏好匹配度 | `profile_relevance` | 提供了 profile_company + profile_position | 面试风格是否匹配Profile的偏好和重点 |

未提供JD/Profile时，对应维度评0分（表示未使用，非负面评价）。

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/test/stream` | POST | 单次测试 SSE 流 |
| `/api/suites` | GET | 列出可用测试套件 |
| `/api/suite/run` | POST | 运行套件 SSE 流 |
| `/api/sessions` | GET | 列出历史测试记录 |
| `/api/sessions/{id}` | GET | 获取测试详情 |
| `/api/profiles` | GET | 代理 vectordb 偏好列表 |

## 配置

### 环境变量

LLM 配置共享 `../interview-agent/.env`，无需重复配置。

本项目专属变量（`interview-tester/.env`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TEST_CANDIDATE_TEMPERATURE` | 0.7 | 候选人 LLM 温度，越高回答越有创造性 |
| `TEST_EVALUATOR_TEMPERATURE` | 0.3 | 评估 LLM 温度，越低评估越一致 |

### .env.example

```bash
# 候选人 LLM 温度（越高越有创造性）
TEST_CANDIDATE_TEMPERATURE=0.7
# 评估 LLM 温度（越低越一致）
TEST_EVALUATOR_TEMPERATURE=0.3
```

## 开发

### 添加新行为模式

1. 在 `candidate.py` 的 `_STYLE_PROMPTS` 字典中添加模式名和中文行为描述
2. 在 `candidate.py` 的 `_VALID_STYLES` 集合中添加模式名
3. 在 Web 前端 `web/index.html` 的 `STYLES` 常量中添加选项

### 添加新评估维度

1. 在 `schemas.py` 的 `Evaluation` 模型中添加新字段
2. 在 `evaluator.py` 的 `build_evaluator_prompt()` 中添加维度描述和 JSON 字段
3. 在 Web 前端 `web/index.html` 的 `renderEvaluation()` 评分数组中添加展示

### 添加新测试套件

在 `suites/` 目录下新建 YAML 文件，参考预置套件格式。

### 依赖关系

```
interview-tester
├── interview-agent (path dependency, 可编辑安装)
│   └── 提供: build_interview_agent(), llm_settings, parse_jd()
├── langchain-openai >= 0.3.0
├── pydantic >= 2.0.0
├── pydantic-settings >= 2.0.0
├── python-dotenv >= 1.0.0
├── fastapi >= 0.115.0
├── uvicorn >= 0.30.0
├── sse-starlette >= 2.0.0
├── httpx >= 0.27.0
└── pyyaml >= 6.0
```

## 测试

### 运行

```bash
cd interview-tester
uv sync --group dev

# 运行全部测试
uv run pytest tests/ -v

# 带覆盖率
uv run pytest tests/ --cov=interview_tester --cov-report=term-missing

# Lint
uv run ruff check src tests
```

### 测试结构

```
tests/
├── conftest.py          # 环境隔离：自动注入测试用 env vars + tmp_path 数据目录
├── test_schemas.py      #  7 tests — Pydantic 模型默认值/字段/校验
├── test_utils.py        # 19 tests — 结束检测/路径消毒/JD和Profile格式化/fetch mock
├── test_candidate.py    # 12 tests — 5种行为模式/水平等级/fallback/LLM构建
├── test_evaluator.py    # 10 tests — 评估prompt构建/维度动态/JD和Profile条件/JSON解析
├── test_suite.py        # 17 tests — 矩阵展开/YAML加载/resolve/汇总统计/分组
└── test_recorder.py     #  6 tests — QA记录/文件保存/完成/错误标记
```

### 隔离策略

- **环境变量**：覆盖 `LLM_PROVIDERS`/`AUTH_SECRET_KEY` 等，确保不读真实 `.env`
- **文件系统**：`data/sessions/` 指向 `tmp_path`，不碰生产数据
- **LLM 调用**：mock `llm_settings.get_provider()` 返回假 provider，不发起真实 API 请求
- **HTTP 请求**：mock `httpx.AsyncClient`（通过 monkeypatch），不连接真实 vectordb

### 关键模块覆盖率

| 模块 | 覆盖率 | 说明 |
|---|---|---|
| `schemas.py` | 100% | 数据模型 |
| `config.py` | 100% | 配置读取 |
| `recorder.py` | 100% | 会话记录和持久化 |
| `suite.py` | 100% | 套件加载、矩阵展开、汇总统计 |
| `utils.py` | 96% | 纯函数全覆盖（fetch_profile mock） |
| `candidate.py` | 92% | 行为模式 prompt 构建 |
| `evaluator.py` | 84% | 评估 prompt + JSON 解析（evaluate_session 需 LLM） |
| `main.py` | 0% | CLI 入口 + LLM 编排，需集成测试 |
| `server.py` | 0% | FastAPI SSE 流，需集成测试 |
