"""Create the AI Search index and load ./data/*.md (chunk -> embed -> upload).

Usage: python scripts/ingest.py   (needs .env + `az login` + RBAC roles, see GUIDE.md)
Cost: a few cents at most with text-embedding-3-small.
"""
import pathlib
import sys

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI
from azure.identity import get_bearer_token_provider

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

DIMS = 1536  # text-embedding-3-small


def chunk(text: str, size: int = 450, overlap: int = 60) -> list[str]:
    """Paragraph-aware chunking: pack paragraphs up to ~size chars, carry overlap."""
    out, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > size:
            out.append(cur.strip())
            cur = cur[-overlap:] + "\n\n" + para
        else:
            cur += "\n\n" + para
    if cur.strip():
        out.append(cur.strip())
    return out


def main() -> None:
    s = get_settings()
    entra = DefaultAzureCredential() if not (s.azure_search_api_key and s.azure_openai_api_key) else None
    cred = AzureKeyCredential(s.azure_search_api_key) if s.azure_search_api_key else entra

    index = SearchIndex(
        name=s.azure_search_index,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=DIMS,
                vector_search_profile_name="vp",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="vp", algorithm_configuration_name="hnsw")],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="default",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")]
                    ),
                )
            ]
        ),
    )
    SearchIndexClient(s.azure_search_endpoint, cred).create_or_update_index(index)
    print(f"index '{s.azure_search_index}' ready")

    if s.azure_openai_api_key:
        aoai = AzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_version=s.azure_openai_api_version,
            api_key=s.azure_openai_api_key,
        )
    else:
        aoai = AzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_version=s.azure_openai_api_version,
            azure_ad_token_provider=get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            ),
        )

    docs = []
    for path in sorted((pathlib.Path(__file__).parent.parent / "data").glob("*.md")):
        for i, c in enumerate(chunk(path.read_text())):
            docs.append({"id": f"{path.stem}-{i}", "content": c, "source": path.name})
    if not docs:
        sys.exit("no docs in ./data")

    embs = aoai.embeddings.create(
        model=s.azure_openai_embedding_deployment, input=[d["content"] for d in docs]
    )
    for d, e in zip(docs, embs.data):
        d["embedding"] = e.embedding

    SearchClient(s.azure_search_endpoint, s.azure_search_index, cred).upload_documents(docs)
    print(f"uploaded {len(docs)} chunks")


if __name__ == "__main__":
    main()
