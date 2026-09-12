import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langsmith import traceable
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from .config import settings
from .database import chunks, documents, ensure_database, raw_files, vector_index_status
from .embeddings import get_embeddings
from .extractors import SUPPORTED_EXTENSIONS
from .ingestion import ingest_document


def _serialize_document(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(record["_id"]),
        "filename": record["filename"],
        "content_type": record.get("content_type"),
        "size_bytes": record.get("size_bytes", 0),
        "status": record.get("status", "processing"),
        "stage": record.get("stage", "uploaded"),
        "progress": record.get("progress", 0),
        "character_count": record.get("character_count", 0),
        "chunk_count": record.get("chunk_count", 0),
        "vector_count": record.get("vector_count", 0),
        "embedding_dimensions": record.get("embedding_dimensions"),
        "raw_file_id": str(record["raw_file_id"]),
        "created_at": record["created_at"].isoformat(),
        "error": record.get("error"),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database()
    yield


app = FastAPI(title="Local RAG Studio API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)
    document_id: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        documents.database.client.admin.command("ping")
        return {
            "status": "ok",
            "database": "connected",
            "vector_index": vector_index_status(),
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {exc}")


@app.get("/config")
def public_config() -> Dict[str, Any]:
    return {
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "max_upload_mb": settings.max_upload_mb,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
    }


@app.post("/documents", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="The uploaded file has no filename.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Files are limited to {settings.max_upload_mb} MB.")

    extension = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {extension or 'unknown'}")

    now = datetime.now(timezone.utc)
    raw_file_id = raw_files.upload_from_stream(
        file.filename,
        io.BytesIO(data),
        metadata={"content_type": file.content_type, "uploaded_at": now},
    )
    result = documents.insert_one(
        {
            "filename": file.filename,
            "content_type": file.content_type or "application/octet-stream",
            "size_bytes": len(data),
            "raw_file_id": raw_file_id,
            "status": "processing",
            "stage": "uploaded",
            "progress": 8,
            "chunk_count": 0,
            "vector_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    background_tasks.add_task(ingest_document, str(result.inserted_id))
    record = documents.find_one({"_id": result.inserted_id})
    return _serialize_document(record)


@app.get("/documents")
def list_documents() -> List[Dict[str, Any]]:
    return [_serialize_document(record) for record in documents.find().sort("created_at", -1)]


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> Dict[str, Any]:
    try:
        record = documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        record = None
    if not record:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _serialize_document(record)


@app.get("/documents/{document_id}/raw")
def download_raw_document(document_id: str) -> StreamingResponse:
    try:
        record = documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        record = None
    if not record:
        raise HTTPException(status_code=404, detail="Document not found.")
    stream = raw_files.open_download_stream(record["raw_file_id"])

    def iter_file():
        try:
            while data := stream.read(1024 * 1024):
                yield data
        finally:
            stream.close()

    headers = {"Content-Disposition": f'attachment; filename="{record["filename"]}"'}
    return StreamingResponse(iter_file(), media_type=record.get("content_type"), headers=headers)


@app.get("/documents/{document_id}/chunks")
def inspect_chunks(document_id: str, limit: int = Query(default=8, ge=1, le=50)) -> List[Dict[str, Any]]:
    output = []
    cursor = chunks.find({"document_id": document_id}).sort("chunk_index", 1).limit(limit)
    for row in cursor:
        vector = row.get("embedding", [])
        output.append(
            {
                "id": str(row["_id"]),
                "chunk_index": row["chunk_index"],
                "page": row.get("page"),
                "section": row.get("section"),
                "content": row["content"],
                "embedding_dimensions": len(vector),
                "embedding_preview": vector[:10],
            }
        )
    return output


@app.post("/search")
@traceable(name="mongodb-vector-retrieval", run_type="retriever")
def semantic_search(request: SearchRequest) -> Dict[str, Any]:
    if vector_index_status() != "ready":
        raise HTTPException(status_code=503, detail="The vector index is still building. Try again shortly.")

    vector = get_embeddings().embed_query(request.query)
    vector_search: Dict[str, Any] = {
        "index": settings.mongodb_vector_index,
        "path": "embedding",
        "queryVector": [float(value) for value in vector],
        "numCandidates": max(request.limit * 15, 100),
        "limit": request.limit,
    }
    if request.document_id:
        vector_search["filter"] = {"document_id": {"$eq": request.document_id}}

    pipeline = [
        {"$vectorSearch": vector_search},
        {
            "$project": {
                "_id": 1,
                "document_id": 1,
                "filename": 1,
                "chunk_index": 1,
                "page": 1,
                "section": 1,
                "content": 1,
                "embedding": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    try:
        matches = list(chunks.aggregate(pipeline))
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}")

    return {
        "query": request.query,
        "embedding_dimensions": len(vector),
        "results": [
            {
                "id": str(row["_id"]),
                "document_id": row["document_id"],
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "page": row.get("page"),
                "section": row.get("section"),
                "content": row["content"],
                "score": row.get("score", 0),
                "embedding_preview": row.get("embedding", [])[:8],
            }
            for row in matches
        ],
    }
