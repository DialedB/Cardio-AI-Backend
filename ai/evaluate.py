"""Evaluate the RAG pipeline against ai/eval/questions.jsonl.

Runs every question through the real RagService several times (answers vary between
runs) and reports, per question and overall: whether the pipeline behaved as expected,
which stage decided, whether an expected source was retrieved, how many expected facts
the answer contains, and whether the answer names the expected file.

This calls OpenAI and reads Neon, so it is not part of pytest. Start with ``--list`` to
check which questions can run against the current collection, then for example:

    python evaluate.py --runs 3 --output eval/results-baseline.json
    python evaluate.py --runs 3 --compare eval/results-baseline.json

Telemetry exports are off by default so evaluation traffic stays out of the dashboards;
set CARDIO_RAG_TELEMETRY_DISABLED=false to keep them.
"""

import os

os.environ.setdefault("CARDIO_RAG_TELEMETRY_DISABLED", "true")

import argparse  # noqa: E402
import contextvars  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from dataclasses import asdict, dataclass  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from settings import (  # noqa: E402
    COLLECTION_NAME,
    DOCS_DIR,
    RAG_MODEL_NAME,
    SAFETY_REVIEW_MODEL,
    get_neon_connection_url,
)

QUESTIONS_PATH = Path(__file__).resolve().parent / "eval" / "questions.jsonl"

# What a result looks like to the user, independent of which stage produced it.
BEHAVIOURS = ("answer", "not_enough_info", "refuse_scope", "refuse_filter", "empty", "emergency")
OUTCOME_BEHAVIOUR = {
    "insufficient_context": "not_enough_info",
    "out_of_scope": "refuse_scope",
    "safety_rejected": "refuse_filter",
    "empty_input": "empty",
    "safety_fallback": "unavailable",
    "error": "unavailable",
}
NOT_ENOUGH_INFO = re.compile(r"(don't|do not) have enough information")
EMERGENCY_ADVICE = re.compile(
    r"emergency services|emergency number|call (911|112|999|an ambulance)|ambulance"
    r"|emergency (room|department)"
)
QUESTION_FIELDS = {"id", "question", "expect", "sources", "facts", "stage", "history",
                   "known_issue", "tags"}

# Approximate USD per 1M input/output tokens, for the cost estimate only. Model names in
# usage reports may carry a date suffix, so they are matched by prefix. Update as needed.
PRICES_PER_MILLION = {
    "gpt-6-astra": (10.00, 50.00),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-4o-mini": (0.15, 0.60),
}


@dataclass(frozen=True)
class RunScore:
    question_id: str
    run: int
    behaviour: str
    outcome: str
    stage: str
    passed: bool
    # None when the question has no expected sources or facts.
    source_hit: bool | None
    fact_recall: float | None
    cited: bool | None
    seconds: float
    answer: str
    retrieved_sources: tuple[str, ...]


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).lower()


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    """Load and validate the question file; raises ValueError naming the bad line."""
    questions = []
    seen = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        question = json.loads(line)
        problems = []
        if set(question) - QUESTION_FIELDS:
            problems.append(f"unknown fields {sorted(set(question) - QUESTION_FIELDS)}")
        if not isinstance(question.get("id"), str) or question["id"] in seen:
            problems.append("missing or duplicate id")
        if not isinstance(question.get("question"), str):
            problems.append("missing question")
        if question.get("expect") not in BEHAVIOURS:
            problems.append(f"expect must be one of {BEHAVIOURS}")
        if question.get("expect") == "answer" and not question.get("sources"):
            problems.append("answer questions need expected sources")
        for entry in question.get("history", []):
            if entry.get("role") not in {"user", "assistant"} or not entry.get("content"):
                problems.append("history entries need a user/assistant role and content")
        if problems:
            raise ValueError(f"{path.name} line {number}: {'; '.join(problems)}")
        seen.add(question["id"])
        questions.append(question)
    return questions


def behaviour_of(result) -> str:
    """Map an AnswerResult to what the user experienced."""
    if result.outcome == "answered":
        if NOT_ENOUGH_INFO.search(normalize(result.answer)):
            return "not_enough_info"
        return "answer"
    return OUTCOME_BEHAVIOUR.get(result.outcome, result.outcome)


