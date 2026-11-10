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

### Security note: Entra "Security defaults" were disabled for this demo
`az login` failed with `AADSTS530035` ("blocked by security defaults") because the personal account couldn't register MFA. To get past it we set **Microsoft Entra ID -> Properties -> Manage security defaults -> Disabled**.
- That turns off the tenant-wide MFA requirement, which is acceptable only for a throwaway lab tenant.
- **Re-enable it after the demo:** portal -> Microsoft Entra ID -> Properties -> Manage security defaults -> **Enabled** -> Save. (Or replace it with Conditional Access policies requiring MFA.)
- In a real environment never leave it off: use MFA / Conditional Access, plus least-privilege RBAC.

Login still failing (MFA, wrong tenant, browser opens a folder)? See **Appendix: login and MFA troubleshooting** at the end.

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
Also: **re-enable Entra Security defaults** (see the security note under Step 2).
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

## Optional: deploy and test on AKS (~$2/day for the node; delete the RG after)
Resources and why: see `basic.md` (AKS section). Terraform for the whole stack: `infra/`.
Free-trial gotchas: `az acr build` is blocked (build with local Docker instead); allowed VM sizes are limited per region (we used `Standard_D2as_v6`).

### A. Build and push the image (needs Docker running; stop it afterwards)
```bash
export AZURE_CONFIG_DIR=$HOME/.azure-wsl SUF=18430
az acr login -n acrazureai$SUF
docker build -t acrazureai$SUF.azurecr.io/azure-ai-lab:v1 .
docker push acrazureai$SUF.azurecr.io/azure-ai-lab:v1
```

### B. Cluster + identity (one-time)
```bash
export RG=azure-ai-lab-rg LOC=eastus2 SUF=18430
az acr create -n acrazureai$SUF -g $RG -l $LOC --sku Basic
az aks create -g $RG -n aks$SUF -l $LOC --tier free --node-count 1 --node-vm-size Standard_D2as_v6 \
  --attach-acr acrazureai$SUF --enable-oidc-issuer --enable-workload-identity --generate-ssh-keys

# identity the pod acts as + permissions (client ID goes in k8s/deployment.yaml)
az identity create -n id-ai-app$SUF -g $RG -l $LOC
PID=$(az identity show -n id-ai-app$SUF -g $RG --query principalId -o tsv)
SUB=$(az account show --query id -o tsv); BASE=/subscriptions/$SUB/resourceGroups/$RG/providers
az role assignment create --assignee-object-id $PID --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" --scope $BASE/Microsoft.CognitiveServices/accounts/aoai$SUF
az role assignment create --assignee-object-id $PID --assignee-principal-type ServicePrincipal \
  --role "Search Index Data Reader" --scope $BASE/Microsoft.Search/searchServices/srch$SUF

# trust link: this cluster's ServiceAccount default/ai-app may act as the identity
ISS=$(az aks show -g $RG -n aks$SUF --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create -n fc-ai-app -g $RG --identity-name id-ai-app$SUF \
  --issuer "$ISS" --subject system:serviceaccount:default:ai-app --audiences api://AzureADTokenExchange
```

### C. kubectl setup (WSL: /usr/local/bin may be read-only, so install to ~/.local/bin)
```bash
mkdir -p ~/.local/bin
export AZURE_CONFIG_DIR=$HOME/.azure-wsl PATH=$HOME/.local/bin:$PATH
az aks install-cli --install-location ~/.local/bin/kubectl --kubelogin-install-location ~/.local/bin/kubelogin
az aks get-credentials -g azure-ai-lab-rg -n aks18430      # writes ~/.kube/config
```
`kubelogin` = Azure/Entra auth plugin for kubectl (AKS equivalent of `aws eks get-token`).

### D. Deploy
```bash
kubectl apply -f k8s/deployment.yaml     # ServiceAccount + Deployment + Service (ClusterIP, private)
kubectl rollout status deploy/ai-app
```

