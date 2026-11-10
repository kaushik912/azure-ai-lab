#!/usr/bin/env bash
# Render k8s/deployment.yaml with values from `terraform output` and print to stdout.
#   scripts/render-k8s.sh | kubectl apply -f -
#   scripts/render-k8s.sh | less            # just look at it
# Optional: IMAGE_TAG=v2 scripts/render-k8s.sh | kubectl apply -f -
set -euo pipefail
cd "$(dirname "$0")/.."

tf() { terraform -chdir=infra output -raw "$1"; }

export CLIENT_ID="$(tf app_identity_client_id)"
export AOAI_ENDPOINT="$(tf aoai_endpoint)"
export SEARCH_ENDPOINT="$(tf search_endpoint)"
export ACR_LOGIN_SERVER="$(tf acr_login_server)"
export IMAGE_TAG="${IMAGE_TAG:-v1}"

# Only substitute our variables, so any other `$` in the manifest is left alone.
envsubst '${CLIENT_ID} ${AOAI_ENDPOINT} ${SEARCH_ENDPOINT} ${ACR_LOGIN_SERVER} ${IMAGE_TAG}' < k8s/deployment.yaml
