import io
from datetime import datetime, timezone
from typing import Dict, List

from bson import ObjectId
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable

from .config import settings
from .database import chunks, documents, raw_files
from .embeddings import get_embeddings
from .extractors import extract_documents
from .source_metadata import extract_source_metadata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(document_id: ObjectId, stage: str, progress: int, **fields: object) -> None:
    documents.update_one(
        {"_id": document_id},
        {"$set": {"stage": stage, "progress": progress, "updated_at": _now(), **fields}},
    )


@traceable(name="document-ingestion", run_type="chain")
def ingest_document(document_id_text: str) -> None:
    document_id = ObjectId(document_id_text)
    record = documents.find_one({"_id": document_id})
    if not record:
        return

    try:
        _set_status(document_id, "extracting", 20)
        stream = raw_files.open_download_stream(record["raw_file_id"])
        data = stream.read()
        extracted = extract_documents(record["filename"], data)
        source_metadata = extract_source_metadata(item.page_content for item in extracted)
        character_count = sum(len(item.page_content) for item in extracted)
        if not character_count:
            raise ValueError("The document did not contain readable text.")

        _set_status(document_id, "chunking", 42, character_count=character_count)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            add_start_index=True,
        )
        split_documents: List[Document] = splitter.split_documents(extracted)
        split_documents = [item for item in split_documents if item.page_content.strip()]
        if not split_documents:
            raise ValueError("The document produced no searchable chunks.")

        _set_status(document_id, "embedding", 58, chunk_count=len(split_documents))
        vectors = get_embeddings().embed_documents([item.page_content for item in split_documents])
        if vectors and len(vectors[0]) != settings.embedding_dimensions:
            raise ValueError(
                f"Embedding model returned {len(vectors[0])} dimensions, but EMBEDDING_DIMENSIONS is "
                f"{settings.embedding_dimensions}. Update .env and recreate the vector index."
            )

        _set_status(document_id, "storing", 82, vector_count=len(vectors))
        chunks.delete_many({"document_id": document_id_text})
        rows: List[Dict[str, object]] = []
        for index, (item, vector) in enumerate(zip(split_documents, vectors)):
            rows.append(
                {
                    "document_id": document_id_text,
                    "filename": record["filename"],
                    "chunk_index": index,
                    "content": item.page_content,
                    "page": item.metadata.get("page"),
                    "section": item.metadata.get("section"),
                    "start_index": item.metadata.get("start_index"),
                    "embedding": [float(value) for value in vector],
                    **source_metadata,
                    "created_at": _now(),
                }
            )
        if rows:
            chunks.insert_many(rows)

        _set_status(
            document_id,
            "ready",
            100,
            status="ready",
            chunk_count=len(rows),
            vector_count=len(rows),
            embedding_dimensions=settings.embedding_dimensions,
            source_metadata=source_metadata,
            parser_version=2,
            completed_at=_now(),
            error=None,
        )
    except Exception as exc:
        chunks.delete_many({"document_id": document_id_text})
        _set_status(document_id, "failed", 100, status="failed", error=str(exc))
