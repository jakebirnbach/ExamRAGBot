"""Request and response bodies of the JSON API."""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from study_assistant.domain.entities import Citation

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class CitationOut(BaseModel):
    source: str
    page: int
    page_end: int | None
    label: str
    """Ready to display, e.g. ``handout.pdf, pp. 3-5``."""

    @classmethod
    def of(cls, citation: Citation) -> "CitationOut":
        return cls(
            source=citation.source,
            page=citation.page,
            page_end=citation.page_end,
            label=str(citation),
        )


class AskRequest(BaseModel):
    question: Question
    topics: list[str] = []
    """Exact labels from ``GET /topics``; empty means all materials."""


class AskResponse(BaseModel):
    text: str
    citations: list[CitationOut]
    grounded: bool


class TopicsResponse(BaseModel):
    topics: list[str]


class QuizRequest(BaseModel):
    topics: list[str] = []


class QuizResponse(BaseModel):
    question: str
    reference_answer: str
    """Sent up front because grading is stateless; the client hides it until graded."""
    citations: list[CitationOut]
    topic: str | None


class GradeRequest(BaseModel):
    question: LongText
    reference_answer: LongText
    answer: LongText


class GradeResponse(BaseModel):
    correct: bool
    feedback: str
    score: float
