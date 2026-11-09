"""RagAdapter implements the shared RAGInterface on top of RagService."""

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from rag_adapter import RagAdapter, parse_history, to_rag_source
from rag_fakes import DRAFT, QUESTION, SOURCE, FakeRunnable, build_service, message
from rag_service import FILTER_REFUSAL, ResponseReview, add_disclaimer

from saferag import SafeRAG
from shared.contracts.rag import RAGInterface, RAGRequest


def test_adapter_satisfies_the_shared_interface():
    assert isinstance(RagAdapter(build_service()), RAGInterface)


async def test_query_through_saferag_returns_contract_response():
    secured = SafeRAG(RagAdapter(build_service()))

    response = await secured.query(RAGRequest(query=QUESTION))

    assert response.answer == add_disclaimer(DRAFT)
    assert response.critic.accepted is True
    assert response.metadata == {"outcome": "answered", "record_in_history": True}
    assert [source.reference for source in response.sources] == ["guide.pdf"]
    assert response.sources[0].excerpt == SOURCE.page_content
    assert response.sources[0].metadata == {"page": 3}


async def test_history_from_metadata_reaches_the_models():
    model = FakeRunnable(message(DRAFT))
    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier reply"},
    ]

    await RagAdapter(build_service(model=model)).query(
        RAGRequest(query=QUESTION, conversation_id="c1", metadata={"history": history})
    )

    for messages in model.calls:
        assert HumanMessage(content="Earlier question") in messages
        assert AIMessage(content="Earlier reply") in messages


async def test_refusal_returns_no_sources():
    service = build_service(reviewer=FakeRunnable(ResponseReview(approved=False)))

    response = await RagAdapter(service).query(RAGRequest(query=QUESTION))

    assert response.answer == add_disclaimer(FILTER_REFUSAL)
    assert response.sources == []
    assert response.critic.accepted is False
    assert response.metadata["outcome"] == "safety_rejected"


async def test_failure_returns_fail_closed_answer_without_critic():
    service = build_service(retriever=FakeRunnable(ConnectionError("Neon unavailable")))

    response = await RagAdapter(service).query(RAGRequest(query=QUESTION))

    assert response.metadata == {"outcome": "error", "record_in_history": False}
    assert response.critic is None
    assert response.sources == []


async def test_malformed_history_raises_without_calling_the_pipeline():
    model = FakeRunnable(message(DRAFT))

    with pytest.raises(ValueError, match="history"):
        await RagAdapter(build_service(model=model)).query(
            RAGRequest(query=QUESTION, metadata={"history": "not a list"})
        )

    assert model.calls == []


def test_parse_history_converts_roles():
    assert parse_history(None) == []
    assert parse_history([]) == []
    assert parse_history(
        [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
    ) == [HumanMessage(content="Hi"), AIMessage(content="Hello")]


@pytest.mark.parametrize(
    "entry",
    [
        "text",
        {"role": "system", "content": "private secret"},
        {"role": "user"},
        {"role": "user", "content": 5},
    ],
)
def test_parse_history_rejects_bad_entries_without_quoting_content(entry):
    with pytest.raises(ValueError) as error:
        parse_history([entry])

    assert "private secret" not in str(error.value)


@pytest.mark.parametrize(
    ("metadata", "reference"),
    [
        ({"source_key": "guide.pdf", "source": "C:\\private\\guide.pdf"}, "guide.pdf"),
        ({"source": "C:\\private\\docs\\other.pdf"}, "other.pdf"),
        ({"source": "/srv/private/docs/linux.pdf"}, "linux.pdf"),
        ({}, "unknown"),
    ],
)
def test_source_reference_never_exposes_absolute_paths(metadata, reference):
    source = to_rag_source(Document(page_content="Text", metadata=metadata))

    assert source.reference == reference
    assert source.metadata == {}
    assert "private" not in source.model_dump_json()
