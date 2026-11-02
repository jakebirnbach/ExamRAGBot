import pytest

from study_assistant.application.use_cases.answer_question import (
    NOT_COVERED_MARKER,
    NOT_COVERED_TEXT,
    REFUSED_TEXT,
    SYSTEM_PROMPT,
    AnswerQuestion,
    build_user_message,
    renumber_citations,
)
from study_assistant.application.use_cases.retrieve_context import RetrieveContext
from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    Citation,
    EmbeddedChunk,
    MetadataFilter,
    ScoredChunk,
)
from tests.fakes import FakeEmbedder, FakeLLM, InMemoryVectorStore

ROWS = [
    ("ttm.pdf", 3, None, "M3", "TTM\nThe stages of change are precontemplation and contemplation."),
    ("deck.pdf", 10, 12, "M4", "Deck\nOARS: open questions, affirmations, reflections, summaries."),
    ("sleep.pdf", 2, None, "M6", "Sleep\nAdults need seven or more hours of sleep & rest <daily>."),
]


def hit(source: str, page: int, page_end: int | None = None) -> ScoredChunk:
    meta = ChunkMetadata(source, page, 0, page_end=page_end)
    return ScoredChunk(Chunk(f"{source}#0", "Title\nbody", meta), 1.0)


@pytest.fixture
def retrieve() -> RetrieveContext:
    emb, store = FakeEmbedder(), InMemoryVectorStore()
    for source, page, page_end, topic, text in ROWS:
        meta = ChunkMetadata(source, page, 0, topic=topic, page_end=page_end)
        chunk = Chunk(Chunk.make_id(source, 0), text, meta)
        store.upsert([EmbeddedChunk(chunk, emb.embed_query(text))])
    return RetrieveContext(emb, store, top_k=3, top_n=3)


def test_prompt_contains_numbered_escaped_sources_and_question(retrieve: RetrieveContext) -> None:
    llm = FakeLLM(["Adults need seven or more hours [1]."])
    AnswerQuestion(retrieve, llm).execute("How much sleep do adults need?")

    (call,) = llm.calls
    assert call.system == SYSTEM_PROMPT
    user = call.messages[0].content
    assert user.startswith('<sources>\n<source id="1"')
    assert user.rstrip().endswith("Question: How much sleep do adults need?")
    assert 'pages="pp. 10-12"' in user and 'topic="M6"' in user
    assert "&amp; rest &lt;daily&gt;" in user  # source text can't break out of its tag
    assert "\nSleep\n" not in user  # title header line stripped from each excerpt


def test_citations_map_to_pages_and_renumber_by_first_use() -> None:
    hits = [hit("a.pdf", 1), hit("b.pdf", 4, 6), hit("c.pdf", 9)]
    text, cites = renumber_citations("First [3]. Second [1][3]. Third [2, 3].", hits)
    assert text == "First [1]. Second [2][1]. Third [3][1]."
    assert cites == (Citation("c.pdf", 9), Citation("a.pdf", 1), Citation("b.pdf", 4, 6))


def test_out_of_range_markers_are_dropped() -> None:
    text, cites = renumber_citations("Claim [7]. Other [1].", [hit("a.pdf", 1)])
    assert text == "Claim. Other [1]."
    assert cites == (Citation("a.pdf", 1),)


def test_grounded_answer(retrieve: RetrieveContext) -> None:
    answer = AnswerQuestion(retrieve, FakeLLM(["OARS stands for four skills [2]."])).execute(
        "OARS?"
    )
    assert answer.grounded
    assert len(answer.citations) == 1 and answer.text.endswith("[1].")


def test_not_covered_marker(retrieve: RetrieveContext) -> None:
    llm = FakeLLM([f"{NOT_COVERED_MARKER}\nThe excerpts cover sleep and OARS [3]."])
    answer = AnswerQuestion(retrieve, llm).execute("What is the capital of France?")
    assert not answer.grounded and answer.citations == ()
    assert answer.text == f"{NOT_COVERED_TEXT} The excerpts cover sleep and OARS."


def test_uncited_answer_is_not_grounded(retrieve: RetrieveContext) -> None:
    answer = AnswerQuestion(retrieve, FakeLLM(["Probably eight hours."])).execute("Sleep?")
    assert not answer.grounded and answer.text == "Probably eight hours."


def test_no_retrieval_hits_skips_the_llm(retrieve: RetrieveContext) -> None:
    llm = FakeLLM()
    answer = AnswerQuestion(retrieve, llm).execute("x", MetadataFilter(topics=("M9",)))
    assert answer.text == NOT_COVERED_TEXT and not answer.grounded and llm.calls == []


def test_refusal_becomes_a_polite_answer(retrieve: RetrieveContext) -> None:
    answer = AnswerQuestion(retrieve, FakeLLM([FakeLLM.REFUSE])).execute("Sleep?")
    assert answer.text == REFUSED_TEXT and not answer.grounded


def test_max_tokens_passed_through(retrieve: RetrieveContext) -> None:
    llm = FakeLLM(["x [1]"])
    AnswerQuestion(retrieve, llm, max_tokens=1234).execute("Sleep?")
    assert llm.calls[0].max_tokens == 1234


def test_build_user_message_strips_question() -> None:
    assert build_user_message("  hi  ", [hit("a.pdf", 1)]).endswith("Question: hi")
