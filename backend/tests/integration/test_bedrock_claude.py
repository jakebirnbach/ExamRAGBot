"""One real request to Claude on Bedrock. It costs money (a fraction of a cent), so it only
runs with RUN_BEDROCK_TESTS=1, using the configured adapter (BEDROCK_API), model and profile."""

import os

import pytest

from study_assistant.domain.ports import Message
from study_assistant.infrastructure.config import get_settings
from study_assistant.main import Container

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BEDROCK_TESTS") != "1", reason="set RUN_BEDROCK_TESTS=1 (makes a paid call)"
)


def test_real_completion() -> None:
    llm = Container(get_settings()).llm  # whichever adapter BEDROCK_API selects
    reply = llm.complete("Reply with one word.", [Message("user", "Say OK.")], max_tokens=512)
    assert reply.strip()
