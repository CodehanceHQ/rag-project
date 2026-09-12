# Evaluation guide

The evaluation files provide known expectations for the fictional Northstar corpus. Keep this directory out of MongoDB so the expected answers cannot be retrieved as source material.

## Evaluation suites

| File | Upload these document groups | Purpose |
| --- | --- | --- |
| `questions.json` | `policies`, `procedures`, `reference` | Establish a clean retrieval baseline without deliberately conflicting or irrelevant sources |
| `conflict-and-noise-questions.json` | `policies`, `procedures`, `reference`, `conflicting-versions`, `noise` | Test obsolete policies, controlling amendments, ambiguous wording, and topically similar noise |
| `solution-experiments.json` | Groups listed by each experiment | Compare an existing failure with a specific remediation and measurable acceptance criteria |

Run the baseline first. Save its ranks and scores, then upload `conflicting-versions` and `noise` and run the challenge suite. Several challenge questions deliberately repeat baseline questions so you can compare how their ranking changes.

The solution experiments distinguish between two implementation states:

- `available_manual` means the treatment can be tested with the application now.
- `pending` means the JSON defines the future acceptance test, but the capability must be implemented before the treatment run is possible.

This prevents an evaluation plan from being mistaken for an implemented feature. At present, permanent document deletion is the available document-management treatment. Metadata extraction and filtering, hybrid search, structure-aware CSV chunks, reranking, and calibrated relevance thresholds remain pending.

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
| 1 | Baseline groups | Default | Default | Vector |  |  |
| 2 | Add conflicting versions | Default | Default | Vector |  |  |
| 3 | Add noise | Default | Default | Vector |  |  |

Change one variable per run. Useful future comparisons include smaller and larger chunks, metadata filters, hybrid keyword and vector search, a reranker, and different embedding models.

## Run a solution experiment

Each entry in `solution-experiments.json` contains:

1. A concrete failure and query.
2. A control configuration using the current behavior.
3. One treatment tied to a specific capability.
4. Success criteria that can be checked without relying on appearance or intuition.

Record the control result before implementing the treatment. After implementation, repeat the same query against the same corpus. A fix passes only when all success criteria hold and the baseline suite does not materially regress.
