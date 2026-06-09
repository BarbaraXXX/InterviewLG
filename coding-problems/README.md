# coding-problems

离线手撕题库生成工具。它不抓取刷题平台题面，只读取你维护的题目索引，调用 OpenAI-compatible LLM 生成原创 `CodingProblem` JSONL，人工审查后再导入 `interview-vectordb`。

## 目录

```text
coding-problems/
  data/input/       题目索引，例如 hot100_index.jsonl
  data/generated/   LLM 生成的候选题库，默认不提交
  data/reviewed/    人工审查后的题库，可导入 vectordb
  src/              生成、校验、提升脚本
  run.py            CLI 入口
```

## 输入索引

`data/input/hot100_index.jsonl` 每行一题，只放低风险元信息，不放平台题面：

```json
{"source":"leetcode_hot100","source_id":"206","slug":"reverse-linked-list","title":"反转链表","difficulty":"easy","importance":"hot100","answer_mode":"core","topics":["linked_list","pointer"],"tags":["iteration","recursion"]}
```

字段说明：

- `source/source_id/slug/title`：题源映射和标题。
- `difficulty`：`easy|medium|hard`。
- `importance`：`hot100|high|normal`。
- `answer_mode`：`core|acm`。
- `topics/tags`：检索和去重用标签。

## 环境变量

复制 `.env.example`：

```bash
cp .env.example .env
```

配置：

```bash
CODING_LLM_BASE_URL=https://api.deepseek.com
CODING_LLM_API_KEY=your-api-key
CODING_LLM_MODEL=deepseek-chat
CODING_LLM_TEMPERATURE=0.2
CODING_LLM_TIMEOUT_SECONDS=60
```

也兼容 `DEEPSEEK_API_KEY` / `LLM_API_KEY`，但建议使用 `CODING_LLM_*`，避免和主服务混淆。

## 生成

先小批量生成，确认风格后再扩大：

```bash
cd coding-problems
python3 run.py generate \
  --input data/input/hot100_index.jsonl \
  --output data/generated/hot100_generated.jsonl \
  --limit 10 \
  --overwrite
```

生成结果会带 `_review` 字段：

```json
"_review":{"status":"pending","source":"leetcode_hot100","source_id":"206","slug":"reverse-linked-list","warnings":[]}
```

这个字段只给人工审查使用，不会进入最终导入文件。

## 校验

```bash
python3 run.py validate --input data/generated/hot100_generated.jsonl
```

校验内容包括：

- 必填字段是否存在。
- 枚举是否合法。
- 是否至少有一个 example。
- starter code 是否至少包含 `python` 或 `cpp`。
- 是否误带 `solution/answer/evaluation_points/complexity` 等答案字段。

## 人工审查

人工审查 `data/generated/hot100_generated.jsonl`，重点看：

- 题面是否原创、清晰、和题目标题一致。
- 样例是否自洽，且不是平台官方原样例。
- starter code 是否只是空模板。
- 是否没有标准答案、题解、复杂度分析。

审查后执行：

```bash
python3 run.py promote \
  --input data/generated/hot100_generated.jsonl \
  --output data/reviewed/hot100_reviewed.jsonl \
  --overwrite
```

`promote` 会去掉 `_review` 字段，只保留 `interview-vectordb` 可导入的 `CodingProblem`。

## 导入 vectordb

```bash
cd ../interview-vectordb
uv run interview-vectordb import-coding-problems ../coding-problems/data/reviewed
```

导入前请确认 embedding 配置，生产环境建议使用 DashScope `text-embedding-v4`。

## 注意

- 不要把刷题平台题面、官方样例、官方模板、题解复制进 input 或 reviewed。
- 题源编号只用于内部真实性映射，不建议直接展示给用户。
- 第一批建议每 10-20 道生成一次，审查 prompt 风格后再继续。
