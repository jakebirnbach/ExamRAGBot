"""Derive module / lesson / topic for each course file from its path and name.

Transcripts encode their lesson in the file name (``M3 L1 Video 7 - Self-Efficacy.pdf``).
Top-level handouts and articles are matched to a lesson by title; anything ambiguous or
unmatched becomes ``General / Reference``.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path, PurePath

MODULE_NAMES: dict[int, str] = {
    1: "Foundations of Health Coaching",
    2: "Setting Up & Conducting Sessions",
    3: "Health Behavior Change Theory",
    4: "Motivational Interviewing & Coaching Strategies",
    5: "Professional Practice, Ethics & Self-Care",
    6: "Health Promotion, Fitness, Nutrition & Wellness",
}
GENERAL_TOPIC = "General / Reference"

_LESSON_FILE = re.compile(
    r"^M(?P<module>\d+)\s+L(?P<lesson>\d+)\s+Video\s+\d+\s*-?\s*(?P<title>.*)$"
)
_MODULE_DIR = re.compile(r"^Module\s+(?P<module>\d+)\b", re.IGNORECASE)
_TITLE_PREFIXES = ("video slides handout - ",)
_TRAILING_COPY = re.compile(r"\s*(\(\d+\)|\d+)$")  # "Foo (1)", "Transtheoretical Model 2"
_MIN_CONTAINED_LEN = 10
_FUZZY_THRESHOLD = 0.88


def topic_label(module: int) -> str:
    return f"M{module} · {MODULE_NAMES.get(module, f'Module {module}')}"


def normalize_title(title: str) -> str:
    t = title.strip().lower()
    for prefix in _TITLE_PREFIXES:
        t = t.removeprefix(prefix)
    t = _TRAILING_COPY.sub("", t)
    t = t.removeprefix("the ")
    return re.sub(r"[^a-z0-9]", "", t)


@dataclass(frozen=True, slots=True)
class Classification:
    topic: str
    module: str | None = None
    lesson: str | None = None


GENERAL = Classification(GENERAL_TOPIC)


class CourseCatalog:
    def __init__(self, lessons: dict[str, set[tuple[int, int]]]) -> None:
        """``lessons`` maps a normalised lesson title to the (module, lesson) pairs using it."""
        self._lessons = lessons

    @classmethod
    def from_directory(cls, root: Path) -> "CourseCatalog":
        lessons: dict[str, set[tuple[int, int]]] = defaultdict(set)
        for path in root.rglob("*.pdf"):
            if m := _LESSON_FILE.match(path.stem):
                key = normalize_title(m["title"])
                if key:
                    lessons[key].add((int(m["module"]), int(m["lesson"])))
        return cls(dict(lessons))

    def classify(self, relative_path: PurePath) -> Classification:
        if m := _LESSON_FILE.match(relative_path.stem):
            module, lesson = int(m["module"]), int(m["lesson"])
            return Classification(topic_label(module), f"M{module}", f"L{lesson}")
        for part in relative_path.parts[:-1]:
            if d := _MODULE_DIR.match(part):
                module = int(d["module"])
                return Classification(topic_label(module), f"M{module}")
        return self._match_title(relative_path.stem)

    def _match_title(self, stem: str) -> Classification:
        key = normalize_title(stem)
        if not key:
            return GENERAL
        candidates = self._lessons.get(key)
        if not candidates:
            candidates = self._contained(key) or self._fuzzy(key)
        if not candidates:
            return GENERAL
        modules = {module for module, _ in candidates}
        if len(modules) != 1:
            return GENERAL  # e.g. "Follow-Up Session" exists in both M2 and M4
        module = modules.pop()
        lessons = {lesson for _, lesson in candidates}
        lesson = f"L{lessons.pop()}" if len(lessons) == 1 else None
        return Classification(topic_label(module), f"M{module}", lesson)

    def _contained(self, key: str) -> set[tuple[int, int]]:
        hits: set[tuple[int, int]] = set()
        for title, pairs in self._lessons.items():
            shorter = min(key, title, key=len)
            if len(shorter) >= _MIN_CONTAINED_LEN and (key in title or title in key):
                hits |= pairs
        return hits

    def _fuzzy(self, key: str) -> set[tuple[int, int]]:
        best, best_ratio = None, _FUZZY_THRESHOLD
        for title in self._lessons:
            ratio = SequenceMatcher(None, key, title).ratio()
            if ratio >= best_ratio:
                best, best_ratio = title, ratio
        return set(self._lessons[best]) if best else set()
