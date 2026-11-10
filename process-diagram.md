# How this demo gets built, tested and deployed

Solid boxes = what we actually did. Dashed boxes = what a production team adds (CI/CD, evals, monitoring).

## 1. Build -> test -> deploy

```mermaid
flowchart TD
    subgraph DEV["1. Develop (local, WSL)"]
        A["Write code<br/>FastAPI + LangGraph"] --> B["pytest (offline unit tests)"]
        B --> C["Run locally: uvicorn<br/>uses az login (keyless)"]
    end

    subgraph INFRA["2. Provision infrastructure (Terraform)"]
        T1["terraform plan"] --> T2["terraform apply"]
        T2 --> R["Resource group, Azure OpenAI + 2 models,<br/>AI Search, ACR, AKS,<br/>Managed Identity + RBAC"]
    end

    subgraph DATA["3. Load data"]
        D1["data/*.md"] --> D2["scripts/ingest.py<br/>chunk -> embed -> upsert"]
        D2 --> D3[("AI Search index 'docs'")]
    end

    subgraph SHIP["4. Package and ship"]
        S1["docker build"] --> S2["docker push"]
        S2 --> ACR[("Azure Container Registry")]
        S3["scripts/render-k8s.sh<br/>(fills manifest from terraform output)"] --> S4["kubectl apply"]
        ACR -. "node pulls image (AcrPull)" .-> POD
        S4 --> POD["Pod on AKS<br/>Workload Identity, no keys"]
    end

    subgraph VERIFY["5. Verify"]
        V1["kubectl get pods / logs"] --> V2["kubectl port-forward"]
        V2 --> V3["curl /ask, /ask/stream<br/>grounded answer + decline case"]
    end

    C --> T1
    R --> D2
    R --> S1
    D3 --> V3
    POD --> V1

    subgraph PROD["Production extras (not built here)"]
        P1["GitHub Actions CI/CD<br/>test, build, push, deploy"]
        P2["RAG eval set as a CI gate"]
        P3["App Insights tracing,<br/>token + latency alerts"]
        P4["Ingress + TLS + auth, autoscaling"]
    end
    V3 -.-> P1
    P1 -.-> P2
    P1 -.-> P3
    P1 -.-> P4

    V3 --> CLEAN["terraform destroy / az group delete<br/>then purge soft-deleted OpenAI account"]

    classDef later stroke-dasharray: 5 5,fill:#f5f5f5,color:#333
    class P1,P2,P3,P4 later
```

## 2. What happens on one request (runtime)

```mermaid
sequenceDiagram
    autonumber
    participant U as Client (curl)
    participant API as FastAPI pod (AKS)
    participant ID as Entra ID
    participant S as Azure AI Search
    participant O as Azure OpenAI

    U->>API: POST /ask {question}
    Note over API,ID: Workload Identity: pod token -> access token (cached, no secrets)
    API->>ID: exchange federated token
    ID-->>API: access token
    API->>O: embed(question) [text-embedding-3-small]
    O-->>API: vector
    API->>S: hybrid query (BM25 + vector) + semantic rerank
    S-->>API: top chunks with rerank scores (0-4)
    alt best score >= threshold
        API->>O: chat(context + question) [gpt-4.1-mini]
        O-->>API: grounded answer
        API-->>U: answer + sources
    else not grounded
        API-->>U: "I don't know" (no LLM call, no tokens spent)
    end
```

## 3. Who can do what (identity map)

```mermaid
flowchart LR
    ME["You (az login)"] -->|"OpenAI User<br/>Search Service + Index Data Contributor"| AZ[("OpenAI + Search")]
    POD["Pod identity<br/>(federated credential)"] -->|"OpenAI User<br/>Search Index Data Reader"| AZ
    NODE["AKS kubelet identity"] -->|AcrPull| ACR[("ACR")]
```

## Cheat sheet: where each step lives
| Step | File / command |
| --- | --- |
| Infra | `infra/` -> `terraform apply` |
| Data | `scripts/ingest.py` (re-run when documents change) |
| Image | `Dockerfile` -> `docker build` / `push` |
| Deploy | `k8s/deployment.yaml` (template) + `scripts/render-k8s.sh` |
| Test | `pytest`, then `kubectl port-forward` + `curl` |
| Teardown | `terraform destroy`, purge soft-deleted OpenAI |
