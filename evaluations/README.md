# Evaluation guide

The cases in `questions.json` provide known expectations for the fictional Northstar corpus. Keep this directory out of MongoDB so the expected answers cannot be retrieved as source material.

## Evaluate retrieval first

The current application returns passages and similarity scores. For each answerable case, record:

- whether an expected source appears at rank 1
- whether an expected source appears in the top 3
- whether the retrieved text actually contains the expected fact
- whether a superseded or irrelevant source ranks above the controlling source

Two useful aggregate measures are:

- `Recall@3`: the percentage of answerable questions with an expected source in the first three results
- `MRR`: the average reciprocal rank of the first expected source, where rank 1 scores 1, rank 2 scores 0.5, and rank 3 scores 0.33

Similarity scores are not correctness probabilities. Compare scores within an experiment, but do not assume that an 80 percent similarity means an answer is 80 percent likely to be correct.

## Evaluate answer generation later

After an LLM answer layer is added, separately check:

- factual agreement with `expected_fact`
- citations that directly support each claim
- correct handling of document status and effective dates
- completeness when several sources are required
- clarification for ambiguous questions
- abstention when no source contains the answer

An answer can sound excellent while relying on the wrong retrieved passage. Keeping retrieval and generation scores separate makes the failure visible.

## Suggested experiment log

| Run | Corpus | Chunk size | Overlap | Search method | Recall@3 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Current documents | Default | Default | Vector |  |  |
| 2 | Add old policy | Default | Default | Vector |  |  |
| 3 | Add amendment and noise | Default | Default | Vector |  |  |

Change one variable per run. Useful future comparisons include smaller and larger chunks, metadata filters, hybrid keyword and vector search, a reranker, and different embedding models.
