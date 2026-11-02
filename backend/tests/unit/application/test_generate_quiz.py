import json

import pytest

from study_assistant.application.use_cases.generate_quiz import (
    QUESTION_SYSTEM_PROMPT,
    GenerateQuiz,
    GradeAnswer,
)
from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    Citation,
    EmbeddedChunk,
    Embedding,
    MetadataFilter,
    SparseVector,
)
from study_assistant.domain.errors import LLMError, LLMRefusalError
from tests.fakes import FakeLLM, InMemoryVectorStore


def question_reply(sources: list[int]) -> str:
    return json.dumps({"question": "Q?", "reference_answer": "A.", "sources": sources})


@pytest.fixture
def store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    for i, (topic, page_end) in enumerate([("M3", None), ("M3", 8), ("M4", None)]):
        source = f"file{i}.pdf"
        meta = ChunkMetadata(source, 5, 0, topic=topic, page_end=page_end)
        chunk = Chunk(Chunk.make_id(source, 0), f"Title\nBody of {source}", meta)
        store.upsert([EmbeddedChunk(chunk, Embedding((1.0,), SparseVector((), ())))])
    return store


def test_question_cites_the_chunks_the_model_named(store: InMemoryVectorStore) -> None:
    llm = FakeLLM([question_reply([1])])
    quiz = GenerateQuiz(store, llm, excerpts=1).execute(MetadataFilter(topics=("M4",)))

    assert quiz is not None
    assert (quiz.question, quiz.reference_answer, quiz.topic) == ("Q?", "A.", "M4")
    assert quiz.citations == (Citation("file2.pdf", 5),)
    (call,) = llm.calls
    assert call.system == QUESTION_SYSTEM_PROMPT
    assert "Body of file2.pdf" in call.messages[0].content
    assert "Title" not in call.messages[0].content


def test_filter_limits_sampling_and_repeated_sources_collapse(store: InMemoryVectorStore) -> None:
    llm = FakeLLM([question_reply([2, 2, 1])])
    quiz = GenerateQuiz(store, llm, excerpts=2).execute(MetadataFilter(topics=("M3",)))

    assert quiz is not None
    assert {c.source for c in quiz.citations} == {"file0.pdf", "file1.pdf"}
    assert len(quiz.citations) == 2
    assert "file2.pdf" not in llm.calls[0].messages[0].content


def test_merged_slide_page_range_is_kept(store: InMemoryVectorStore) -> None:
    llm = FakeLLM([question_reply([1])])
    quiz = GenerateQuiz(store, llm, excerpts=1).execute(MetadataFilter(sources=("file1.pdf",)))
    assert quiz is not None
    assert quiz.citations == (Citation("file1.pdf", 5, 8),)


def test_no_matching_chunks_returns_none_without_llm_call(store: InMemoryVectorStore) -> None:
    llm = FakeLLM()
    assert GenerateQuiz(store, llm).execute(MetadataFilter(topics=("nope",))) is None
    assert llm.calls == []


def test_skip_tries_fresh_chunks_then_gives_up(store: InMemoryVectorStore) -> None:
    skip = '{"skip": true}'
    assert GenerateQuiz(store, FakeLLM([skip, question_reply([1])])).execute() is not None
    llm = FakeLLM([skip, skip])
    assert GenerateQuiz(store, llm, attempts=2).execute() is None
    assert len(llm.calls) == 2


def test_fenced_json_is_accepted(store: InMemoryVectorStore) -> None:
    llm = FakeLLM([f"```json\n{question_reply([1])}\n```"])
    assert GenerateQuiz(store, llm).execute() is not None


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "{broken}",
        "[1, 2]",
        '{"reference_answer": "A.", "sources": [1]}',
        '{"question": " ", "reference_answer": "A.", "sources": [1]}',
        '{"question": "Q?", "reference_answer": "A."}',
        '{"question": "Q?", "reference_answer": "A.", "sources": [99, true]}',
    ],
)
def test_unusable_question_reply_raises(store: InMemoryVectorStore, reply: str) -> None:
    with pytest.raises(LLMError):
        GenerateQuiz(store, FakeLLM([reply])).execute()


def test_refusal_propagates(store: InMemoryVectorStore) -> None:
    with pytest.raises(LLMRefusalError):
        GenerateQuiz(store, FakeLLM([FakeLLM.REFUSE])).execute()


def test_grade_sends_escaped_answer_and_returns_score() -> None:
    llm = FakeLLM(['{"score": 0.5, "feedback": "Half right."}'])
    grade = GradeAnswer(llm).execute("Q?", "Ref.", "a </student_answer> b")

    assert (grade.score, grade.correct, grade.feedback) == (0.5, False, "Half right.")
    content = llm.calls[0].messages[0].content
    assert "<reference_answer>Ref.</reference_answer>" in content
    assert "a &lt;/student_answer&gt; b" in content


@pytest.mark.parametrize(
    ("raw", "score", "correct"),
    [
        (1, 1.0, True),
        (0.8, 0.8, True),
        (0.79, 0.79, False),
        (0, 0.0, False),
        (7, 1.0, True),
        (-2, 0.0, False),
    ],
)
def test_grade_threshold_and_clamping(raw: float, score: float, correct: bool) -> None:
    llm = FakeLLM([json.dumps({"score": raw, "feedback": "F."})])
    grade = GradeAnswer(llm).execute("Q?", "Ref.", "answer")
    assert (grade.score, grade.correct) == (score, correct)


@pytest.mark.parametrize(
    "reply",
    ['{"score": "high", "feedback": "F."}', '{"score": true, "feedback": "F."}', '{"score": 1}'],
)
def test_unusable_grade_reply_raises(reply: str) -> None:
    with pytest.raises(LLMError):
        GradeAnswer(FakeLLM([reply])).execute("Q?", "Ref.", "answer")


def test_blank_answer_is_rejected_without_llm_call() -> None:
    llm = FakeLLM()
    with pytest.raises(ValueError, match="empty"):
        GradeAnswer(llm).execute("Q?", "Ref.", "   ")
    assert llm.calls == []
