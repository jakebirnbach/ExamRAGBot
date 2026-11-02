import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from study_assistant.application.use_cases.answer_question import AnswerQuestion
from study_assistant.application.use_cases.generate_quiz import GenerateQuiz, GradeAnswer
from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.application.use_cases.retrieve_context import RetrieveContext
from study_assistant.domain.entities import Chunk, ChunkMetadata, EmbeddedChunk
from study_assistant.interfaces.api.app import ApiDependencies, build_api
from tests.fakes import FakeEmbedder, FakeLLM, InMemoryVectorStore

PASSWORD = "correct horse"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


class Harness:
    def __init__(self) -> None:
        self.llm = FakeLLM()
        self.warmed = 0
        embedder = FakeEmbedder()
        store = InMemoryVectorStore()
        for source, topic in (("ttm.pdf", "M3"), ("oars.pdf", "M4")):
            text = f"Title\nthe stages of change in {source}"
            meta = ChunkMetadata(source, 3, 0, topic=topic, page_end=5)
            chunk = Chunk(Chunk.make_id(source, 0), text, meta)
            store.upsert([EmbeddedChunk(chunk, embedder.embed_query(text))])
        retrieve = RetrieveContext(embedder, store, top_k=2, top_n=2)

        def warm_up() -> None:
            self.warmed += 1

        self.app = build_api(
            ApiDependencies(
                answer=lambda: AnswerQuestion(retrieve, self.llm),
                list_topics=lambda: ListTopics(store),
                generate_quiz=lambda: GenerateQuiz(store, self.llm, excerpts=1, attempts=1),
                grade_answer=lambda: GradeAnswer(self.llm),
                warm_up=warm_up,
                password=PASSWORD,
            )
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with TestClient(harness.app) as c:
        yield c


def test_blank_password_is_refused_at_build_time() -> None:
    noop = lambda: None  # noqa: E731
    with pytest.raises(ValueError, match="password"):
        build_api(
            ApiDependencies(
                answer=noop,  # type: ignore[arg-type]
                list_topics=noop,  # type: ignore[arg-type]
                generate_quiz=noop,  # type: ignore[arg-type]
                grade_answer=noop,  # type: ignore[arg-type]
                warm_up=noop,
                password="  ",
            )
        )


def test_startup_warms_models_once(harness: Harness, client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert harness.warmed == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/topics"), ("POST", "/ask"), ("POST", "/quiz"), ("POST", "/quiz/grade")],
)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Bearer "},
        {"Authorization": f"Basic {PASSWORD}"},
    ],
)
def test_every_route_needs_the_password(
    client: TestClient, harness: Harness, method: str, path: str, headers: dict[str, str]
) -> None:
    body = {"question": "q", "reference_answer": "r", "answer": "a"}
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert harness.llm.calls == []


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_are_not_exposed(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_topics(client: TestClient) -> None:
    assert client.get("/topics", headers=AUTH).json() == {"topics": ["M3", "M4"]}


def test_ask_returns_citations_and_applies_topic_filter(
    harness: Harness, client: TestClient
) -> None:
    harness.llm.queue("Six stages [1].")
    response = client.post(
        "/ask", headers=AUTH, json={"question": " What are the stages? ", "topics": ["M4"]}
    )
    assert response.status_code == 200
    assert response.json() == {
        "text": "Six stages [1].",
        "grounded": True,
        "citations": [
            {"source": "oars.pdf", "page": 3, "page_end": 5, "label": "oars.pdf, pp. 3-5"}
        ],
    }
    assert "ttm.pdf" not in harness.llm.calls[0].messages[0].content


def test_ask_no_topics_searches_everything(harness: Harness, client: TestClient) -> None:
    harness.llm.queue("Stages [1][2].")
    assert client.post("/ask", headers=AUTH, json={"question": "stages"}).status_code == 200
    content = harness.llm.calls[0].messages[0].content
    assert "ttm.pdf" in content
    assert "oars.pdf" in content


def test_ask_general_answer_has_no_citations(harness: Harness, client: TestClient) -> None:
    harness.llm.queue("GENERAL_KNOWLEDGE\nStart with your weakest module.")
    body = client.post("/ask", headers=AUTH, json={"question": "x", "topics": ["nope"]}).json()
    assert body == {"text": "Start with your weakest module.", "citations": [], "grounded": False}


@pytest.mark.parametrize(
    "body", [{}, {"question": ""}, {"question": "   "}, {"question": "x" * 2001}]
)
def test_ask_rejects_bad_questions(harness: Harness, client: TestClient, body: object) -> None:
    assert client.post("/ask", headers=AUTH, json=body).status_code == 422
    assert harness.llm.calls == []


def test_llm_failure_is_a_502_without_internal_details(client: TestClient) -> None:
    # FakeLLM raises LLMError with its own message when no reply is queued.
    response = client.post("/ask", headers=AUTH, json={"question": "stages"})
    assert response.status_code == 502
    assert "FakeLLM" not in response.text


def test_quiz_then_grade(harness: Harness, client: TestClient) -> None:
    harness.llm.queue(json.dumps({"question": "Q?", "reference_answer": "Ref.", "sources": [1]}))
    quiz = client.post("/quiz", headers=AUTH, json={"topics": ["M3"]})
    assert quiz.status_code == 200
    assert quiz.json() == {
        "question": "Q?",
        "reference_answer": "Ref.",
        "topic": "M3",
        "citations": [{"source": "ttm.pdf", "page": 3, "page_end": 5, "label": "ttm.pdf, pp. 3-5"}],
    }

    harness.llm.queue('{"score": 0.9, "feedback": "Nice."}')
    grade = client.post(
        "/quiz/grade",
        headers=AUTH,
        json={"question": "Q?", "reference_answer": "Ref.", "answer": "My answer"},
    )
    assert grade.json() == {"correct": True, "feedback": "Nice.", "score": 0.9}


def test_quiz_with_no_material_is_404(client: TestClient) -> None:
    response = client.post("/quiz", headers=AUTH, json={"topics": ["nope"]})
    assert response.status_code == 404
    assert "another topic" in response.json()["detail"]


def test_grade_rejects_blank_answer(harness: Harness, client: TestClient) -> None:
    response = client.post(
        "/quiz/grade", headers=AUTH, json={"question": "Q", "reference_answer": "R", "answer": " "}
    )
    assert response.status_code == 422
    assert harness.llm.calls == []
