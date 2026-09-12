# Northstar Analytics learning corpus

This directory contains fictional company documents designed to make the strengths and weaknesses of retrieval-augmented generation visible. No policy applies to a real company or person.

## What to upload

Start by uploading the files in `policies/`, `procedures/`, and `reference/`. Ask the baseline questions in `../evaluations/questions.json`, then add `conflicting-versions/` and `noise/` to see how retrieval changes.

Do not upload the `evaluations` directory. It contains expected answers and would leak the answers into the searchable collection.

## Suggested experiments

### 1. Direct factual retrieval

Ask: `How many annual leave days does a full-time employee receive?`

The current policy states 25 days. This is the simplest RAG case because the question and source use similar language and the answer is contained in one passage.

### 2. Version conflicts

Upload `conflicting-versions/annual-leave-policy-2024-superseded.md`, then repeat the leave question. The old document says 20 days. A vector database understands textual similarity, not which policy is authoritative. Filenames and text can help a person spot the conflict, but production systems need structured version metadata and retrieval filters.

### 3. Amendments and multi-document reasoning

Upload `conflicting-versions/annual-leave-amendment-2026-07.md` and ask: `How much leave can I carry into 2027?`

The base 2026 policy says five days, while the later amendment changes this to eight. Retrieval may return either or both passages. An answer layer must resolve effective dates and cite the controlling source.

### 4. Exact values in tables

Ask about a specific city in `reference/regional-travel-rates.csv`. Embeddings often retrieve the right table, but preserving the relationship between a city and its exact numeric value can be fragile when tables are large or split across chunks.

### 5. Cross-document questions

Ask: `What should I do if a company laptop containing Confidential data is stolen?`

A complete response needs the information-security policy, data-classification policy, and incident-response procedure. Basic nearest-neighbor retrieval can find individually relevant passages but does not itself combine them into a complete answer.

### 6. Ambiguity and retrieval noise

After adding `noise/office-facilities-guide.md`, ask: `What is the allowance for Valencia?`

The question does not say whether it means a travel hotel cap, meal allowance, or office bicycle allowance. A reliable system should ask for clarification. Retrieval alone will still return whichever vector is closest.

### 7. Missing answers

Ask: `Does Northstar provide dental insurance?`

No document answers this. The current application will still return nearest passages because vector search always ranks something. A generated-answer system needs a relevance threshold and an explicit abstention rule.

## What this corpus demonstrates

| Scenario | What to observe | Production requirement |
| --- | --- | --- |
| Direct fact | Correct passage ranks highly | Good extraction, chunking, and embeddings |
| Paraphrase | Different wording still matches | Semantic embeddings |
| Exact code or number | Similarity may be less reliable | Keyword or hybrid search |
| Conflicting versions | Old and current facts both appear | Version metadata and filters |
| Amendment | Authority is spread across documents | Effective-date logic and reranking |
| Cross-document answer | Several passages are required | Query decomposition and answer synthesis |
| Missing answer | Search still returns something | Thresholds, abstention, and evaluation |
| Noise | Plausible but irrelevant text may rank | Reranking and better scope controls |
| Tables | Row relationships can be lost | Structure-aware parsing and chunking |
| Sensitive policy | Same index exposes all uploaded text | Authentication and document-level access control |

## A useful test routine

1. Upload only the current policies and run the baseline questions.
2. Record the top result, its score, and whether the expected source appears in the top three.
3. Add the superseded policy and amendment, then repeat the version-sensitive questions.
4. Add the noise document and repeat ambiguous and missing-answer questions.
5. Change one variable at a time, such as chunk size, overlap, result count, embedding model, or query wording.
6. Delete a source through the application and confirm that it no longer appears in retrieval or MongoDB.

The evaluation file uses expected facts and source filenames rather than fixed similarity scores. Scores depend on the embedding model, chunking settings, and corpus contents.