def matches(fact: str, text: str) -> bool:
    """A fact is ``a|b|c``: present if any alternative appears in the text."""
    return any(alternative in text for alternative in normalize(fact).split("|"))


def score_run(question: dict, result, *, run: int = 1, seconds: float = 0.0) -> RunScore:
    behaviour = behaviour_of(result)
    answer = normalize(result.answer)
    expect = question["expect"]

    if expect == "emergency":
        passed = result.outcome == "emergency" or bool(EMERGENCY_ADVICE.search(answer))
    else:
        passed = behaviour == expect
        if passed and question.get("stage"):
            passed = result.stage == question["stage"]

    expected_sources = question.get("sources", [])
    retrieved = tuple(doc.metadata.get("source_key", "") for doc in result.sources)
    source_hit = cited = fact_recall = None
    if expected_sources:
        source_hit = any(source in retrieved for source in expected_sources)
        if behaviour == "answer":
            stems = [normalize(Path(source).stem) for source in expected_sources]
            cited = any(stem in answer for stem in stems)
    if question.get("facts") and behaviour == "answer":
        facts = question["facts"]
        fact_recall = sum(matches(fact, answer) for fact in facts) / len(facts)

    return RunScore(
        question_id=question["id"],
        run=run,
        behaviour=behaviour,
        outcome=result.outcome,
        stage=result.stage,
        passed=passed,
        source_hit=source_hit,
        fact_recall=fact_recall,
        cited=cited,
        seconds=round(seconds, 2),
        answer=result.answer,
        retrieved_sources=retrieved,
    )


def mean(values) -> float | None:
    values = [float(value) for value in values if value is not None]
    return round(sum(values) / len(values), 3) if values else None


def summarize(questions: list[dict], scores: list[RunScore]) -> dict:
    """Aggregate run scores. Known-issue questions are reported but not in the pass rate."""
    by_id = {}
    for score in scores:
        by_id.setdefault(score.question_id, []).append(score)

    per_question = {}
    for question in questions:
        runs = by_id.get(question["id"])
        if not runs:
            continue
        per_question[question["id"]] = {
            "expect": question["expect"],
            "known_issue": bool(question.get("known_issue")),
            "pass_rate": mean(run.passed for run in runs),
            "behaviours": dict(Counter(run.behaviour for run in runs)),
            "stages": dict(Counter(run.stage for run in runs)),
            "source_hit_rate": mean(run.source_hit for run in runs),
            "fact_recall": mean(run.fact_recall for run in runs),
            "citation_rate": mean(run.cited for run in runs),
            "seconds": mean(run.seconds for run in runs),
        }

    tracked = [q for q in per_question.values() if not q["known_issue"]]
    tracked_scores = [s for s in scores if not per_question[s.question_id]["known_issue"]]
    by_expect = {}
    for expect in BEHAVIOURS:
        rates = [q["pass_rate"] for q in tracked if q["expect"] == expect]
        if rates:
            by_expect[expect] = mean(rates)
    return {
        "questions": len(per_question),
        "runs": len(scores),
        "pass_rate": mean(q["pass_rate"] for q in tracked),
        "pass_rate_by_expect": by_expect,
        "source_hit_rate": mean(s.source_hit for s in tracked_scores),
        "fact_recall": mean(s.fact_recall for s in tracked_scores),
        "citation_rate": mean(s.cited for s in tracked_scores),
        "known_issues_passing": sorted(
            qid for qid, q in per_question.items() if q["known_issue"] and q["pass_rate"]
        ),
        "per_question": per_question,
    }


def estimate_cost(usage: dict) -> float | None:
    """Approximate USD for a {model: usage_metadata} map; None if a model is unpriced."""
    total = 0.0
    for model, tokens in usage.items():
        price = next(
            (p for name, p in PRICES_PER_MILLION.items() if model.startswith(name)), None
        )
        if price is None:
            return None
        total += tokens.get("input_tokens", 0) / 1e6 * price[0]
        total += tokens.get("output_tokens", 0) / 1e6 * price[1]
    return round(total, 4)


