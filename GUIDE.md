# GUIDE: zero to running RAG app on Azure (no Azure experience needed)

Expected total cost: **< $2** of your $200 credit if you do Step 9 (cleanup) when done.
Everything runs locally; Azure hosts only the AI services.

Mental model (AWS -> Azure): *Resource Group* = folder holding all resources (delete it = delete everything). *Azure OpenAI* = Bedrock. *AI Search* = OpenSearch. `az login` = `aws sso login`.

## Step 1. Install Azure CLI (WSL/Ubuntu)
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az version
```

## Step 2. Log in + check credit
```bash
az login --use-device-code      # open the URL, enter the code
az account show -o table        # note State=Enabled, subscription name
```
Free-trial note: Azure OpenAI may be blocked on trial subs ("quota"/"access" errors in Step 4). Fix: portal -> Subscriptions -> **Upgrade** to pay-as-you-go. Your remaining $200 credit still applies; you only pay beyond it.

## Step 3. Set variables + create resource group
```bash
export RG=azure-ai-lab-rg
export LOC=eastus2
export SUF=$RANDOM            # makes names globally unique; keep this shell open (or note the number)
echo $SUF
az group create -n $RG -l $LOC
```

## Step 4. Azure OpenAI + 2 model deployments
```bash
az provider register --namespace Microsoft.CognitiveServices   # one-time, may take a minute

az cognitiveservices account create -n aoai$SUF -g $RG -l $LOC \
  --kind OpenAI --sku S0 --custom-domain aoai$SUF

# chat model (cheap)
az cognitiveservices account deployment create -g $RG -n aoai$SUF \
  --deployment-name gpt-4o-mini --model-name gpt-4o-mini --model-version "2024-07-18" \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10

# embedding model
az cognitiveservices account deployment create -g $RG -n aoai$SUF \
  --deployment-name text-embedding-3-small --model-name text-embedding-3-small --model-version "1" \
  --model-format OpenAI --sku-name Standard --sku-capacity 10
```
If a model/version/region errors: `az cognitiveservices model list -l $LOC -o table | grep -E "gpt-4o-mini|embedding-3-small"` and adjust.

## Step 5. AI Search (free tier = $0)
```bash
az provider register --namespace Microsoft.Search
az search service create -n srch$SUF -g $RG -l $LOC --sku free
# enable Entra (keyless) auth in addition to keys:
az search service update -n srch$SUF -g $RG --auth-options aadOrApiKey \
  --aad-auth-failure-mode http401WithBearerChallenge
```
If free tier says capacity unavailable: try another `LOC` (e.g. `westus2`) or use `--sku basic` (~$0.10/hr; delete in Step 9 same day).

## Step 6. Give *yourself* permission (keyless auth = the "Managed Identity" idea, using your user)
```bash
ME=$(az ad signed-in-user show --query id -o tsv)
SUB=$(az account show --query id -o tsv)
BASE=/subscriptions/$SUB/resourceGroups/$RG/providers

az role assignment create --assignee $ME --role "Cognitive Services OpenAI User" \
  --scope $BASE/Microsoft.CognitiveServices/accounts/aoai$SUF
for R in "Search Service Contributor" "Search Index Data Contributor"; do
  az role assignment create --assignee $ME --role "$R" \
    --scope $BASE/Microsoft.Search/searchServices/srch$SUF
done
```
Wait ~2 min for roles to propagate (403 errors = still propagating).

## Step 7. Configure + install the app
```bash
cd ~/github_projs/azure-ai-lab
cat > .env <<EOF
AZURE_OPENAI_ENDPOINT=https://aoai$SUF.openai.azure.com
AZURE_SEARCH_ENDPOINT=https://srch$SUF.search.windows.net
EOF

python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q                      # offline tests, should pass
python scripts/ingest.py       # creates index + loads data/handbook.md
```
Expect: `index 'docs' ready` then `uploaded N chunks`.

## Step 8. Run + try it
```bash
uvicorn app.main:app --reload
```
New terminal:
```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"How many PTO days roll over?"}' | python3 -m json.tool

curl -N localhost:8000/ask/stream -H 'content-type: application/json' \
  -d '{"question":"What is the on-call stipend?"}'

# should DECLINE with no LLM call (tokens saved):
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"What is the capital of France?"}'
```
Also open http://localhost:8000/docs (auto Swagger UI).

## Step 9. CLEAN UP (do this when finished)
```bash
az group delete -n $RG --yes --no-wait     # deletes everything, stops all billing
```
Check spend anytime: portal.azure.com -> Cost Management.

## Troubleshooting
| Error | Fix |
| --- | --- |
| 401/403 from OpenAI or Search | roles not propagated yet (wait) or wrong `az login` account |
| `DeploymentNotFound` | deployment name != `.env`/defaults (`gpt-4o-mini`, `text-embedding-3-small`) |
| Always "I don't know" | lower `MIN_RERANK_SCORE` (env) e.g. `0.5`; check ingest uploaded chunks |
| Semantic ranker error on free tier | free tier supports it (1000 q/mo); ensure `semantic_configuration_name="default"` matches index |

## Later (optional, costs more): AKS / Container Apps
Needs Docker (build image) and ~$70+/mo for AKS nodes. Only do for a 1-2 hour demo then delete the RG. See `k8s/deployment.yaml`.
