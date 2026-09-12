import time
from typing import Any, Dict, List

import gridfs
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from .config import settings


client = MongoClient(settings.mongo_connection_uri, serverSelectionTimeoutMS=5000)
database = client[settings.mongodb_database]
documents = database["documents"]
chunks = database["chunks"]
raw_files = gridfs.GridFSBucket(database, bucket_name="raw_files")


def ensure_database() -> None:
    client.admin.command("ping")
    documents.create_index([("created_at", DESCENDING)])
    chunks.create_index([("document_id", ASCENDING), ("chunk_index", ASCENDING)])

    existing: List[Dict[str, Any]] = list(chunks.list_search_indexes())
    if any(index.get("name") == settings.mongodb_vector_index for index in existing):
        return

    model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": settings.embedding_dimensions,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "document_id"},
            ]
        },
        name=settings.mongodb_vector_index,
        type="vectorSearch",
    )
    try:
        chunks.create_search_index(model=model)
    except OperationFailure as exc:
        if "already exists" not in str(exc).lower():
            raise


def vector_index_status() -> str:
    try:
        for index in chunks.list_search_indexes():
            if index.get("name") == settings.mongodb_vector_index:
                if index.get("queryable"):
                    return "ready"
                return index.get("status", "building").lower()
        return "missing"
    except PyMongoError:
        return "unavailable"


def wait_for_vector_index(timeout_seconds: int = 45) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if vector_index_status() == "ready":
            return True
        time.sleep(1)
    return False
