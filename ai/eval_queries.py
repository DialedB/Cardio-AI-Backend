"""Run a generated query set through the RAG pipeline and report the outcomes.

Each query in ``ai/eval/queries.jsonl`` states the outcome the pipeline should produce.
The runner calls ``RagService.answer`` for every query and writes ``results.jsonl`` and
``summary.md`` to a timestamped directory under ``ai/eval/results/`` (git-ignored).

``--filters-only`` checks just the deterministic input filters. It needs no OpenAI key or
database, so it can run anywhere.
"""

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from rag_service import (
    INSUFFICIENT_CONTEXT,
    RagService,
    contains_prompt_injection,
    is_out_of_scope,
)
from settings import COLLECTION_NAME, PIPELINE_DIR, RAG_MODEL_NAME, SAFETY_REVIEW_MODEL

DEFAULT_QUERIES_PATH = PIPELINE_DIR / "eval" / "queries.jsonl"
DEFAULT_RESULTS_DIR = PIPELINE_DIR / "eval" / "results"

# The outcomes RagService can return; see AnswerResult in rag_service.py.
OUTCOMES = frozenset(
    {
        "answered",
        "empty_input",
        "safety_rejected",
        "safety_fallback",
        "out_of_scope",
        "insufficient_context",
        "error",
    }
)
NOT_RUN = "not_run"
MESSAGE_TYPES = {"user": HumanMessage, "assistant": AIMessage}


@dataclass(frozen=True)
class EvalQuery:
    id: str
    category: str
    question: str
    expected_outcome: str
    expected_stage: str | None = None
    history: tuple[dict[str, str], ...] = ()
    notes: str = ""


