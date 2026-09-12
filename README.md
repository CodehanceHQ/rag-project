# Local RAG Studio

A local-first document ingestion and semantic retrieval application. Original files are stored in MongoDB GridFS, while extracted chunks, metadata, and Hugging Face embeddings are stored in a MongoDB collection with a Vector Search index.

The repository includes a fictional [RAG learning corpus](sample-documents/README.md), separate [baseline](evaluations/questions.json) and [conflict-and-noise](evaluations/conflict-and-noise-questions.json) question sets, and an [evaluation guide](evaluations/README.md). The corpus demonstrates direct retrieval, paraphrases, exact values, tables, conflicting policy versions, amendments, multi-document questions, ambiguity, irrelevant noise, and questions that should not be answered.

## Architecture

- Next.js UI: drag-and-drop, ingestion progress, storage inspection, retrieval
- FastAPI: uploads, parsing, embedding, MongoDB access
- MongoDB Atlas Local: raw GridFS files plus vectorized chunks
- Hugging Face Sentence Transformers: local embeddings
- LangChain: document representation, chunking, and embedding integration
- LangSmith: optional tracing, disabled by default
- OrbStack: lightweight Docker-compatible runtime for MongoDB Atlas Local

### How the pieces interact

```mermaid
flowchart LR
    U[User] -->|drops a file or asks a question| UI[Next.js web interface]
    UI -->|HTTP requests| API[FastAPI backend]

    subgraph MAC[Your Mac]
        UI
        API
        EX[Document extractors<br/>PyMuPDF and Office parsers]
        LC[LangChain<br/>documents and text splitting]
        HF[Hugging Face model<br/>local embeddings]

        subgraph ORB[OrbStack Linux VM]
            subgraph MONGO[MongoDB Atlas Local]
                DOCS[(documents collection<br/>status and metadata)]
                RAW[(GridFS<br/>original file bytes)]
                CHUNKS[(chunks collection<br/>text and embedding arrays)]
                INDEX[(Vector Search index)]
                CHUNKS --> INDEX
            end
        end
    end

    API --> EX
    EX --> LC
    LC --> HF
    API --> DOCS
    API --> RAW
    HF -->|384-number vectors| CHUNKS
    API -->|vector query| INDEX
    INDEX -->|closest chunks and scores| API
    API -->|passages and source metadata| UI

    API -. optional traces when enabled .-> LS[LangSmith cloud]

    classDef interface fill:#d8ff57,stroke:#173f30,color:#17211d;
    classDef service fill:#faf9f5,stroke:#66716b,color:#17211d;
    classDef storage fill:#173f30,stroke:#173f30,color:#ffffff;
    class UI interface;
    class API,EX,LC,HF service;
    class DOCS,RAW,CHUNKS,INDEX storage;
```

The frontend and backend run as normal macOS processes. Only MongoDB Atlas Local runs in a container. OrbStack supplies the lightweight Linux environment required by that container.

### Upload and vectorization flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Next.js UI
    participant API as FastAPI
    participant DB as MongoDB / GridFS
    participant Parser as Document parser
    participant Embed as Hugging Face embeddings

    User->>UI: Drop document
    UI->>API: POST /documents
    API->>DB: Store original bytes in GridFS
    API->>DB: Create processing record
    API-->>UI: Return document ID
    loop While processing
        UI->>API: Poll document status
        API-->>UI: Stage and percentage
    end
    API->>Parser: Extract text and source locations
    Parser->>API: Pages, slides, sheets, or plain text
    API->>API: Split text into overlapping chunks
    API->>Embed: Encode chunks locally
    Embed-->>API: Embedding vectors
    API->>DB: Store chunk text, metadata, and vectors
    API->>DB: Mark document ready
