"""JSON API. Receives use-case factories from the composition root.

Routes are plain ``def`` so FastAPI runs them in its thread pool: use cases block on CPU-bound
models and network calls.
"""

import hmac
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from study_assistant.application.use_cases.answer_question import AnswerQuestion
from study_assistant.application.use_cases.generate_quiz import GenerateQuiz, GradeAnswer
from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.domain.entities import MetadataFilter
from study_assistant.domain.errors import StudyAssistantError
from study_assistant.interfaces.api.schemas import (
    AskRequest,
    AskResponse,
    CitationOut,
    GradeRequest,
    GradeResponse,
    QuizRequest,
    QuizResponse,
    TopicsResponse,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    answer: Callable[[], AnswerQuestion]
    list_topics: Callable[[], ListTopics]
    generate_quiz: Callable[[], GenerateQuiz]
    grade_answer: Callable[[], GradeAnswer]
    warm_up: Callable[[], None]
    """Runs once before the server accepts requests."""
    password: str


def _to_filter(topics: list[str]) -> MetadataFilter | None:
    return MetadataFilter(topics=tuple(topics)) if topics else None


def _password_gate(password: str) -> Callable[[HTTPAuthorizationCredentials | None], None]:
    expected = password.encode()

    def check(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
        ],
    ) -> None:
        supplied = credentials.credentials.encode() if credentials else b""
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Wrong password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return check


def build_api(deps: ApiDependencies) -> FastAPI:
    if not deps.password.strip():
        raise ValueError("the API needs a non-empty password")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        deps.warm_up()
        yield

    # No docs routes: they'd be the only pages reachable without the password.
    app = FastAPI(
        title="Study Assistant", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.exception_handler(StudyAssistantError)
    def service_failed(_: Request, exc: StudyAssistantError) -> JSONResponse:
        # Details can name AWS accounts or model ids, so they stay in the server log.
        logger.error("request failed: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "A service the assistant depends on failed. Please try again."},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    protected = APIRouter(dependencies=[Depends(_password_gate(deps.password))])

    @protected.get("/topics")
    def topics() -> TopicsResponse:
        return TopicsResponse(topics=deps.list_topics().execute())

    @protected.post("/ask")
    def ask(body: AskRequest) -> AskResponse:
        answer = deps.answer().execute(body.question, _to_filter(body.topics))
        return AskResponse(
            text=answer.text,
            citations=[CitationOut.of(c) for c in answer.citations],
            grounded=answer.grounded,
        )

    @protected.post("/quiz")
    def quiz(body: QuizRequest) -> QuizResponse:
        question = deps.generate_quiz().execute(_to_filter(body.topics))
        if question is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Couldn't find quiz material here. Try again or pick another topic.",
            )
        return QuizResponse(
            question=question.question,
            reference_answer=question.reference_answer,
            citations=[CitationOut.of(c) for c in question.citations],
            topic=question.topic,
        )

    @protected.post("/quiz/grade")
    def grade(body: GradeRequest) -> GradeResponse:
        result = deps.grade_answer().execute(body.question, body.reference_answer, body.answer)
        return GradeResponse(correct=result.correct, feedback=result.feedback, score=result.score)

    app.include_router(protected)
    return app