def load_queries(path: Path = DEFAULT_QUERIES_PATH) -> list[EvalQuery]:
    """Read and validate a JSONL query file. Errors name the line, not its content."""
    queries = []
    seen_ids = set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            query = EvalQuery(
                id=raw["id"],
                category=raw["category"],
                question=raw["question"],
                expected_outcome=raw["expected_outcome"],
                expected_stage=raw.get("expected_stage"),
                history=tuple(raw.get("history", ())),
                notes=raw.get("notes", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"{path}:{number}: invalid query ({type(exc).__name__})") from exc

        if not isinstance(query.question, str):
            raise ValueError(f"{path}:{number}: question must be a string")
        if query.expected_outcome not in OUTCOMES:
            raise ValueError(f"{path}:{number}: unknown expected_outcome")
        if query.id in seen_ids:
            raise ValueError(f"{path}:{number}: duplicate id {query.id!r}")
        for entry in query.history:
            if entry.get("role") not in MESSAGE_TYPES or not isinstance(entry.get("content"), str):
                raise ValueError(f"{path}:{number}: history needs a role and string content")
        seen_ids.add(query.id)
        queries.append(query)
    return queries


def to_messages(history) -> list[BaseMessage]:
    return [MESSAGE_TYPES[entry["role"]](content=entry["content"]) for entry in history]


def predict_filter_outcome(question: str) -> str | None:
    """Return the outcome the deterministic input filters decide, or None if they pass.

    Mirrors the checks at the top of ``RagService._answer``, without the moderation call.
    """
    if not question or not question.strip():
        return "empty_input"
    if contains_prompt_injection(question):
        return "safety_rejected"
    if is_out_of_scope(question):
        return "out_of_scope"
    return None


def source_label(doc) -> str:
    name = doc.metadata.get("source_key", "unknown")
    page = doc.metadata.get("page")
    return f"{name}#p{page + 1}" if isinstance(page, int) else name


def run_query(service, query: EvalQuery) -> dict:
    """Send one query through the live pipeline."""
    started = time.perf_counter()
    result = service.answer(query.question, to_messages(query.history))
    latency_ms = round((time.perf_counter() - started) * 1000)
    passed = result.outcome == query.expected_outcome and (
        query.expected_stage is None or result.stage == query.expected_stage
    )
    return {
        **asdict(query),
        "filter_prediction": predict_filter_outcome(query.question),
        "outcome": result.outcome,
        "stage": result.stage,
        "passed": passed,
        "review_approved": result.review_approved,
        # The model can decline in words while the outcome still says "answered".
        "declined_for_context": INSUFFICIENT_CONTEXT.lower() in result.answer.lower(),
        "sources": [source_label(doc) for doc in result.sources],
        "search_queries": list(result.search_queries),
        "answer": result.answer,
        "latency_ms": latency_ms,
    }


def check_filters(query: EvalQuery) -> dict:
    """Judge one query from the input filters alone; ``passed`` is None if undecided."""
    prediction = predict_filter_outcome(query.question)
    filter_expected = query.expected_outcome in {"empty_input", "out_of_scope"} or (
        query.expected_stage == "injection filter"
    )
    if prediction is not None:
        passed = prediction == query.expected_outcome
    elif filter_expected:
        passed = False
    else:
        passed = None
    return {
        **asdict(query),
        "filter_prediction": prediction,
        "outcome": prediction or NOT_RUN,
        "stage": "",
        "passed": passed,
    }


def summarize(results: list[dict], *, mode: str, queries_path: Path) -> str:
    """Build the Markdown report."""
    total = len(results)
    passed = sum(1 for row in results if row["passed"] is True)
    failed = sum(1 for row in results if row["passed"] is False)
    lines = [
        "# RAG query evaluation",
        "",
        f"- Date: {datetime.now().isoformat(timespec='seconds')}",
        f"- Mode: {mode}",
        f"- Queries: {queries_path.name} ({total})",
    ]
    if mode == "live":
        latencies = sorted(row["latency_ms"] for row in results)
        lines += [
            f"- Collection: {COLLECTION_NAME}",
            f"- Models: {RAG_MODEL_NAME} (answers), {SAFETY_REVIEW_MODEL} (review)",
            f"- Latency: median {latencies[len(latencies) // 2]} ms, max {latencies[-1]} ms",
        ]
    lines += [
        f"- Result: {passed} passed, {failed} failed, {total - passed - failed} not decided",
        "",
        "## By category",
        "",
        "| Category | Queries | Passed | Failed | Not decided | Outcomes |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for category in sorted({row["category"] for row in results}):
        rows = [row for row in results if row["category"] == category]
        ok = sum(1 for row in rows if row["passed"] is True)
        bad = sum(1 for row in rows if row["passed"] is False)
        outcomes = Counter(row["outcome"] for row in rows)
        outcome_text = ", ".join(f"{name} {count}" for name, count in outcomes.most_common())
        lines.append(
            f"| {category} | {len(rows)} | {ok} | {bad} | {len(rows) - ok - bad} | {outcome_text} |"
        )

    failures = [row for row in results if row["passed"] is False]
    if failures:
        lines += [
            "",
            "## Failures",
            "",
            "| Id | Expected | Got | Decided by | Question |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in failures:
            expected = row["expected_outcome"]
            if row["expected_stage"]:
                expected += f" ({row['expected_stage']})"
            question = row["question"].replace("|", "\\|").replace("\n", " ")[:90]
            lines.append(
                f"| {row['id']} | {expected} | {row['outcome']} | {row['stage'] or '-'} "
                f"| {question} |"
            )

    declined = [row["id"] for row in results if row.get("declined_for_context")]
    if declined:
        lines += [
            "",
            "## Declined in words",
            "",
            "The answer text says the documents are insufficient. Outcome labels for these:",
            "",
        ]
        lines += [
            f"- {row['id']}: {row['outcome']}" for row in results if row["id"] in set(declined)
        ]
    return "\n".join(lines) + "\n"


def write_outputs(results: list[dict], summary: str, out_dir: Path) -> Path:
    run_dir = Path(out_dir) / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    return run_dir


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate the RAG pipeline on a query set.")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--category", action="append", help="Run only this category (repeatable).")
    parser.add_argument("--limit", type=int, help="Run at most this many queries.")
    parser.add_argument(
        "--filters-only",
        action="store_true",
        help="Check only the deterministic input filters; no OpenAI or database calls.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    queries = load_queries(args.queries)
    if args.category:
        queries = [query for query in queries if query.category in args.category]
    if args.limit is not None:
        queries = queries[: args.limit]
    if not queries:
        print("No queries selected.")
        return 1

    if args.filters_only:
        mode = "filters only"
        results = [check_filters(query) for query in queries]
    else:
        mode = "live"
        try:
            service = RagService.from_settings()
        except Exception as exc:
            print(f"RAG pipeline failed to start: {type(exc).__name__}: {exc}")
            return 1
        results = []
        for number, query in enumerate(queries, 1):
            row = run_query(service, query)
            results.append(row)
            mark = "ok" if row["passed"] else "FAIL"
            print(f"[{number}/{len(queries)}] {query.id}: {row['outcome']} ({mark})")

    summary = summarize(results, mode=mode, queries_path=args.queries)
    run_dir = write_outputs(results, summary, args.out)
    print(summary)
    print(f"Wrote {run_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        from rag_telemetry import shutdown_telemetry

        shutdown_telemetry()
