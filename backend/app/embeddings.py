from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from .config import settings


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def count_tokens(text: str) -> int:
    """How many tokens the embedding model sees in this text."""
    tokenizer = get_embeddings()._client.tokenizer
    return len(tokenizer.encode(text, add_special_tokens=False, verbose=False))


@lru_cache(maxsize=1)
def token_budget() -> int:
    """The most tokens one chunk may hold. The model reads a fixed number and
    silently ignores the rest; two of those are its own start and end markers."""
    limit = int(get_embeddings()._client.max_seq_length) - 2
    return min(settings.chunk_tokens, limit) if settings.chunk_tokens > 0 else limit
