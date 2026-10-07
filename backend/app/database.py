import time
from typing import Any, Dict, List

import gridfs
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from .config import settings
from .source_metadata import extract_source_metadata


client = MongoClient(settings.mongo_connection_uri, serverSelectionTimeoutMS=5000)
database = client[settings.mongodb_database]
documents = database["documents"]
chunks = database["chunks"]
raw_files = gridfs.GridFSBucket(database, bucket_name="raw_files")


def ensure_database() -> None:
    client.admin.command("ping")
    documents.create_index([("created_at", DESCENDING)])
    chunks.create_index([("document_id", ASCENDING), ("chunk_index", ASCENDING)])
    chunks.create_index([("source_status", ASCENDING), ("effective_date", DESCENDING)])
    _backfill_source_metadata()

    existing: List[Dict[str, Any]] = list(chunks.list_search_indexes())
    vector_definition = {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": settings.embedding_dimensions,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "document_id"},
            {"type": "filter", "path": "source_status"},
            {"type": "filter", "path": "effective_date"},
        ]
    }
    text_definition = {
        "mappings": {
            "dynamic": False,
            "fields": {
                "content": {"type": "string", "indexOptions": "offsets", "store": True, "norms": "include"},
                "filename": {"type": "string", "indexOptions": "offsets", "store": True, "norms": "include"},
                "document_id": {"type": "token", "normalizer": "lowercase"},
                "source_status": {"type": "token", "normalizer": "lowercase"},
                "record_id": {"type": "token", "normalizer": "lowercase"},
                "effective_date": {"type": "date"},
            },
        }
    }
    _ensure_search_index(existing, settings.mongodb_vector_index, vector_definition, "vectorSearch")
    _ensure_search_index(existing, settings.mongodb_text_index, text_definition, "search")


def _ensure_search_index(
    existing: List[Dict[str, Any]],
    name: str,
    definition: Dict[str, Any],
    index_type: str,
) -> None:
    current = next((index for index in existing if index.get("name") == name), None)
    try:
        if current:
            if current.get("latestDefinition") != definition:
                if index_type == "vectorSearch":
                    # Atlas Local cannot update vector definitions in place. The index is
                    # derived from stored embeddings, so recreate it without touching data.
                    chunks.drop_search_index(name)
                    chunks.create_search_index(
                        model=SearchIndexModel(definition=definition, name=name, type=index_type)
                    )
                else:
                    chunks.update_search_index(name, definition)
            return
        chunks.create_search_index(
            model=SearchIndexModel(definition=definition, name=name, type=index_type)
        )
    except OperationFailure as exc:
        if "already exists" not in str(exc).lower():
            raise


def _backfill_source_metadata() -> None:
    for record in documents.find(
        {"status": "ready", "source_metadata": {"$exists": False}},
        {"_id": 1},
    ):
        document_id = str(record["_id"])
        rows = list(
            chunks.find({"document_id": document_id}, {"content": 1})
            .sort("chunk_index", ASCENDING)
            .limit(4)
        )
        metadata = extract_source_metadata(row.get("content", "") for row in rows)
        documents.update_one({"_id": record["_id"]}, {"$set": {"source_metadata": metadata}})
        chunks.update_many({"document_id": document_id}, {"$set": metadata})


def search_index_status(name: str) -> str:
    try:
        for index in chunks.list_search_indexes():
            if index.get("name") == name:
                if index.get("queryable"):
                    return "ready"
                return index.get("status", "building").lower()
        return "missing"
    except PyMongoError:
        return "unavailable"


def vector_index_status() -> str:
    return search_index_status(settings.mongodb_vector_index)


def wait_for_vector_index(timeout_seconds: int = 45) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if vector_index_status() == "ready":
            return True
        time.sleep(1)
    return False
