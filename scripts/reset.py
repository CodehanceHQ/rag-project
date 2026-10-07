"""Empty the database: every document, chunk, vector and original file.

The collections and their search indexes stay in place, so the API keeps
working and does not need a restart. MongoDB must be running.

    make reset          # asks first
    make reset YES=1    # no question
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pymongo.errors import PyMongoError  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import chunks, database, documents  # noqa: E402

try:
    found = documents.count_documents({}), chunks.count_documents({})
except PyMongoError:
    sys.exit("MongoDB is not reachable. Start it with `make db-up` and try again.")

print(f"Database '{settings.mongodb_database}' holds {found[0]} document(s) and {found[1]} chunk(s).")
if not any(found) and not database["raw_files.files"].count_documents({}):
    print("Already empty.")
    sys.exit(0)

if not os.environ.get("YES"):
    if input("Delete all of it? This cannot be undone. [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing deleted.")
        sys.exit(0)

for name in ("chunks", "documents", "raw_files.files", "raw_files.chunks"):
    database[name].delete_many({})
print("Database emptied.")
