# Evaluations

Two evaluations over the sample corpus in `corpus/documents`. They measure
different things. Both need the corpus ingested.

Keep this directory out of the database: it holds the expected answers, and
ingesting it would let them be retrieved as source material.

## The questions

There are 17, in seven shapes. They live in `corpus/manifest.yaml`, and the
two JSON files here are generated from it by `corpus/generate/eval_suites.py`.
Edit the manifest and regenerate; never edit the JSON by hand.

| Shape | Count | Example | Expected of single-pass RAG |
| --- | --- | --- | --- |
| Single hop | 2 | What is the shelf life of the Classic Sourdough? | Pass |
| Multi hop | 2 | Which flour supplier for the withdrawn product also supplies the High Street bakery? | Fail |
| Long distance | 2 | Why was the Classic Sourdough launch delayed? | Fail |
| Context loss | 4 | What temperature is the deck oven set to for the Classic Sourdough? | Fail under plain chunking |
| Aggregation | 3 | Which bakery had the most waste in 2025? | Fail |
| Ambiguous | 2 | What temperature should the oven be set to for the sourdough? | Should ask which product |
| Unanswerable | 2 | How many calories are in the Classic Sourdough? | Should decline |

| File | Shapes |
| --- | --- |
| `questions.json` | Single hop, multi hop, long distance, context loss, aggregation |
| `conflict-and-noise-questions.json` | Ambiguous and unanswerable |

The failures are the measurement, not a bug. A multi-hop question that passes
means the corpus is not hard enough.

## Retrieval evaluation

Checks which documents came back. Use **Run evaluation** in the UI, or:

```bash
curl -s -X POST http://localhost:18001/evaluations/run | jq
```

To run only some shapes, untick the others in the UI, or name the ones you
want:

```bash
curl -s -X POST http://localhost:18001/evaluations/run \
  -H 'Content-Type: application/json' \
  -d '{"categories": ["single_hop", "context_loss"]}' | jq
```

Scoring is by filename: was an expected source returned, did the pipeline
abstain when it should, did it ask for clarification when it should. It costs
nothing unless the ambiguity check is configured.

## Answer evaluation

Checks the sentence the system produced. It needs `OPENROUTER_API_KEY`, and
each question makes one paid model call.

```bash
.venv/bin/python evaluations/answer_eval/run.py --system path-a
```

Three deterministic checks per question, with no model involved:

- **States the expected fact:** a named thing or measurement from the right answer appears.
- **Avoids the known wrong answer:** for example "6 days", the near-twin product's shelf life.
- **Claims are supported:** every named thing in the answer appears in a passage the answer cited.

A model judge is used only where the right answer is prose that cannot be
string-matched, such as a list of causes. Its verdicts are stored per case.

| Flag | |
| --- | --- |
| `--only cl-01,mh-01` | Grade a subset |
| `--runs 3` | Repeat each question; answers vary between runs |
| `--no-judge` | Deterministic checks only |
| `--judge <model>` | Override the judge model |

Results are written to `evaluations/results/`.

## Comparing configurations

To compare chunking strategies or embedding models, change one setting,
re-ingest with `corpus/generate/ingest.py --fresh`, run both evaluations, and
keep the results file. Change one thing at a time, or the numbers cannot be
attributed.

Scores from the retriever and the reranker are ranking signals, not
probabilities. A score of 0.80 does not mean an answer is 80 percent likely to
be right.
