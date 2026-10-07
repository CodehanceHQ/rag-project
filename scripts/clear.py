"""Wipe the database clean: drop it, with every document, chunk, vector,
original file and search index, then build the empty collections and fresh
search indexes again so the API works without a restart. MongoDB must be
running.

    make clear          # asks first
    make clear YES=1    # no question
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pymongo.errors import PyMongoError  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import (chunks, client, documents, ensure_database,  # noqa: E402
                          search_index_status)

try:
    found = documents.count_documents({}), chunks.count_documents({})
except PyMongoError:
    sys.exit("MongoDB is not reachable. Start it with `make db-up` and try again.")

name = settings.mongodb_database
print(f"Database '{name}' holds {found[0]} document(s) and {found[1]} chunk(s).")

if not os.environ.get("YES"):
    answer = input("Wipe it, search indexes included? This cannot be undone. [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        print("Nothing deleted.")
        sys.exit(0)

# Search indexes belong to their collection, but drop them by name first so
# none is left behind half-removed when the database goes.
for index in list(chunks.list_search_indexes()):
    chunks.drop_search_index(index["name"])
client.drop_database(name)
print("Database dropped.")

print("Building empty collections and fresh search indexes ...")
ensure_database()
deadline = time.time() + 90
while time.time() < deadline:
    states = [search_index_status(settings.mongodb_vector_index),
              search_index_status(settings.mongodb_text_index)]
    if states == ["ready", "ready"]:
        break
    time.sleep(1)
print(f"Vector index: {states[0]}. Text index: {states[1]}.")
print("Database wiped clean.")
