"""Hybrid retrieval: BM25 keyword + vector (RRF fused), then semantic reranker."""
from azure.search.documents.models import VectorizedQuery

from .clients import openai_client, search_client
from .config import get_settings


async def embed(text: str) -> list[float]:
    s = get_settings()
    r = await openai_client().embeddings.create(
        model=s.azure_openai_embedding_deployment, input=text
    )
    return r.data[0].embedding


async def hybrid_search(query: str, k: int = 4) -> list[dict]:
    s = get_settings()
    results = await search_client().search(
        search_text=query,  # BM25 leg
        vector_queries=[
            VectorizedQuery(vector=await embed(query), k_nearest_neighbors=50, fields="embedding")
        ],  # vector leg
        query_type="semantic",  # reranker pass
        semantic_configuration_name="default",
        top=k,
        select=["id", "content", "source"],
    )
    return [
        {
            "id": r["id"],
            "content": r["content"],
            "source": r.get("source"),
            "rerank_score": r.get("@search.reranker_score") or 0.0,
        }
        async for r in results
    ]
