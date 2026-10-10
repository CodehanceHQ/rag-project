# RAG Project

A retrieval-augmented generation (RAG) system that runs on your own machine. You give it documents; it splits them into passages, stores them in a searchable form, and answers questions from the passages it finds.

## Quick start

You need [OrbStack](https://orbstack.dev/) (or another Docker engine) running, Python 3.10 or newer, Node.js 20.9 or newer, and `make`.

```bash
open -a OrbStack   # start the Docker engine, if it isn't running
make start
```

Then open <http://localhost:13001>.

`make start` checks your dependencies, installs the project the first time, starts MongoDB, and starts the API and the UI. It is safe to run again: anything already running is left alone. `Ctrl+C` stops the API and the UI; MongoDB keeps running until `make db-down`.

The first run downloads the MongoDB image and the embedding model, so it takes a few minutes. The first search downloads the reranker, which is about 8 GB.

### Load the sample corpus

The application starts empty. You can drop your own files into the UI, or load the 100-document sample corpus that ships with the project: the paperwork of a fictional bakery company. With the system running, in a second terminal:

```bash
.venv/bin/python corpus/generate/ingest.py
```

Expect 99 of 100 documents to load. `inspection_cert_scanned.pdf` is a scanned image with no text, included on purpose to show that limitation.

## How it works

RAG has two halves. **Ingestion** happens once per document and prepares it for search. **Retrieval and answering** happens on every question.

### The parts

```mermaid
flowchart LR
    U[You] --> UI[Next.js UI<br/>port 13001]
    UI --> API[FastAPI backend<br/>port 18001]
    API --> EMB[Embedding model<br/>runs locally]
    API --> RR[Reranker model<br/>runs locally]
    API --> DB[(MongoDB Atlas Local<br/>port 27018)]
    API -. optional .-> LLM[OpenRouter<br/>language model]

    subgraph DB_CONTENTS[Inside MongoDB]
        RAW[(Original files)]
        CHUNKS[(Chunks: text + vectors)]
        VI[(Vector index)]
        TI[(Full-text index)]
    end
    DB --- DB_CONTENTS
```

Everything runs on your machine except the optional language model call. MongoDB is the only part that runs in a container.

### Ingestion: from a file to searchable chunks

```mermaid
sequenceDiagram
    actor User
    participant UI as UI
    participant API as API
    participant DB as MongoDB
    participant Embed as Embedding model

    User->>UI: Drop a document
    UI->>API: POST /documents
    API->>DB: Store the original file
    API-->>UI: Document ID
    Note over API: Background job starts
    API->>API: Extract text, page by page
    API->>API: Split into overlapping chunks
    API->>Embed: Chunks
    Embed-->>API: One vector per chunk
    API->>DB: Store chunk text, vectors and source details
    UI->>API: Poll status until ready
```

1. **Extract.** Text is pulled from the file with its page, slide or sheet number.
2. **Chunk.** The text is cut into pieces small enough to embed. How it is cut is a setting; see [Chunking strategies](#chunking-strategies). The default cuts at paragraph and sentence breaks, with a small overlap between pieces so a sentence cut at a boundary still appears whole in one of them.
3. **Embed.** Each chunk is turned into a vector of 384 numbers that represents its meaning. Chunks with similar meaning get vectors that are close together.
4. **Store.** The chunk text, its vector and where it came from go into MongoDB, which indexes them two ways: by vector and by words.

The system also reads `Status:` and `Effective date:` lines from a document's header, so out-of-date documents can be filtered out later.

### Chunking strategies

`CHUNKING_STRATEGY` in `.env` chooses how documents are cut. Each strategy is one small class in `backend/app/chunking/`.

| Strategy | Where it cuts | Good at | Weak at |
| --- | --- | --- | --- |
| `recursive` (default) | By size, at paragraph, line or sentence breaks | Any text, fast, predictable sizes | Separates a fact from the thing it refers to |
| `structural` | At headings: one chunk per section | Keeping what the author grouped together | Long sections exceed what the embedding model reads |
| `hybrid` | At headings, then by size inside long sections; each piece starts with its document and section name | Pieces that fit the model and still say where they came from | Needs detectable headings |
| `semantic` | Where the topic changes, found by embedding every sentence | Text with no usable structure | Tables and lists; slower to ingest |
| `contextual` | Wherever another strategy cuts; it then adds one model-written sentence to each piece saying what it is about | Pieces that depend on a neighbour, such as "Set it to 230 °C" | Needs a second, larger model: slow if run locally, paid if hosted |

`contextual` needs a model that can write, which the embedding model cannot do. `CONTEXTUAL_BASE_STRATEGY` chooses which of the other four strategies does the cutting, and `CONTEXTUAL_PROVIDER` chooses where the writing model runs:

| Provider | Where | Cost | Speed | Privacy |
| --- | --- | --- | --- | --- |
| `local` (default) | A Hugging Face model on your machine, `Qwen/Qwen3.5-9B` unless you set `CONTEXTUAL_LOCAL_MODEL` | Free | A few seconds per chunk; hours for the whole sample corpus | Nothing leaves your machine |
| `openrouter` | A hosted model | Paid: one call per chunk, about 4,000 for the sample corpus | Minutes for the whole corpus | Document text is sent to the provider |

The local model downloads the first time it is used, about 19 GB for the default. A smaller one such as `HuggingFaceTB/SmolLM3-3B` (about 6 GB) is faster and needs less memory. To swap it, set `CONTEXTUAL_LOCAL_MODEL` to another Hugging Face chat model.

Chunk size is measured in tokens, the unit the embedding model counts in, not characters. The model reads a fixed number of tokens (256 for the default model) and ignores anything beyond that, and a table of numbers uses far more tokens per character than prose. So `recursive`, `hybrid`, `semantic` and `contextual` never produce a chunk longer than the model reads. `structural` is the exception: it keeps each section whole, however long.

To try one, set it in `.env`, restart the API, and re-ingest everything:

```bash
.venv/bin/python corpus/generate/ingest.py --fresh
```

`--fresh` deletes the documents already stored, so the whole corpus is chunked and embedded again. Each chunk and document records the strategy that produced it, and `/health` shows the one in use. Run the evaluations after each change to compare.

### Retrieval: from a question to passages

```mermaid
flowchart TD
    Q[Question] --> E[Embed the question]
    E --> V[Vector search<br/>30 candidates by meaning]
    Q --> T[Full-text search<br/>30 candidates by words]
    V --> F[Fuse the two rankings]
    T --> F
    F --> R[Rerank each candidate<br/>against the question]
    R --> TH{Any above the<br/>relevance threshold?}
    TH -- no --> AB[Abstain]
    TH -- yes --> P[Top passages]
    P --> G[Language model answers<br/>from those passages]
```

1. **Filter.** Documents marked as superseded are excluded unless you ask for them.
2. **Search twice.** Vector search finds chunks that mean something similar to the question. Full-text search finds chunks that share its words. Each returns up to 30 candidates.
3. **Fuse.** The two ranked lists are merged with reciprocal rank fusion, which combines positions and ignores the raw scores, because the two kinds of score aren't comparable.
4. **Rerank.** A second model reads the question and each candidate together and scores how well they match. This is slower and more accurate than the first search.
5. **Threshold.** Passages scoring below 0.15 are dropped. If none remain, the system abstains instead of guessing.
6. **Answer.** The top passages are pasted into a prompt and a language model answers from them, citing passages by number.

The UI also has a **vector-only** mode that does step 2's vector search and nothing else, so you can compare a bare baseline with the full pipeline.

An optional **ambiguity check** runs when the top two passages score almost the same: a language model decides whether the question has several readings and, if so, offers you choices.

### What this design cannot do

The pipeline retrieves once. Reranking only reorders what the first search found, so if the right passage never made the candidate list, nothing later can recover it. And the language model cannot ask for anything it wasn't handed.

That is fine when the answer sits in one passage. It breaks down in four situations:

| Situation | Example |
| --- | --- |
| Multi-hop | You need fact A before you know to look for fact B |
| Long-distance evidence | The answer is spread across documents, and no single chunk resembles the question |
| Chunks that lost their context | "Set it to 230 °C" never says what *it* is |
| Aggregation | "What is the trend across these twelve reports?" needs many reads, not a top five |

The sample corpus is built to trigger each of these.

## Using it

**In the UI** (<http://localhost:13001>): drop documents in, watch them ingest, inspect the stored chunks and vectors, and run searches. Results show the vector, full-text, fusion and reranker scores separately. The strip above the results names the chunking strategy and each stage of the pipeline; click a stage to see its list and what became of every candidate. The last step on the strip writes an answer from the top passages, with the passages it cited marked.

**Through the API** (<http://localhost:18001/docs> lists every endpoint):

```bash
# passages only
curl -s -X POST http://localhost:18001/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "What was found wrong with batch 4471?"}' | jq

# passages plus a generated answer (needs OPENROUTER_API_KEY, or ANSWER_PROVIDER=local)
curl -s -X POST http://localhost:18001/answer \
  -H 'Content-Type: application/json' \
  -d '{"query": "What was found wrong with batch 4471?"}' | jq
```

## Evaluating it

Both evaluations need the sample corpus loaded.

**Retrieval** checks which documents came back. Use **Run evaluation** in the UI, or:

```bash
curl -s -X POST http://localhost:18001/evaluations/run | jq
```

**Answers** checks what the system said: whether it stated the expected fact, avoided the known wrong one, and whether every named claim appears in a passage it cited. It needs `OPENROUTER_API_KEY`.

```bash
.venv/bin/python evaluations/answer_eval/run.py --system path-a
```

Add `--no-judge` to skip the model-graded questions and avoid that cost, or `--only sh-01,mh-01` to run a subset.

Single-hop questions should pass. Multi-hop and long-distance questions are expected to fail; they mark the limit described above. See [corpus/README.md](corpus/README.md) for how the corpus and its questions are built.

## Configuration

Settings live in `.env`, which `make setup` creates from `.env.example`. Ingestion and retrieval need no API key.

| Setting | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Enables hosted answers and the ambiguity check. Without it, search still works, and answers work with `ANSWER_PROVIDER=local`. |
| `OPENROUTER_MODEL` | The hosted language model used for both |
| `ANSWER_PROVIDER` | Who writes the answer: `openrouter` (hosted, paid) or `local` (a Hugging Face model on your machine, free and slower). |
| `ANSWER_LOCAL_MODEL` | The local answering model, `Qwen/Qwen3.5-9B` by default: about 19 GB to download and to hold in memory. |
| `CHUNKING_STRATEGY` | How documents are cut into chunks: `recursive`, `structural`, `hybrid`, `semantic` or `contextual`. Re-ingest after changing it. |
| `CONTEXTUAL_BASE_STRATEGY` | For `contextual` only: the strategy that does the cutting. |
| `CONTEXTUAL_PROVIDER` | For `contextual` only: `local` (a Hugging Face model on your machine) or `openrouter` (hosted, paid). |
| `CONTEXTUAL_LOCAL_MODEL`, `CONTEXTUAL_MODEL` | The model that writes the sentence: locally, and hosted (blank uses `OPENROUTER_MODEL`). |
| `CHUNK_TOKENS`, `CHUNK_OVERLAP_TOKENS` | Largest chunk and the overlap between chunks, in embedding-model tokens. `CHUNK_TOKENS=0` means as many as the model reads. |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | The local embedding model. Change both together, then re-ingest every document. |
| `RERANKER_MODEL` | The local reranker. The default, `Qwen/Qwen3-Reranker-4B`, is about 8 GB on disk and in memory. `cross-encoder/ms-marco-MiniLM-L-6-v2` is a small, fast alternative. Recalibrate `MINIMUM_RELEVANCE_SCORE` after changing it. |
| `RERANKER_MAX_TOKENS` | The most tokens of question and chunk the reranker reads (1024). Longer chunks are cut off there, which keeps a very long chunk from exhausting memory. |
| `MINIMUM_RELEVANCE_SCORE` | The abstain threshold (0.15). Recalibrate it if you change the corpus or either model. |
| `LANGSMITH_TRACING` | Optional tracing, off by default |

Restart the API after changing `.env`. When an OpenRouter key is set, your question and the retrieved passages are sent to that provider, so don't enable it for documents that mustn't leave your machine.

Supported files: PDF, DOCX, PPTX, XLSX, CSV, HTML, TXT, Markdown, JSON, XML, YAML and common source-code files. Scanned PDFs need OCR, which isn't included.

## Where the data lives

Everything is in the MongoDB database `rag_project`, kept in Docker volumes that survive restarts.

| Collection | Contents |
| --- | --- |
| `documents` | One record per upload: filename, status, counts |
| `chunks` | Chunk text, its vector, page and source status |
| `raw_files.files`, `raw_files.chunks` | The original uploaded files |

To browse it, connect [MongoDB Compass](https://www.mongodb.com/products/tools/compass) to:

```text
mongodb://rag:rag-local-password@localhost:27018/?authSource=admin&directConnection=true
```

To wipe the database and start again, run `make clear`. It drops the database, with every document, chunk, vector, original file and search index, then rebuilds the empty search indexes so the API keeps working. It asks before doing so.

Delete single documents through the UI, not directly in the database, so the file, its chunks and its record are removed together. `docker compose down -v` deletes all stored data.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `make start` stops at the checks | Follow the `fix:` line printed under each failure |
| "API offline" in the UI | Check <http://localhost:18001/health>; if MongoDB is down, run `make db-up` |
| "The vector index is still building" | Wait a few seconds after first start and retry |
| First upload or first search is slow | The embedding model and the reranker (about 8 GB) download once, then are cached |
| A PDF reports that no text was found | It is a scanned image; OCR isn't included |
| `make start` says a port is in use by another program | It names the program and its PID; stop that program and run `make start` again |
