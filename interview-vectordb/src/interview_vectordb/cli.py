import json
import sys
from pathlib import Path

from interview_vectordb.db import ProfileDB
from interview_vectordb.logging_config import setup_logging
from interview_vectordb.schema import InterviewExperience


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _import_path(path: Path) -> None:
    if not path.exists():
        print(f"Path not found: {path}")
        return
    if path.is_file() and path.suffix == ".json":
        _import_file(path)
    elif path.is_dir():
        for f in sorted(path.glob("*.json")):
            _import_file(f)
    else:
        print(f"Unsupported path: {path}")


def _import_file(path: Path) -> None:
    db = ProfileDB()
    data = _load_json(path)
    if isinstance(data, dict):
        data = [data]
    exps = [InterviewExperience(**e) for e in data]
    ids = db.add_experiences(exps)
    print(f"Imported {len(ids)} experiences from {path.name}")


def _start_server() -> None:
    import uvicorn

    from interview_vectordb.api import api_app
    from interview_vectordb.config import mcp_server_settings
    from interview_vectordb.server import mcp

    mcp_app = mcp.streamable_http_app()
    api_app.mount("/mcp", mcp_app)
    uvicorn.run(api_app, host="0.0.0.0", port=mcp_server_settings.port)


def _build_question_card_store():
    from interview_vectordb.config import embedding_settings
    from interview_vectordb.db import _QUESTION_CARDS_DB_PATH
    from interview_vectordb.embeddings import build_embedding_provider
    from interview_vectordb.question_cards import QuestionCardStore

    return QuestionCardStore(_QUESTION_CARDS_DB_PATH, build_embedding_provider(embedding_settings))


def _build_coding_problem_store():
    from interview_vectordb.coding_problems import CodingProblemStore
    from interview_vectordb.config import embedding_settings
    from interview_vectordb.db import _CODING_PROBLEMS_DB_PATH
    from interview_vectordb.embeddings import build_embedding_provider

    return CodingProblemStore(_CODING_PROBLEMS_DB_PATH, build_embedding_provider(embedding_settings))


def _import_question_cards(path: Path) -> None:
    from interview_vectordb.config import embedding_settings
    from interview_vectordb.question_cards import load_question_cards_from_path

    cards = load_question_cards_from_path(path)
    store = _build_question_card_store()
    stats = store.import_cards(cards, batch_size=embedding_settings.batch_size, replace=True)
    payload = {
        "embedding": {
            "provider": embedding_settings.provider,
            "base_url": embedding_settings.base_url,
            "model": embedding_settings.model,
            "dimensions": embedding_settings.dimensions,
            "batch_size": embedding_settings.batch_size,
            "external_api": embedding_settings.provider.strip().lower() not in {"deterministic", "fake", "local"},
        },
        "input_cards": len(cards),
        **stats,
        "total": store.count(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _import_coding_problems(path: Path) -> None:
    from interview_vectordb.coding_problems import load_coding_problems_from_path
    from interview_vectordb.config import embedding_settings

    problems = load_coding_problems_from_path(path)
    store = _build_coding_problem_store()
    stats = store.import_problems(problems, batch_size=embedding_settings.batch_size, replace=True)
    payload = {
        "embedding": {
            "provider": embedding_settings.provider,
            "base_url": embedding_settings.base_url,
            "model": embedding_settings.model,
            "dimensions": embedding_settings.dimensions,
            "batch_size": embedding_settings.batch_size,
            "external_api": embedding_settings.provider.strip().lower() not in {"deterministic", "fake", "local"},
        },
        "input_problems": len(problems),
        **stats,
        "total": store.count(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _search_question_cards(query: str, domain: list[str]) -> None:
    store = _build_question_card_store()
    cards = store.search(query, domain=domain, top_k=5)
    print(json.dumps({"cards": cards}, ensure_ascii=False, indent=2))


def _search_coding_problems(query: str) -> None:
    store = _build_coding_problem_store()
    problems = store.search(query, top_k=5)
    print(json.dumps({"problems": problems}, ensure_ascii=False, indent=2))


def main() -> None:
    setup_logging()
    if len(sys.argv) < 2:
        _start_server()
        return

    cmd = sys.argv[1]

    if cmd == "import":
        if len(sys.argv) < 3:
            print("Usage: interview-vectordb import <path>")
            sys.exit(1)
        _import_path(Path(sys.argv[2]))

    elif cmd == "profile":
        if len(sys.argv) < 4:
            print("Usage: interview-vectordb profile <company> <position>")
            sys.exit(1)
        db = ProfileDB()
        company, position = sys.argv[2], sys.argv[3]
        profile = db.get_or_generate_profile(company, position)
        print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))

    elif cmd == "list":
        db = ProfileDB()
        profiles = db.list_profiles()
        print(json.dumps([p.model_dump() for p in profiles], ensure_ascii=False, indent=2))

    elif cmd == "serve":
        _start_server()

    elif cmd == "import-cards":
        if len(sys.argv) < 3:
            print("Usage: interview-vectordb import-cards <jsonl-file-or-directory>")
            sys.exit(1)
        _import_question_cards(Path(sys.argv[2]))

    elif cmd == "import-coding-problems":
        if len(sys.argv) < 3:
            print("Usage: interview-vectordb import-coding-problems <jsonl-file-or-directory>")
            sys.exit(1)
        _import_coding_problems(Path(sys.argv[2]))

    elif cmd == "search-cards":
        if len(sys.argv) < 3:
            print("Usage: interview-vectordb search-cards <query> [domain ...]")
            sys.exit(1)
        _search_question_cards(sys.argv[2], sys.argv[3:])

    elif cmd == "search-coding-problems":
        if len(sys.argv) < 3:
            print("Usage: interview-vectordb search-coding-problems <query>")
            sys.exit(1)
        _search_coding_problems(sys.argv[2])

    elif cmd == "regen":
        db = ProfileDB()
        results = db.batch_generate_profiles()
        print(f"Generated {len(results)} profiles")
        for key, profile in results.items():
            print(f"  {key}: {profile.difficulty_tendency}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
