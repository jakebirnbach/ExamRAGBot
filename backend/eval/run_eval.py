"""Retrieval eval: does the right page reach the top 5?

For every hybrid weight (alpha) it reports, with and without the reranker:

* hit@1 / hit@5 - share of questions with an acceptable page at rank 1 / in the top 5
* MRR@5         - mean of 1/rank of the first acceptable page (0 if not in the top 5)
* recall@K      - acceptable page anywhere in the K hybrid candidates: the ceiling the
                  reranker can reach, since it only re-orders that shortlist

The final top 5 uses the same per-source cap as the app. A retrieved chunk counts when it
comes from an acceptable source and its page range covers the acceptable page.

    uv run python eval/run_eval.py                     # alphas 1.0 0.7 0.5 0.3 0.0
    uv run python eval/run_eval.py --alphas 0.5 --misses
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from study_assistant.application.use_cases.retrieve_context import limit_per_source
from study_assistant.domain.entities import ScoredChunk
from study_assistant.infrastructure.config import get_settings
from study_assistant.main import Container

EVAL_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    gold: frozenset[tuple[str, int]]

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "Question":
        gold = {(str(row["expected_source"]), int(row["expected_page"]))}
        for alt in row.get("also_accept", []):
            gold.add((str(alt["source"]), int(alt["page"])))
        return cls(str(row["id"]), str(row["question"]), frozenset(gold))

    def matches(self, hit: ScoredChunk) -> bool:
        m = hit.chunk.metadata
        return any(s == m.source and m.page <= p <= m.last_page for s, p in self.gold)


@dataclass
class Tally:
    ranks: list[int | None] = field(default_factory=list)  # 1-based rank of first hit
    in_pool: list[bool] = field(default_factory=list)

    def add(self, q: Question, ranked: list[ScoredChunk], pool: list[ScoredChunk]) -> None:
        self.ranks.append(next((i for i, h in enumerate(ranked, 1) if q.matches(h)), None))
        self.in_pool.append(any(q.matches(h) for h in pool))

    def row(self) -> tuple[float, float, float, float]:
        n = len(self.ranks)
        hit1 = sum(r == 1 for r in self.ranks) / n
        hit5 = sum(r is not None for r in self.ranks) / n
        mrr = sum(1 / r for r in self.ranks if r) / n
        return hit1, hit5, mrr, sum(self.in_pool) / n


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--questions", type=Path, default=EVAL_DIR / "questions.jsonl")
    ap.add_argument("--alphas", type=float, nargs="+", default=[1.0, 0.7, 0.5, 0.3, 0.0])
    ap.add_argument(
        "--misses", action="store_true", help="List misses (reranked, at HYBRID_ALPHA)."
    )
    ap.add_argument("--json", type=Path, help="Also write results to this file.")
    args = ap.parse_args()

    settings = get_settings()
    container = Container(settings)
    top_k, top_n, cap = (
        settings.retrieval_top_k,
        settings.rerank_top_n,
        settings.max_chunks_per_source,
    )
    stores = {a: container.vector_store(alpha=a) for a in args.alphas}
    miss_alpha = settings.hybrid_alpha if settings.hybrid_alpha in args.alphas else args.alphas[0]
    questions = [
        Question.from_json(json.loads(line))
        for line in args.questions.read_text().splitlines()
        if line.strip()
    ]

    tallies = {(a, rr): Tally() for a in args.alphas for rr in (False, True)}
    misses: list[tuple[Question, list[ScoredChunk]]] = []
    started = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"\r[{i}/{len(questions)}] {q.id}", end="", file=sys.stderr, flush=True)
        query = container.embedder.embed_query(q.text)
        rerank_cache: dict[str, float] = {}
        for alpha in args.alphas:
            pool = stores[alpha].search(query, top_k)
            todo = [c for c in pool if c.chunk.id not in rerank_cache]
            for c in container.reranker.rerank(q.text, todo, top_n=len(todo)):
                rerank_cache[c.chunk.id] = c.score
            reranked = sorted(
                (ScoredChunk(c.chunk, rerank_cache[c.chunk.id]) for c in pool),
                key=lambda s: s.score,
                reverse=True,
            )
            for rr, ranked in ((False, pool), (True, reranked)):
                final = limit_per_source(ranked, top_n, cap)
                tallies[(alpha, rr)].add(q, final, pool)
                if rr and alpha == miss_alpha and not any(q.matches(h) for h in final):
                    misses.append((q, final))
    elapsed = time.monotonic() - started

    print(
        f"\r{len(questions)} questions, top_k={top_k}, top_n={top_n}, "
        f"max {cap}/source, {elapsed:.0f}s\n",
        file=sys.stderr,
    )
    recall_col = f"recall@{top_k}"
    print(f"{'alpha':>5}  {'rerank':<6}  {'hit@1':>6}  {'hit@5':>6}  {'MRR@5':>6}  {recall_col:>9}")
    results = []
    for alpha in args.alphas:
        for rr in (False, True):
            hit1, hit5, mrr, recall = tallies[(alpha, rr)].row()
            results.append(
                {
                    "alpha": alpha,
                    "rerank": rr,
                    "hit@1": hit1,
                    "hit@5": hit5,
                    "mrr@5": mrr,
                    f"recall@{top_k}": recall,
                }
            )
            label = "yes" if rr else "no"
            metrics = f"{hit1:>6.1%}  {hit5:>6.1%}  {mrr:>6.3f}  {recall:>9.1%}"
            print(f"{alpha:>5.1f}  {label:<6}  {metrics}")
        print()

    if args.misses:
        print(f"Missed with rerank at alpha={miss_alpha}:")
        for q, final in misses:
            print(f"\n  {q.id}: {q.text}")
            print(f"     want: {sorted(q.gold)[:3]}{' ...' if len(q.gold) > 3 else ''}")
            for h in final[:3]:
                m = h.chunk.metadata
                pages = f"{m.page}-{m.page_end}" if m.page_end else str(m.page)
                print(f"     got:  {m.source[:70]} p{pages}")

    if args.json:
        args.json.write_text(
            json.dumps({"questions": len(questions), "results": results}, indent=2)
        )


if __name__ == "__main__":
    main()
