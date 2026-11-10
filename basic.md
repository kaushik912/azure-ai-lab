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

---

## Getting started with AI development in Azure: what you need
1. **Azure account + subscription** (free trial = $200 for 30 days). Trial limits we hit: some models have 0 quota, some VM sizes blocked, ACR Tasks (cloud builds) blocked. Upgrading to pay-as-you-go removes these; unused credit stays.
2. **Azure CLI** (`az`): the command line for everything below.
3. **Login that works**: for a personal (outlook.com) account, always use `az login --tenant <id>`; Security Defaults may block CLI login until MFA is set up or defaults are disabled.
4. **Resource providers registered**: Azure features are opt-in per subscription (`az provider register`).
5. **A region with capacity + quota** for the model you want.
6. **Python 3.11+** and a venv; SDKs: `openai`, `azure-identity`, `azure-search-documents`.
7. **Permissions (RBAC)** for your user, so keyless auth works.
8. Later, for deployment: **Docker** (or CI), **kubectl**, optionally **Terraform**.

---

## Every command, explained

### Login and account
- `az login --tenant <tenant-id> [--use-device-code]`: sign in. `--tenant` avoids the "Microsoft Services" tenant trap with personal accounts. Device code = sign in via a short code in any browser.
- `az account show -o table`: which subscription/tenant am I using? Quick check that login worked.
- `az account set --subscription <id>`: pick the default subscription when you have several.
- `export AZURE_CONFIG_DIR=$HOME/.azure-wsl`: WSL-only fix. `~/.azure` pointed at the Windows folder (read-only); this gives the CLI a Linux-side config dir.

### Foundations
- `az group create -n <rg> -l <region>`: make the resource group (the folder). Region = where its metadata lives.
- `az provider register --namespace Microsoft.X [--wait]`: enable a service type (CognitiveServices = OpenAI, Search, ContainerRegistry, ContainerService = AKS, ManagedIdentity...) for this subscription. One-time per subscription.
- `SUF=18430` / `$RANDOM`: random suffix; many Azure names are globally unique (they become URLs).

### Azure OpenAI
- `az cognitiveservices account create --kind OpenAI --sku S0 --custom-domain <name>`: creates the Azure OpenAI account. `--custom-domain` gives the `https://<name>.openai.azure.com` endpoint, required for Entra (keyless) auth.
- `az cognitiveservices account deployment create --deployment-name chat --model-name gpt-4.1-mini --model-version ... --sku-name GlobalStandard --sku-capacity 10`: deploys a model under a name. `capacity 10` = 10K tokens/min quota. `GlobalStandard` = Azure routes to any region (more capacity). Our code calls the deployment name (`chat`), not the model name.
- `az cognitiveservices account list-models ...`: which models/versions exist, and their lifecycle (GenerallyAvailable / Legacy / Deprecating). Deprecating models can't be newly deployed.
- `az cognitiveservices usage list -l <region>`: shows quota per model; limit 0 = you can't deploy it.

### AI Search
- `az search service create --sku free`: creates the search service (free = 50 MB, 3 indexes, enough for the lab). Free tier is capacity-limited per region (eastus2 was full; westus2 worked).
- `az search service update --auth-options aadOrApiKey`: allow Entra login in addition to keys. Without this, RBAC roles don't work.

### Permissions (RBAC)
- `az ad signed-in-user show --query id`: your user's object ID in Entra.
- `az role assignment create --assignee-object-id <id> --role "<role>" --scope <resource-id>`: "this identity can do this role on this resource". Roles used: `Cognitive Services OpenAI User` (call models), `Search Service Contributor` (create index), `Search Index Data Contributor` (read/write docs), `Search Index Data Reader` (read only; used for the app).
- Roles take ~2 min to take effect.

### Running the app (not Azure commands)
- `pip install -e '.[dev]'`: installs the app and dev tools from `pyproject.toml`.
- `python scripts/ingest.py`: creates the index (fields, vector config, semantic config), splits `data/*.md` into chunks, gets embeddings, uploads.
- `uvicorn app.main:app --reload`: starts the API on :8000. `/docs` = Swagger UI.
- `curl localhost:8000/ask -d '{"question":"..."}'`: ask a question.
- `pytest -q`: offline tests (no Azure needed).

