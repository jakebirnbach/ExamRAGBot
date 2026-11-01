"""Domain-level exceptions. Adapters translate SDK errors into these."""


class StudyAssistantError(Exception):
    """Base class for every error raised by the application."""


class DocumentParsingError(StudyAssistantError):
    """A source document could not be read or parsed."""


class EmbeddingError(StudyAssistantError):
    """Text could not be embedded."""


class VectorStoreError(StudyAssistantError):
    """The vector store rejected a write or a query."""


class LLMError(StudyAssistantError):
    """The language model call failed or returned unusable output."""