```

### Retrieval flow

1. The user writes a natural-language question.
2. The same Hugging Face model converts that question into a 384-dimensional vector.
3. MongoDB Vector Search compares the question vector with the stored chunk vectors.
4. MongoDB returns the closest chunks with similarity scores.
5. The UI displays the passages, filenames, pages or sections, and scores.

This version performs **retrieval**, not generated question answering. It deliberately shows the source passages so you can learn how semantic search behaves before adding an LLM response layer.

### Permanent deletion flow

The document inspector includes a **Delete** action. Before anything is removed, the interface displays a confirmation dialog listing the affected raw file, chunks, vectors, index entries, and metadata. Confirming it calls `DELETE /documents/{document_id}`. The backend removes all chunks, deletes the original GridFS file, and finally deletes the document record. MongoDB automatically removes deleted vectors from the Vector Search index.

Documents cannot be deleted while ingestion is still running. This prevents an active background job from recreating chunks after the source record has been removed.

## Supported documents

PDF, DOCX, PPTX, XLSX, TXT, Markdown, CSV, JSON, HTML, XML, YAML, and common source-code files. Image-only PDFs need OCR, which is not included in this first version.

## Prerequisites

- macOS with [OrbStack](https://orbstack.dev/) installed and running
- Python 3.11
- Node.js 20.9 or newer
- `make`

Confirm that OrbStack is exposing its Docker-compatible engine:

```bash
docker info
docker compose version
```

## First-time setup

1. Install and start OrbStack.
2. Open a terminal in the project directory:

```bash
cd ~/path/to/rag
make setup
```

`make setup` creates `.env` from `.env.example`, creates a Python virtual environment, installs the backend dependencies, and installs the frontend packages.

3. Start MongoDB Atlas Local:

```bash
make db-up
```

The first database startup downloads the Atlas Local image. Wait for it to become healthy:

```bash
docker ps
```

## Run the application

Keep MongoDB running and use two terminal windows.

Terminal 1: start the API:

```bash
cd ~/path/to/rag
make api
```

Terminal 2: start the UI:

```bash
cd ~/path/to/rag
make web
```

Open <http://localhost:3000>.

Useful local URLs:

- Application: <http://localhost:3000>
- API health: <http://localhost:8000/health>
- Interactive API documentation: <http://localhost:8000/docs>

The first ingestion downloads the configured embedding model and can take a minute. Later runs use the local Hugging Face cache. A Hugging Face token is optional for this public model; setting `HF_TOKEN` only increases Hub download rate limits.

## Configuration

Copy `.env.example` to `.env` (automatically done by `make setup`). The default local username and password are shared by the backend and Compose file. No API key is required unless you enable LangSmith tracing. `MONGODB_URI` is intentionally blank for local use; it can hold a full Atlas cloud connection string later.

Do not change `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` after storing documents without rebuilding the vector index and re-ingesting the documents.

## Data persistence

The Compose volumes retain:

- `mongodb_data`: document records, GridFS files, and chunk documents
- `mongodb_search`: MongoDB Vector Search indexes
- `mongodb_config`: replica-set configuration

`docker compose down` stops MongoDB without deleting data. Avoid `docker compose down -v` unless you intentionally want to delete all stored documents and vectors.

## Where each kind of data lives

| Data | Location | Purpose |
| --- | --- | --- |
| Original uploaded bytes | MongoDB GridFS | Download or reprocess the unmodified source file |
| Document metadata | `documents` collection | Filename, MIME type, size, stage, progress, and errors |
| Extracted text | `chunks.content` | Human-readable content returned by retrieval |
| Embeddings | `chunks.embedding` | Numeric representation used for semantic similarity |
| Source metadata | `chunks.page` and `chunks.section` | Connect results to their original location |
| Vector index | MongoDB `chunk_vector_index` | Efficient nearest-neighbor lookup |

## Inspect MongoDB directly

The application inspector shows a convenient preview, but you can also examine the underlying MongoDB records with a graphical application or from the terminal.

### Option 1: MongoDB Compass

[MongoDB Compass](https://www.mongodb.com/products/tools/compass) is the easiest visual database browser.

1. Install and open Compass while OrbStack and the `local-rag-mongodb` container are running.
2. Create a new connection with this local development URI:

```text
mongodb://rag:rag-local-password@localhost:27017/local_rag?authSource=admin&directConnection=true
```

3. Open the `local_rag` database.
4. Select a collection and open its **Documents** tab.

The collections are:

| Collection | Contents |
| --- | --- |
| `documents` | One application record per upload, including status, counts, and its GridFS file ID |
| `chunks` | Extracted text chunks, source metadata, and embedding arrays |
| `raw_files.files` | GridFS filename, size, upload date, and file metadata |
| `raw_files.chunks` | Binary pieces of the original files managed by GridFS |

The `chunks.embedding` field is the actual vector stored as an array of floating-point numbers. Use the application’s **Download raw** action to view an original file; `raw_files.chunks.data` is binary storage rather than extracted text.

If you change `MONGODB_ROOT_USERNAME` or `MONGODB_ROOT_PASSWORD` in `.env`, update the Compass URI accordingly.

### Option 2: `mongosh` inside the container

The Atlas Local image already includes `mongosh`, so you do not need to install the shell separately:

```bash
docker exec -it local-rag-mongodb mongosh \
  --username rag \
  --password rag-local-password \
  --authenticationDatabase admin \
  local_rag
```

Once connected, try these read-only commands:

```javascript
// Show all collections.
show collections

// Count each type of stored object.
db.documents.countDocuments()
db.chunks.countDocuments()
db.raw_files.files.countDocuments()

// Inspect document metadata without printing vectors or binary data.
db.documents.find(
  {},
  { filename: 1, status: 1, size_bytes: 1, chunk_count: 1, vector_count: 1 }
).pretty()

// Inspect chunk text and only the first eight numbers of each vector.
db.chunks.find(
  {},
  { filename: 1, page: 1, section: 1, content: 1, embedding: { $slice: 8 } }
).limit(5).pretty()

// Inspect the raw GridFS file metadata.
db.raw_files.files.find(
  {},
  { filename: 1, length: 1, uploadDate: 1, metadata: 1 }
).pretty()

// Verify that the Vector Search index is ready and queryable.
db.chunks.aggregate([
  { $listSearchIndexes: {} },
  { $project: { name: 1, status: 1, queryable: 1 } }
]).toArray()
```

Run `exit` to leave `mongosh`.

Direct editing or deletion in Compass or `mongosh` can leave GridFS, document metadata, and vectors out of sync. Use the application’s permanent-delete action when removing an uploaded document.

## Stop and restart

Stop the application servers with `Ctrl+C`. Stop MongoDB without deleting its data:

```bash
make db-down
```

Start it again later with:

```bash
make db-up
```

## Troubleshooting

### `API offline` in the interface

Confirm FastAPI is running and check <http://localhost:8000/health>. If MongoDB is unavailable, open OrbStack and run `make db-up` again.

### Vector index is still building

Atlas Local creates the Vector Search index on its first startup. Wait a short time and retry the search. The connection badge in the interface changes to `MongoDB ready` when it is queryable.

### First upload seems slow

The first vectorization downloads `sentence-transformers/all-MiniLM-L6-v2` from Hugging Face. Subsequent uploads reuse the cached model.

### PDF reports that no text was found

The PDF probably contains scanned images rather than embedded text. This version does not yet run OCR.
