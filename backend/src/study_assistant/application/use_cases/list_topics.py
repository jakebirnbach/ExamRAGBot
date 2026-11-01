from study_assistant.domain.ports import VectorStore


class ListTopics:
    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def execute(self) -> list[str]:
        return self._store.list_topics()
