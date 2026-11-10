# azure-ai-lab

Enterprise RAG + agentic gateway on Azure. Interview-prep showcase.

Stack: FastAPI (async, SSE) · LangGraph router · Azure OpenAI · Azure AI Search (hybrid + semantic rerank) · Workload Identity · AKS · App Insights.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # fill endpoints
az login               # DefaultAzureCredential picks this up
pytest
uvicorn app.main:app --reload
curl -N -X POST localhost:8000/ask/stream -H 'content-type: application/json' -d '{"question":"hi"}'
```

## Roadmap (maps to 30-day plan)
- [x] P1/P2: FastAPI + AOAI + hybrid search + LangGraph router
- [x] Ingestion script: chunk -> embed -> index (`scripts/ingest.py`)
- [ ] Retry loop in graph on low rerank score
- [x] P3: ACR push + AKS deploy with Workload Identity (`k8s/deployment.yaml`), tested via port-forward
- [ ] P4: GitHub Actions CI/CD, App Insights token-usage spans, eval set
- [ ] Terraform/Bicep for RG, AOAI, Search, AKS, ACR