def ingested_sources() -> set[str]:
    """source_key values present in the configured collection (one read-only query)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(get_neon_connection_url())
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT DISTINCT e.cmetadata->>'source_key' FROM langchain_pg_embedding e "
                    "JOIN langchain_pg_collection c ON c.uuid = e.collection_id "
                    "WHERE c.name = :name"
                ),
                {"name": COLLECTION_NAME},
            )
            return {key for (key,) in rows if key}
    finally:
        engine.dispose()


def runnable(question: dict, available: set[str]) -> bool:
    """A question with expected sources needs at least one of them to be ingested."""
    sources = question.get("sources", [])
    return not sources or any(source in available for source in sources)


def to_history(entries):
    types = {"user": HumanMessage, "assistant": AIMessage}
    return [types[entry["role"]](content=entry["content"]) for entry in entries]


def run_evaluation(service, questions: list[dict], *, runs: int, workers: int):
    from langchain_core.callbacks import get_usage_metadata_callback

    def run_one(question, run):
        started = time.perf_counter()
        result = service.answer(question["question"], to_history(question.get("history", [])))
        return score_run(question, result, run=run, seconds=time.perf_counter() - started)

    jobs = [(question, run) for question in questions for run in range(1, runs + 1)]
    with get_usage_metadata_callback() as usage, ThreadPoolExecutor(workers) as pool:
        # Each job runs in a copy of this context so the usage callback sees its calls.
        futures = [
            pool.submit(contextvars.copy_context().run, run_one, question, run)
            for question, run in jobs
        ]
        scores = []
        for done, future in enumerate(futures, 1):
            scores.append(future.result())
            print(f"\r  {done}/{len(jobs)} runs", end="", flush=True)
        print()
        return scores, dict(usage.usage_metadata)


def format_rate(value) -> str:
    return "  -  " if value is None else f"{value:5.0%}"


def print_report(questions, summary, usage, cost, skipped) -> None:
    print(f"\n{'question':30} {'expect':15} {'pass':>5} {'src':>5} {'facts':>5} {'cited':>5}"
          "  behaviour (stage)")
    for question in questions:
        q = summary["per_question"].get(question["id"])
        if q is None:
            continue
        stages = ", ".join(f"{stage or '?'}×{n}" for stage, n in q["stages"].items())
        behaviours = ", ".join(f"{b}×{n}" for b, n in q["behaviours"].items())
        flag = " [known issue]" if q["known_issue"] else ""
        print(f"{question['id'][:30]:30} {q['expect']:15} {format_rate(q['pass_rate'])}"
              f" {format_rate(q['source_hit_rate'])} {format_rate(q['fact_recall'])}"
              f" {format_rate(q['citation_rate'])}  {behaviours} ({stages}){flag}")

    print(f"\nPass rate (excluding known issues): {format_rate(summary['pass_rate'])}")
    for expect, rate in summary["pass_rate_by_expect"].items():
        print(f"  {expect:16} {format_rate(rate)}")
    print(f"Expected source retrieved: {format_rate(summary['source_hit_rate'])}")
    print(f"Expected facts in answers: {format_rate(summary['fact_recall'])}")
    print(f"Answers naming the file:   {format_rate(summary['citation_rate'])}")
    if summary["known_issues_passing"]:
        print(f"Known issues now passing (check if fixed): {summary['known_issues_passing']}")
    if skipped:
        print(f"Skipped (expected sources not ingested): {', '.join(skipped)}")
    for model, tokens in usage.items():
        print(f"Tokens {model}: {tokens.get('input_tokens', 0)} in / "
              f"{tokens.get('output_tokens', 0)} out")
    print("Estimated cost: " + ("unknown model price" if cost is None else f"~${cost}"))


def print_comparison(summary: dict, previous: dict) -> None:
    print("\nCompared with previous run:")
    for key in ("pass_rate", "source_hit_rate", "fact_recall", "citation_rate"):
        old, new = previous["summary"].get(key), summary.get(key)
        delta = "" if old is None or new is None else f"  ({new - old:+.0%})"
        print(f"  {key:16} {format_rate(old)} -> {format_rate(new)}{delta}")
    old_rates = previous["summary"].get("per_question", {})
    for qid, q in summary["per_question"].items():
        old = old_rates.get(qid, {}).get("pass_rate")
        if old is not None and q["pass_rate"] is not None and old != q["pass_rate"]:
            print(f"  {qid:30} {format_rate(old)} -> {format_rate(q['pass_rate'])}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate the RAG pipeline on fixed questions.")
    parser.add_argument("--runs", type=int, default=3, help="Runs per question (default 3).")
    parser.add_argument("--workers", type=int, default=4, help="Parallel runs (default 4).")
    parser.add_argument("--ids", help="Comma-separated question ids to run.")
    parser.add_argument("--tags", help="Comma-separated tags; run questions with any of them.")
    parser.add_argument("--model", default=RAG_MODEL_NAME, help="Chat model to evaluate.")
    parser.add_argument("--review-model", default=SAFETY_REVIEW_MODEL, help="Reviewer model.")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--output", type=Path, help="Write all runs and the summary as JSON.")
    parser.add_argument("--compare", type=Path, help="Previous --output file to compare with.")
    parser.add_argument(
        "--include-missing",
        action="store_true",
        help="Also run questions whose expected sources are not ingested.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List questions and ingestion status without calling OpenAI.",
    )
    args = parser.parse_args(argv)
    if args.runs < 1 or args.workers < 1:
        parser.error("--runs and --workers must be at least 1")
    return args


def select(questions, ids=None, tags=None):
    if ids:
        wanted = set(ids.split(","))
        unknown = wanted - {q["id"] for q in questions}
        if unknown:
            raise SystemExit(f"Unknown question ids: {sorted(unknown)}")
        questions = [q for q in questions if q["id"] in wanted]
    if tags:
        wanted = set(tags.split(","))
        questions = [q for q in questions if wanted & set(q.get("tags", []))]
    return questions


def main(argv=None) -> int:
    args = parse_args(argv)
    questions = select(load_questions(args.questions), args.ids, args.tags)
    available = ingested_sources()
    missing_files = sorted(
        {s for q in questions for s in q.get("sources", [])}
        - {path.name for path in Path(DOCS_DIR).glob("*.pdf")}
    )
    if missing_files:
        print(f"Warning: expected sources not found in {DOCS_DIR}: {missing_files}")

    skipped = [] if args.include_missing else [
        q["id"] for q in questions if not runnable(q, available)
    ]
    to_run = [q for q in questions if q["id"] not in skipped]

    if args.list:
        for q in questions:
            status = "skip: not ingested" if q["id"] in skipped else "ready"
            print(f"{q['id']:30} {q['expect']:15} {status}")
        print(f"\n{len(to_run)} of {len(questions)} questions can run against "
              f"'{COLLECTION_NAME}'.")
        return 0
    if not to_run:
        print("No questions to run.")
        return 1

    from rag_service import RagService

    logging.getLogger("cardio-rag").setLevel(logging.WARNING)
    print(f"Evaluating {len(to_run)} questions x {args.runs} runs with model={args.model}, "
          f"reviewer={args.review_model}, collection={COLLECTION_NAME}")
    service = RagService.from_settings(model_name=args.model, review_model_name=args.review_model)
    started = time.perf_counter()
    scores, usage = run_evaluation(service, to_run, runs=args.runs, workers=args.workers)
    summary = summarize(to_run, scores)
    cost = estimate_cost(usage)
    print_report(to_run, summary, usage, cost, skipped)
    print(f"Elapsed: {time.perf_counter() - started:.0f}s")

    if args.compare:
        print_comparison(summary, json.loads(args.compare.read_text(encoding="utf-8")))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "config": {"model": args.model, "review_model": args.review_model,
                       "collection": COLLECTION_NAME, "runs": args.runs},
            "summary": summary,
            "usage": usage,
            "estimated_cost_usd": cost,
            "skipped": skipped,
            "scores": [asdict(score) for score in scores],
        }
        args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
