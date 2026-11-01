from dataclasses import dataclass

from study_assistant.domain.entities.answer import Citation


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question: str
    reference_answer: str
    citations: tuple[Citation, ...]
    topic: str | None = None


@dataclass(frozen=True, slots=True)
class QuizGrade:
    """Result of grading a student's answer against a :class:`QuizQuestion`."""

    correct: bool
    feedback: str
    score: float
    """0.0 - 1.0; allows partial credit."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be within [0, 1], got {self.score}")
