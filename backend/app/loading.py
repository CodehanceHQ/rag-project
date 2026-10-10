"""Load each model once, and only one model at a time.

The libraries that load models are not safe to use from two threads at once:
a search that loads the reranker while ingestion is loading the embedding
model can leave one of them half built ("Cannot copy out of meta tensor").
Every loader therefore takes the same lock, and keeps what it loaded.
"""
import threading
from functools import lru_cache, wraps

_loading = threading.RLock()


def load_once(maxsize: int = 1):
    def decorate(loader):
        cached = lru_cache(maxsize=maxsize)(loader)

        @wraps(loader)
        def locked(*args, **kwargs):
            with _loading:
                return cached(*args, **kwargs)

        locked.cache_clear = cached.cache_clear
        return locked
    return decorate