### Cleanup
- `az group delete -n <rg> --yes --no-wait`: deletes the group and everything in it. `--no-wait` returns immediately.

---

## AKS (Kubernetes) section

**Why AKS here:** the JD asks for containers + AKS. For this tiny app Azure Container Apps would be simpler and cheaper, but AKS is the interview topic.

**Concepts**
- **Container image**: app + Python + dependencies packaged (`Dockerfile`). Multi-stage = build deps in one stage, copy only the result into a small final image; runs as non-root.
- **ACR (Azure Container Registry)**: private store for images (like ECR). AKS pulls from it.
- **AKS cluster**: Azure runs the Kubernetes control plane (free tier); you pay for the **node(s)** (VMs).
- **Node pool**: the VMs that run pods. We use 1 node, `Standard_D2as_v6` (2 vCPU / 8 GB). Trial subs only allow certain VM sizes per region.
- **Pod / Deployment / Service**: pod = running container; Deployment = "keep N pods running, roll updates"; Service = stable internal address in front of pods. `ClusterIP` = internal only (no public exposure).
- **Probes**: readiness (ready for traffic?) and liveness (restart if dead?) both hit `/healthz`.
- **OIDC issuer + Workload Identity**: AKS can issue signed tokens for pods. Azure trusts them via a **federated credential**, so a pod acts as a **Managed Identity** with no secrets. Flow: pod's ServiceAccount token -> Entra exchanges it -> access token for OpenAI/Search -> `DefaultAzureCredential` handles this automatically.

**Commands**
- `az acr create -n <name> --sku Basic`: create the registry (~$0.17/day).
- `az acr build ...`: cloud build; **blocked on free trial** (`TasksOperationsNotAllowed`), so we built locally instead.
- `docker build -t <acr>.azurecr.io/azure-ai-lab:v1 .`: build the image locally. Tag must include the registry host.
- `az acr login -n <name>`: lets Docker authenticate to the registry.
- `docker push <acr>.azurecr.io/azure-ai-lab:v1`: upload the image. (Docker can be turned off afterwards.)
- `az aks create --tier free --node-count 1 --node-vm-size Standard_D2as_v6 --attach-acr <acr> --enable-oidc-issuer --enable-workload-identity --generate-ssh-keys`: creates the cluster. `--attach-acr` lets nodes pull from ACR; `--enable-oidc-issuer` + `--enable-workload-identity` turn on passwordless pod identity; `--generate-ssh-keys` creates `~/.ssh/id_rsa` if missing (for node SSH, unused here).
- `az identity create -n id-ai-app...`: creates the **user-assigned managed identity** the pod will act as. Its `clientId` goes in the ServiceAccount annotation.
- `az role assignment create` (for the identity's principal ID): grants it OpenAI User + Search Index Data Reader (read-only: the app never writes the index).
- `az identity federated-credential create --issuer <aks-oidc-url> --subject system:serviceaccount:default:ai-app`: the trust link: "tokens from this cluster's ServiceAccount `ai-app` in namespace `default` may act as this identity". Subject must match exactly.
- `az aks install-cli`: installs `kubectl` (Kubernetes CLI) and `kubelogin` (Entra login plugin).
- `az aks get-credentials -g <rg> -n <aks>`: writes cluster connection info into a kubeconfig file.
- `kubectl get nodes`: is the node Ready?
- `scripts/render-k8s.sh | kubectl apply -f -`: fills `k8s/deployment.yaml` (a template) with values from `terraform output` using `envsubst`, then creates the ServiceAccount, Deployment, Service.
- `kubectl get pods` / `kubectl logs deploy/ai-app` / `kubectl describe pod`: status, app logs, why a pod fails (image pull errors, probe failures).
- `kubectl port-forward svc/ai-app 8080:80`: tunnel localhost:8080 to the private Service, to test without exposing it publicly.
- `kubectl rollout restart deploy/ai-app`: restart pods (e.g. after a new image or role change).

**AKS cost / safety notes**
- ~$2/day for the node; delete the resource group when done.
- No public LoadBalancer/Ingress on purpose: an open endpoint with no auth would let anyone spend your tokens.
- Production adds: Ingress + TLS, auth (Entra / APIM), HPA autoscaling, network policies, private cluster, Key Vault CSI for any remaining secrets, CI/CD (GitHub Actions) for build and deploy.
