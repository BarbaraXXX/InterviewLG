# RAG Data Pipeline

Offline tools for collecting public interview-question pages, preserving raw
source data, extracting `QuestionCard` records with DeepSeek, and producing
domain-split JSONL files that can later be imported into `interview-vectordb`.

This directory is intentionally separate from the deployed services. It should
run locally or in a temporary job, not as a long-running server process.

## Data Model

The final JSONL contains one `QuestionCard` per line:

```json
{
  "id": "stable-card-id",
  "domain": ["backend", "redis"],
  "topic": "Redis persistence",
  "question": "Redis 的 RDB 和 AOF 有什么区别？",
  "answer_outline": ["RDB 是快照持久化", "AOF 是追加日志"],
  "followups": ["线上环境你会怎么选择 RDB 和 AOF？"],
  "tags": ["redis", "rdb", "aof"],
  "difficulty": "",
  "source_url": "https://...",
  "source_title": "..."
}
```

`difficulty` and `followups` may be empty. The first extraction pass is
conservative: it extracts question anchors that exist in the source page, and it
does not invent missing questions or follow-ups.

## Pipeline

```text
source config
  -> fetch raw HTML into data/raw
  -> discover whitelisted child pages
  -> normalize HTML into document blocks
  -> split cleaned documents into evidence-bearing chunks
  -> extract source-derived question cards with DeepSeek
  -> write domain-split final JSONL
```

Raw data is preserved under `data/raw`. By default, reruns reuse the cached raw
HTML. Use `--refresh` only when you intentionally want to fetch the source page
again.

The main extraction path is LLM-based: rules only clean the page body and create
semantic chunks. DeepSeek receives each chunk and returns a JSON object with a
`cards` array. Each extracted card must include `evidence_block_ids`, which are
stored in audit files but omitted from the final JSONL.

## Usage

From this directory:

Useful commands:

```bash
python3 run.py fetch
python3 run.py prepare
python3 run.py extract --limit 3
python3 run.py build --limit 3
python3 run.py split
python3 run.py all
python3 run.py all --sources config/xiaolin_sources.json
```

`prepare` is local-only and does not call DeepSeek. `extract`, `build`, and
`all` call DeepSeek for chunks that are not already cached. Run with `--limit`
first to inspect a small batch before full extraction.

Outputs:

```text
data/raw/                 raw HTML + metadata, preserved locally
data/normalized/          normalized document blocks
data/chunks/              cleaned document chunks with block ids
data/extracted/           final extracted QuestionCard JSONL
data/extracted_audit/     extracted cards with chunk/evidence metadata
data/llm_extract_cache/   cached DeepSeek chunk extraction responses
data/enriched/            optional post-processing output
data/llm_cache/           optional per-card DeepSeek enrichment cache
data/output/question_cards/<domain>.jsonl
data/output/manifest.json
```

## DeepSeek Enrichment

Create a local `.env` from `.env.example`:

```bash
cp .env.example .env
```

Then fill in:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

Run a small extraction batch first:

```bash
python3 run.py prepare
python3 run.py extract --limit 3
python3 run.py split
```

`extract` asks DeepSeek to produce one or more QuestionCards from each cleaned
chunk. It fills `domain`, `topic`, `question`, `answer_outline`, `followups`,
`tags`, and `difficulty` in one pass. Responses are cached under
`data/llm_extract_cache`; use `--force-extract` only when you intentionally want
to request the same chunks again.

`enrich` still exists as an optional second pass for already extracted cards, but
it is not part of the normal `all` flow.

Final files are split by `domain[0]`, for example:

```text
data/output/question_cards/backend.jsonl
data/output/question_cards/cpp.jsonl
data/output/question_cards/agent.jsonl
```

## Adding Sources

Add a source entry to `config/xiaolin_sources.json`:

```json
{
  "id": "xiaolin_cpp_interview",
  "url": "https://www.xiaolincoding.com/interview/cpp.html",
  "adapter": "xiaolin",
  "domain": ["cpp"],
  "tags": ["xiaolincoding", "cpp"]
}
```

The `xiaolin` adapter only cleans and normalizes the page. Final card extraction
still uses the generic question-anchor extractor so that card quality remains
consistent across sources.

For index pages that should only be cached and used for link discovery, set:

```json
{
  "extract": false,
  "discover_prefixes": ["/ai/agent/", "/ai/rag/"]
}
```

Discovered pages inherit the parent source's `domain`, `tags`, and `adapter`.
