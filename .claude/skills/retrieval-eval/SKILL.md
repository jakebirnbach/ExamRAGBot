---
name: retrieval-eval
description: Use when running, extending or interpreting the retrieval eval, or when changing anything that affects retrieval quality (chunking, cleaning, hybrid alpha, top_k/top_n, reranker, per-source cap). Covers eval/questions.jsonl format, writing answer_pattern regexes and labelling with label_questions.py, run_eval.py metrics, the recorded baseline, and the main trap - "misses" that are really labelling errors. Triggers - "run the eval", "hit@5", "did retrieval get worse", "add eval questions", "tune alpha", "is the reranker worth it", "retrieval quality".
---

# Retrieval eval

## Files (backend/eval/)

- `questions_draft.jsonl`: the source of truth you edit. One line per question:
  `{"question", "answer_pattern", "prefer"?}`.
- `label_questions.py`: turns drafts into `questions.jsonl` by searching every indexed page
  (same parser, exclusions and dedup as ingestion) with `answer_pattern`. Every matching page
  becomes acceptable; `prefer` (a substring of the source path) picks the primary
  `expected_source`/`expected_page`. It prints `N pages / M files` per question to stderr.
- `questions.jsonl`: `{id, question, expected_source, expected_page, also_accept:[{source,page}], answer_pattern}`. Generated; don't hand-edit.
- `run_eval.py`: the evaluator. `results/baseline.json` holds the recorded baseline.

```
uv run python eval/label_questions.py eval/questions_draft.jsonl > eval/questions.jsonl
uv run python eval/run_eval.py --misses                 # about 9.5 min: 42 q × 5 alphas, reranking on CPU
uv run python eval/run_eval.py --alphas 0.5 --misses    # quicker single-alpha run
```

Run it in the background. Its stdout is printed only when it finishes, and FlagEmbedding prints
`Compute Scores` progress bars to stderr. It needs the populated Pinecone index and both models.

## Metrics

A hit is a retrieved chunk with an acceptable source whose page range covers an acceptable page.
Per alpha, with and without reranking: hit@1, hit@5, MRR@5, and recall@top_k (the correct page
anywhere in the hybrid shortlist, i.e. the reranker's ceiling). The final top 5 applies the app's
`limit_per_source` cap (2 per file). Each question's embedding and reranker scores are computed
once and reused across alphas.

## Baseline (2026-11-01, 42 questions, 2,871 chunks)

| alpha | rerank | hit@1 | hit@5 | MRR@5 | recall@20 |
|---|---|---|---|---|---|
| 1.0 | no / yes | 73.8 / 78.6 | 97.6 / 100 | .837 / .883 | 100 |
| 0.7 | no / yes | 81.0 / 76.2 | 100 / 100 | .884 / .863 | 100 |
| **0.5** | no / **yes** | 81.0 / 76.2 | 97.6 / **100** | .872 / .863 | 100 |
| 0.3 | no / yes | 71.4 / 76.2 | 92.9 / 100 | .800 / .859 | 100 |
| 0.0 | no / yes | 69.0 / 73.8 | 88.1 / 95.2 | .770 / .827 | 95.2 |

Decision: **keep `HYBRID_ALPHA=0.5` with reranking** (the user confirmed). The reranker makes
hit@5 robust across alphas; its small hit@1 drop (2 questions) doesn't matter because all 5 chunks
go to the LLM. Differences of 1–2 questions are noise at n=42 (each question is 2.4 points).

## The main trap: labelling errors look like retrieval misses

In the first run, all 3 "misses" were correct retrievals that the regex failed to recognise:
- `pre -contemplation` (transcript spacing) vs a pattern expecting `precontemplation`.
  Use `pre[\s-]*contemplation`.
- `4 kcal/g` vs a pattern expecting `calories per gram`.
- Appreciative-inquiry phases spread over spoken prose (`number two is Discover`), not a list.

**Before reporting a miss, read what was retrieved** (`--misses` shows the top 3), then fix the
pattern and relabel. Pattern guidance:
- Match answer-bearing text, not mere mentions. `wellness wheel` alone hit 39 pages; require
  context such as `wellness wheel.{0,250}(assess|rate|scale|…)`.
- About 1–15 pages is healthy. Dozens means too loose (the eval gets lenient); 0 means too strict.
- Allow transcript artefacts and variants (see the course-materials skill): spaced hyphens, ASR
  misspellings, `S.M.A.R.T.` vs `SMART`, `%` vs `percent`.

## Known limitations

- The eval is near its ceiling (97–100% hit@5 for good configurations), so it can't separate them
  well. hit@1/MRR still differ.
- The questions were written by an agent after reading the pages, which favours keyword overlap.
  The user does **not** want the student (their mom) asked for questions. To make the eval harder,
  write paraphrased, scenario-based ("a client says X, which stage?") and two-concept comparison
  questions yourself.
- Recording a new baseline: `--json eval/results/<name>.json`, and update the table above.