### E. Test
```bash
kubectl get nodes                        # Ready
kubectl get pods                         # ai-app-... 1/1 Running
kubectl logs deploy/ai-app --tail=20     # /healthz 200 lines
kubectl port-forward svc/ai-app 8080:80  # tunnel; leave running (Service is not public)
```
Second terminal:
```bash
curl -s localhost:8080/healthz
curl -s localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"How many PTO days roll over?"}' | python3 -m json.tool
curl -s localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"What is the capital of France?"}'      # declines, no LLM call
curl -N localhost:8080/ask/stream -H 'content-type: application/json' \
  -d '{"question":"What is the on-call stipend?"}'        # streams tokens
```
Or open http://localhost:8080/docs.

### F. Things to try / know for interviews
| Try | Shows |
| --- | --- |
| `kubectl exec deploy/ai-app -- env \| grep AZURE_` | Workload Identity webhook injects `AZURE_CLIENT_ID`, `AZURE_FEDERATED_TOKEN_FILE`; no API key anywhere |
| `kubectl delete pod -l app=ai-app` then `kubectl get pods -w` | self-healing |
| `kubectl scale deploy/ai-app --replicas=2` | scaling |
| `kubectl describe pod -l app=ai-app` | events: image pull / probe failures |
| `kubectl rollout restart deploy/ai-app` | restart after new image or role change |

### G. Troubleshooting AKS
| Symptom | Cause / fix |
| --- | --- |
| `ImagePullBackOff` | image not pushed, wrong tag, or ACR not attached (`az aks update --attach-acr`) |
| App 401/403 in logs | role not propagated (wait ~2 min) or federated credential subject != `system:serviceaccount:default:ai-app` |
| Pod `CrashLoopBackOff` | `kubectl logs deploy/ai-app --previous`; usually missing env var |
| `VM size ... not allowed` | pick another size from the error's list |
| `TasksOperationsNotAllowed` | free trial blocks ACR Tasks; use local `docker build` + `push` |
| `Read-only file system` for kubectl install | use `--install-location ~/.local/bin/kubectl` |

### H. Delete everything
```bash
az group delete -n azure-ai-lab-rg --yes --no-wait
```

---

## Appendix: login and MFA troubleshooting

### Why registering MFA in Authenticator did not fix `AADSTS530035` (likely cause; not fully verified)
`outlook.com` is a *personal Microsoft account*, not a native user of the tenant. MFA set up on the personal account is evaluated by Microsoft-account sign-in, not by the tenant's Security defaults. That's also why `aka.ms/mfasetup` routed to the "Microsoft Services" tenant. Entra's sign-in analysis for the failure says: error 530035, blocked by a (Conditional Access-style) policy in the resource tenant. It's a policy block, not a code or command bug.

### Options
1. *Demo (what we did):* keep Security defaults **Disabled** during the lab, re-enable afterwards.
2. *Proper fix:* create a native tenant user (portal -> Microsoft Entra ID -> Users -> New user, e.g. `labadmin@<tenant>.onmicrosoft.com`), give it **Owner** on the subscription (Subscriptions -> Access control (IAM)), register Authenticator for it at first sign-in, and use it for `az login`. Security defaults can then stay on.
3. *Avoid local login:* use Cloud Shell (already authenticated; `terraform` is preinstalled).

### Other login errors we hit
| Error | Cause / fix |
| --- | --- |
| "Selected user account does not exist in tenant 'Microsoft Services'" | personal account defaulted to the wrong tenant; always `az login --tenant <tenant-id>` |
| `AADSTS900144 ... 'client_id'` | sign-in URL was truncated when copied; use `--use-device-code` or let WSL open the browser |
| "No subscriptions found" | free trial not started yet; sign up at azure.microsoft.com/free |
| `[Errno 30] Read-only file system: ~/.azure/azureProfile.json` | `~/.azure` is a symlink to the Windows folder; `export AZURE_CONFIG_DIR=$HOME/.azure-wsl` |
| `az login` opens a folder (e.g. OneDrive) instead of a browser | use `--use-device-code`, or `export BROWSER=wslview` (`sudo apt install wslu`), or paste the full URL into your browser |
| "Please run 'az login'" after a while | session expired, or `az logout` was run in another shell sharing the same `AZURE_CONFIG_DIR` |
