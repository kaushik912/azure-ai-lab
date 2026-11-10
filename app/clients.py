"""Azure clients. Keys if set in .env (lab), else keyless DefaultAzureCredential (prod)."""
from functools import lru_cache

from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents.aio import SearchClient
from openai import AsyncAzureOpenAI

from .config import get_settings


@lru_cache
def credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


@lru_cache
def openai_client() -> AsyncAzureOpenAI:
    s = get_settings()
    common = dict(azure_endpoint=s.azure_openai_endpoint, api_version=s.azure_openai_api_version)
    if s.azure_openai_api_key:
        return AsyncAzureOpenAI(api_key=s.azure_openai_api_key, **common)
    token_provider = get_bearer_token_provider(
        credential(), "https://cognitiveservices.azure.com/.default"
    )
    return AsyncAzureOpenAI(azure_ad_token_provider=token_provider, **common)


@lru_cache
def search_client() -> SearchClient:
    s = get_settings()
    cred = AzureKeyCredential(s.azure_search_api_key) if s.azure_search_api_key else credential()
    return SearchClient(
        endpoint=s.azure_search_endpoint, index_name=s.azure_search_index, credential=cred
    )
