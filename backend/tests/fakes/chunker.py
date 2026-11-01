from study_assistant.domain.entities import Chunk, ChunkMetadata, Document


class FakeChunker:
    """Splits each page into windows of ``words_per_chunk`` whitespace-separated words."""

    def __init__(self, words_per_chunk: int = 50) -> None:
        self._size = words_per_chunk

    def chunk(self, document: Document) -> list[Chunk]:
        chunks: list[Chunk] = []
        for page in document.pages:
            words = page.text.split()
            for start in range(0, len(words), self._size):
                index = len(chunks)
                chunks.append(
                    Chunk(
                        id=Chunk.make_id(document.source, index),
                        text=" ".join(words[start : start + self._size]),
                        metadata=ChunkMetadata(
                            source=document.source,
                            page=page.number,
                            chunk_index=index,
                            topic=document.topic,
                        ),
                    )
                )
        return chunks
