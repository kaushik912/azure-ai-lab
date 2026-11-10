# What lives in the AKS node resource group (`MC_...`) and why

**Pattern:** you declare something in Kubernetes (`Service type=LoadBalancer`, a PVC, a node pool) -> AKS creates the matching Azure resource inside a managed resource group named `MC_<rg>_<cluster>_<region>`. You never create those by hand.

```
 YOUR resource group  azure-ai-lab-<sfx>-rg        AZURE-MANAGED  MC_azure-ai-lab-<sfx>-rg_aks<sfx>_eastus2
 +--------------------------------------+          +--------------------------------------------------+
 | OpenAI, Search, ACR, identity        |          |  Public IP --> Load Balancer --> VM scale set    |
 | AKS cluster object  ----------------------------->        (rules)               (node VMs, pods)   |
 +--------------------------------------+  creates |  VNet + subnet  (nodes live here)                |
                                                    |  NSG (firewall)   Route table   Managed disks    |
                                                    +--------------------------------------------------+
```

## The pieces (1 line each, AWS equivalent)

| Azure resource | What it is | AWS |
| --- | --- | --- |
| VM scale set (VMSS) | group of identical node VMs; scaling = change count | Auto Scaling Group |
| Virtual network + subnet | private network the nodes/pods get IPs from | VPC + subnet |
| Network security group (NSG) | allow/deny rules on subnet/NIC | Security group |
| Route table | where traffic goes next (internet, other subnets) | Route table |
| Load balancer | spreads inbound traffic across nodes; created when you expose a Service | ELB/NLB |
| Public IP | internet-facing address used by the load balancer (also outbound NAT) | Elastic IP |
| Managed disk | block storage; created for each persistent volume (PVC) | EBS |

## Step 1. Find and list it
```bash
export AZURE_CONFIG_DIR=$HOME/.azure-wsl
cd ~/github_projs/azure-ai-lab/infra
RG=$(terraform output -raw resource_group)
AKS=$(terraform output -raw aks_name)
NODE_RG=$(az aks show -g $RG -n $AKS --query nodeResourceGroup -o tsv)
echo $NODE_RG                                   # MC_azure-ai-lab-..._eastus2

az resource list -g $NODE_RG -o table           # everything AKS created for you
```
Look for types: `virtualMachineScaleSets`, `virtualNetworks`, `networkSecurityGroups`, `routeTables`, `loadBalancers` (kubernetes), `publicIPAddresses`.

## Step 2. See each piece
```bash
az vmss list -g $NODE_RG -o table                              # node VMs group
az vmss list-instances -g $NODE_RG -n $(az vmss list -g $NODE_RG --query "[0].name" -o tsv) -o table
az network vnet list -g $NODE_RG -o table                      # the network
az network nsg list -g $NODE_RG -o table                       # firewall
az network route-table list -g $NODE_RG -o table
az network lb list -g $NODE_RG -o table                        # outbound LB (inbound added in Step 3)
az network public-ip list -g $NODE_RG -o table                 # outbound IP for now
```
Connect to the cluster first if needed: `az aks get-credentials -g $RG -n $AKS`.

## Step 3. Watch the pattern: Service -> load balancer + public IP
Use a throwaway nginx (not our app, so nobody can burn your tokens). This makes a **public** endpoint; delete it right after.
```bash
kubectl create deployment hello --image=nginx
kubectl expose deployment hello --type=LoadBalancer --port=80
kubectl get svc hello -w            # wait until EXTERNAL-IP shows (1-3 min), then Ctrl+C

curl -s http://<EXTERNAL-IP> | head -4        # "Welcome to nginx!"

az network public-ip list -g $NODE_RG -o table    # NEW public IP = the EXTERNAL-IP
az network lb rule list -g $NODE_RG --lb-name kubernetes -o table   # NEW rule: port 80 -> nodes
az network nsg rule list -g $NODE_RG --nsg-name $(az network nsg list -g $NODE_RG --query "[0].name" -o tsv) -o table  # NEW allow rule for port 80
```
Cleanup (removes the public IP + LB rule again):
```bash
kubectl delete svc hello
kubectl delete deployment hello
```

## Step 4. Watch the pattern: PVC -> managed disk
```bash
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: demo-pvc }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 1Gi } }
---
apiVersion: v1
kind: Pod
metadata: { name: demo-pod }
spec:
  containers:
    - { name: c, image: nginx, volumeMounts: [{ name: d, mountPath: /data }] }
  volumes:
    - { name: d, persistentVolumeClaim: { claimName: demo-pvc } }
EOF
kubectl get pvc demo-pvc                        # Bound
az disk list -g $NODE_RG -o table               # NEW 1 GiB managed disk
```
Cleanup (disk is deleted with the PVC by default):
```bash
kubectl delete pod demo-pod && kubectl delete pvc demo-pvc
```

## Pattern table: what you do -> what appears in `MC_...`
| You do | Azure creates |
| --- | --- |
| `az aks create` / Terraform cluster | VMSS, VNet, NSG, route table, outbound LB + public IP |
| add/scale a node pool | VMSS instances (or new VMSS) |
| `Service type=LoadBalancer` | public IP + LB frontend/rule + NSG allow rule |
| PVC (default storage class) | managed disk |
| Ingress controller (nginx/AGIC) | its own LB/IP or Application Gateway |

## Rules
- Don't edit or delete things inside `MC_...`; AKS reconciles them and you can break the cluster.
- Deleting the cluster or your main RG removes it automatically.
- Not in Terraform state (Azure owns it); `terraform destroy` still cleans up.
- Its VM is the main cost (~$2/day here); public IPs and disks add small per-day charges.
- Exposing a Service publicly = anyone can hit it. Our app stays ClusterIP on purpose.
