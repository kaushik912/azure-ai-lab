# Azure basics for this lab

## Big picture
You ask a question -> app finds relevant doc snippets -> AI model answers using only those snippets.
Azure rents us the pieces (AI model, search, a place to run the app). We pay per use, from the $200 credit.

## What is Azure OpenAI?
- OpenAI's models (GPT, embeddings) hosted inside *your* Azure account. Azure's equivalent of AWS Bedrock.
- Same models as openai.com, but: your data stays in your tenant, you get Azure auth/RBAC, private networking, quotas, enterprise compliance.
- You don't call "gpt-4.1-mini" directly. You **deploy** a model under a name you pick (ours: `chat`), then call that deployment.
- Billed per token (roughly: 1 token ~ 3/4 of a word). Input and output tokens priced separately.
- **Quota**: each model has a tokens-per-minute cap per subscription/region. Trial subs often get 0 for new models (we hit this with gpt-5-nano).
- Two kinds of model we use:
  - **Chat model** (`gpt-4.1-mini`): reads text, writes an answer.
  - **Embedding model** (`text-embedding-3-small`): turns text into a list of numbers (vector) so "similar meaning" = "close numbers". Powers semantic search.

## Resources we create

| Resource | What it is | AWS equivalent | Cost |
| --- | --- | --- | --- |
| **Subscription** | Billing account holding the $200 credit | AWS account | - |
| **Entra tenant** | Your identity directory (users, roles) | IAM / Identity Center | free |
| **Resource group** `azure-ai-lab-rg` | Folder for everything; delete it = delete all | CloudFormation stack (roughly) | free |
| **Azure OpenAI account** `aoai18430` | Container for model deployments + endpoint URL | Bedrock | pay per token |
| **Deployment** `chat` | gpt-4.1-mini, writes answers | Bedrock model access | per token |
| **Deployment** `text-embedding-3-small` | makes vectors | Titan embeddings | ~free at our scale |
| **AI Search** `srch18430` (free tier) | Stores doc chunks, hybrid keyword+vector search, reranker | OpenSearch / Kendra | $0 (free tier) |
| **Container Registry (ACR)** `acrazureai18430` | Stores our Docker image | ECR | ~$0.17/day |
| **AKS cluster** | Managed Kubernetes that runs the app | EKS | ~$1/day (1 small node) |
| **Managed Identity** | Passwordless identity for the app pod | IAM role (IRSA) | free |
| **Role assignments (RBAC)** | "Identity X may use resource Y" | IAM policies | free |

## Key ideas
- **RAG** (Retrieval-Augmented Generation): don't ask the model to remember your docs; fetch the relevant bits and paste them into the prompt. Cheaper than fine-tuning, always fresh, can cite sources.
- **Hybrid search**: keyword (BM25) + vector (meaning), merged, then a **semantic reranker** re-scores the top hits (score 0-4). We use that score to decide "answer" vs "I don't know".
- **Keyless auth**: no API keys in code. Locally: your `az login`. On AKS: **Workload Identity** links a pod to a Managed Identity. Code uses `DefaultAzureCredential`, which works in both.
- **RBAC roles used**: `Cognitive Services OpenAI User` (call models), `Search Index Data Contributor/Reader` (read/write docs), `Search Service Contributor` (create index).
- **Region matters**: model availability and capacity differ by region (our Search ended up in westus2).

## Cost control
- Models: pennies for this lab. Free Search tier. ACR + AKS are the main costs.
- When done: `az group delete -n azure-ai-lab-rg --yes --no-wait` removes everything and stops billing.
- Check spend: portal.azure.com -> Cost Management.
