"""Interactive test-harness chat around the stateless RAG service."""

from langchain_core.messages import AIMessage, HumanMessage
from rag_service import CHECK_UNAVAILABLE, AnswerResult, RagService, add_disclaimer
from rag_telemetry import shutdown_telemetry
from settings import RAG_MAX_HISTORY_MESSAGES


def print_result(question: str, result: AnswerResult) -> None:
    print(f"\n--- You asked: {question} ---")
    if result.search_queries:
        print("\nSearch queries:")
        for i, query in enumerate(result.search_queries, 1):
            print(f"  {i}. {query}")
    if result.sources:
        print("\nSelected documents:")
        for i, doc in enumerate(result.sources, 1):
            preview = doc.page_content.replace("\n", " ")[:80]
            print(f"  Doc {i} [{source_label(doc)}]: {preview}...")
    print(f"\n🤖 Answer: {result.answer}")
    print(f"\n[outcome: {result.outcome} | decided by: {result.stage or 'unknown'}]")


def source_label(doc) -> str:
    """File name and printed page number of a retrieved chunk."""
    name = doc.metadata.get("source_key", "unknown source")
    page = doc.metadata.get("page_label")
    if page is None and isinstance(doc.metadata.get("page"), int):
        page = doc.metadata["page"] + 1  # PyPDF's "page" is a 0-based index
    return f"{name}, p. {page}" if page is not None else name


def start_chat(service: RagService) -> None:
    print("=" * 60)
    print("Advanced RAG Chat Started (Multi-Query + RRF + Memory)")
    print("=" * 60)
    print("Ask me questions! Type 'quit' to exit.")

    history = []
    try:
        while True:
            try:
                question = input("\nYour question: ")
            except EOFError:
                print("\nGoodbye!")
                break

            if question.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            try:
                result = service.answer(question, history)
                if result.record_in_history:
                    history.append(HumanMessage(content=question))
                    history.append(AIMessage(content=result.answer))
                    del history[:-RAG_MAX_HISTORY_MESSAGES]
                print_result(question, result)
            except Exception as exc:
                print(f"[chat] failed: {type(exc).__name__}: {exc}")
                print(f"\nAnswer: {add_disclaimer(CHECK_UNAVAILABLE)}")
    except KeyboardInterrupt:
        print("\nGoodbye!")


def main() -> int:
    try:
        try:
            service = RagService.from_settings()
        except Exception as exc:
            print(f"RAG pipeline failed to start: {type(exc).__name__}: {exc}")
            return 1
        start_chat(service)
        return 0
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    raise SystemExit(main())
