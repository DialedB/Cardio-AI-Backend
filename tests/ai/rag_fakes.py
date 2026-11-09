"""Fake clients for testing RagService offline: no OpenAI or Neon calls are made."""

from types import SimpleNamespace

from langchain_core.documents import Document
from rag_service import RagService, ResponseReview

QUESTION = "How does exercise affect heart health?"
DRAFT = "Exercise helps the heart."
SOURCE = Document(
    page_content="Regular exercise supports heart health.",
    metadata={"source": "C:\\private\\docs\\guide.pdf", "source_key": "guide.pdf", "page": 3},
)


class FakeRunnable:
    """Returns (or raises) the given outcomes in order and records its inputs."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def invoke(self, value, *_args, **_kwargs):
        self.calls.append(value)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeModeration:
    """``rule(text)`` returns whether text is flagged, or raises to simulate an outage."""

    def __init__(self, rule=lambda _text: False):
        self.rule = rule
        self.inputs = []
        self.moderations = SimpleNamespace(create=self._create)

    def _create(self, *, model, input):
        self.inputs.append(input)
        return SimpleNamespace(results=[SimpleNamespace(flagged=self.rule(input))])


def message(text):
    return SimpleNamespace(content=text)


def build_service(**overrides):
    dependencies = {
        "model": FakeRunnable(message(DRAFT)),
        "query_generator": FakeRunnable(SimpleNamespace(queries=["variation"])),
        "reviewer": FakeRunnable(ResponseReview(approved=True)),
        "moderation_client": FakeModeration(),
        "retriever": FakeRunnable([SOURCE]),
        "model_name": "fake-model",
        "review_model_name": "fake-review-model",
    }
    return RagService(**{**dependencies, **overrides})
