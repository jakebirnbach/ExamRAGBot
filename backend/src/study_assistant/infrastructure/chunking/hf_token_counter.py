from typing import Any


class HuggingFaceTokenCounter:
    """Counts tokens with the embedding model's own tokenizer (loaded lazily)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._tokenizer: Any = None

    def __call__(self, text: str) -> int:
        if self._tokenizer is None:
            from transformers import AutoTokenizer  # noqa: PLC0415 - heavy import, deferred

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._tokenizer.model_max_length = 1_000_000  # we only count; silence length warnings
        return len(self._tokenizer.encode(text, add_special_tokens=False))
