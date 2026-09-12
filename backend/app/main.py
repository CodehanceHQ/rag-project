import io
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from gridfs.errors import NoFile
from bson import ObjectId
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langsmith import traceable
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from .config import settings
from .ambiguity import detect_ambiguity
from .database import chunks, documents, ensure_database, raw_files, search_index_status, vector_index_status
from .embeddings import get_embeddings
from .evaluation import assess_case, load_cases
from .extractors import SUPPORTED_EXTENSIONS
from .ingestion import ingest_document
from .retrieval import reciprocal_rank_fusion, rerank


def _serialize_document(record: Dict[str, Any]) -> Dict[str, Any]:
    source_metadata = dict(record.get("source_metadata", {}))
    for field in ("effective_date", "superseded_date"):
        if isinstance(source_metadata.get(field), datetime):
            source_metadata[field] = source_metadata[field].date().isoformat()
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
        "source_metadata": source_metadata,
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
    mode: Literal["vector", "hybrid"] = "hybrid"
    include_superseded: bool = False
    minimum_score: Optional[float] = Field(default=None, ge=0, le=1)


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        documents.database.client.admin.command("ping")
        return {
            "status": "ok",
            "database": "connected",
            "vector_index": vector_index_status(),
            "text_index": search_index_status(settings.mongodb_text_index),
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "reranker_model": settings.reranker_model,
            "minimum_relevance_score": settings.minimum_relevance_score,
            "ambiguity_llm_configured": bool(settings.openrouter_api_key),
            "ambiguity_model": settings.openrouter_model,
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


@app.delete("/documents/{document_id}")
def delete_document(document_id: str) -> Dict[str, Any]:
    try:
        object_id = ObjectId(document_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found.")

    record = documents.find_one({"_id": object_id})
    if not record:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.get("status") == "processing":
        raise HTTPException(
            status_code=409,
            detail="This document is still being processed. Wait for ingestion to finish before deleting it.",
        )

    documents.update_one(
        {"_id": object_id},
        {"$set": {"status": "deleting", "stage": "deleting", "error": None}},
    )
    try:
        chunk_result = chunks.delete_many({"document_id": document_id})
        raw_deleted = True
        try:
            raw_files.delete(record["raw_file_id"])
        except NoFile:
            # A retry after a partial deletion should still remove the metadata record.
            raw_deleted = False
        document_result = documents.delete_one({"_id": object_id})
    except PyMongoError as exc:
        documents.update_one(
            {"_id": object_id},
            {"$set": {"status": "delete_failed", "stage": "delete failed", "error": str(exc)}},
        )
        raise HTTPException(status_code=500, detail=f"Deletion failed and can be retried: {exc}")

    return {
        "deleted": document_result.deleted_count == 1,
        "document_id": document_id,
        "filename": record["filename"],
        "chunks_deleted": chunk_result.deleted_count,
        "raw_file_deleted": raw_deleted,
    }


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


def _metadata_filters(request: SearchRequest) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []
    if request.document_id:
        filters.append({"document_id": {"$eq": request.document_id}})
    if not request.include_superseded:
        filters.append({"source_status": {"$eq": "current"}})
    return filters


def _vector_candidates(request: SearchRequest, vector: List[float], limit: int) -> List[Dict[str, Any]]:
    vector_search: Dict[str, Any] = {
        "index": settings.mongodb_vector_index,
        "path": "embedding",
        "queryVector": [float(value) for value in vector],
        "numCandidates": max(limit * 15, 100),
        "limit": limit,
    }
    filters = _metadata_filters(request)
    if len(filters) == 1:
        vector_search["filter"] = filters[0]
    elif filters:
        vector_search["filter"] = {"$and": filters}
    pipeline = [
        {"$vectorSearch": vector_search},
        {"$project": {
            "document_id": 1, "filename": 1, "chunk_index": 1, "page": 1,
            "section": 1, "content": 1, "embedding": 1, "record_id": 1,
            "source_status": 1, "effective_date": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]
    output = list(chunks.aggregate(pipeline))
    for item in output:
        item["signal"] = "vector"
        item["vector_score"] = float(item.get("score", 0.0))
    return output


def _text_candidates(request: SearchRequest, limit: int) -> List[Dict[str, Any]]:
    search_filters: List[Dict[str, Any]] = []
    if request.document_id:
        search_filters.append({"equals": {"path": "document_id", "value": request.document_id}})
    if not request.include_superseded:
        search_filters.append({"equals": {"path": "source_status", "value": "current"}})
    compound: Dict[str, Any] = {
        "must": [{"text": {"query": request.query, "path": ["content", "filename"]}}],
    }
    if search_filters:
        compound["filter"] = search_filters
    pipeline = [
        {"$search": {"index": settings.mongodb_text_index, "compound": compound}},
        {"$limit": limit},
        {"$project": {
            "document_id": 1, "filename": 1, "chunk_index": 1, "page": 1,
            "section": 1, "content": 1, "embedding": 1, "record_id": 1,
            "source_status": 1, "effective_date": 1,
            "score": {"$meta": "searchScore"},
        }},
    ]
    output = list(chunks.aggregate(pipeline))
    for item in output:
        item["signal"] = "text"
        item["text_score"] = float(item.get("score", 0.0))
    return output


def _serialize_result(row: Dict[str, Any], score: float) -> Dict[str, Any]:
    effective_date = row.get("effective_date")
    return {
        "id": str(row["_id"]),
        "document_id": row["document_id"],
        "filename": row["filename"],
        "chunk_index": row["chunk_index"],
        "page": row.get("page"),
        "section": row.get("section"),
        "content": row["content"],
        "score": score,
        "vector_score": row.get("vector_score"),
        "text_score": row.get("text_score"),
        "fused_score": row.get("fused_score"),
        "reranker_score": row.get("reranker_score"),
        "signals": row.get("signals", [row.get("signal", "vector")]),
        "record_id": row.get("record_id"),
        "source_status": row.get("source_status", "current"),
        "effective_date": effective_date.date().isoformat() if isinstance(effective_date, datetime) else None,
        "embedding_preview": row.get("embedding", [])[:8],
    }


@app.post("/search")
@traceable(name="retrieval-pipeline", run_type="retriever")
def search(request: SearchRequest) -> Dict[str, Any]:
    if vector_index_status() != "ready":
        raise HTTPException(status_code=503, detail="The vector index is still building. Try again shortly.")

    vector = get_embeddings().embed_query(request.query)
    try:
        if request.mode == "vector":
            baseline_request = request.model_copy(update={"include_superseded": True})
            matches = _vector_candidates(baseline_request, vector, request.limit)
            return {
                "query": request.query,
                "mode": "vector",
                "embedding_dimensions": len(vector),
                "abstained": False,
                "decision": "answer",
                "message": None,
                "clarification": None,
                "pipeline": {
                    "vector_candidates": len(matches), "text_candidates": 0,
                    "fused_candidates": 0, "reranked_candidates": 0,
                    "minimum_score": None, "top_reranker_score": None,
                    "ambiguity_status": "not_applicable",
                },
                "results": [_serialize_result(row, float(row.get("score", 0.0))) for row in matches],
            }

        if search_index_status(settings.mongodb_text_index) != "ready":
            raise HTTPException(status_code=503, detail="The text index is still building. Try again shortly.")
        candidate_limit = max(request.limit, settings.retrieval_candidate_limit)
        vector_matches = _vector_candidates(request, vector, candidate_limit)
        text_matches = _text_candidates(request, candidate_limit)
        fused = reciprocal_rank_fusion(
            [vector_matches, text_matches], rank_constant=settings.rrf_rank_constant
        )
        reranked = rerank(request.query, fused[:candidate_limit])
        minimum_score = request.minimum_score if request.minimum_score is not None else settings.minimum_relevance_score
        accepted = [row for row in reranked if row["reranker_score"] >= minimum_score][:request.limit]
        abstained = not accepted
        ambiguity = (
            detect_ambiguity(request.query, accepted)
            if not abstained
            else {"status": "not_applicable", "decision": "abstain"}
        )
        return {
            "query": request.query,
            "mode": "hybrid",
            "embedding_dimensions": len(vector),
            "abstained": abstained,
            "decision": ambiguity["decision"],
            "message": "The available documents do not contain sufficiently relevant evidence." if abstained else None,
            "clarification": ambiguity if ambiguity["decision"] == "clarify" else None,
            "pipeline": {
                "vector_candidates": len(vector_matches),
                "text_candidates": len(text_matches),
                "fused_candidates": len(fused),
                "reranked_candidates": len(reranked),
                "minimum_score": minimum_score,
                "top_reranker_score": reranked[0]["reranker_score"] if reranked else None,
                "ambiguity_status": ambiguity["status"],
            },
            "results": [_serialize_result(row, row["reranker_score"]) for row in accepted],
        }
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")


@app.post("/evaluations/run")
@traceable(name="retrieval-evaluation", run_type="chain")
def run_evaluation() -> Dict[str, Any]:
    started = time.perf_counter()
    cases = []
    for suite, case in load_cases():
        response = search(SearchRequest(
            query=case["question"],
            limit=8,
            mode="hybrid",
            include_superseded=case["expected_behavior"] == "retrieve_historical_answer",
        ))
        passed, detail = assess_case(case, response)
        cases.append({
            "suite": suite,
            "id": case["id"],
            "question": case["question"],
            "expected_behavior": case["expected_behavior"],
            "passed": passed,
            "detail": detail,
            "abstained": response["abstained"],
            "decision": response["decision"],
            "ambiguity_status": response["pipeline"]["ambiguity_status"],
            "top_results": [
                {"filename": item["filename"], "score": item["score"]}
                for item in response["results"][:3]
            ],
        })
    passed_count = sum(case["passed"] for case in cases)
    return {
        "passed": passed_count,
        "failed": len(cases) - passed_count,
        "total": len(cases),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "cases": cases,
    }
