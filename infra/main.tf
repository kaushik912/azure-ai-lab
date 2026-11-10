locals {
  rg_name = "azure-ai-lab-${var.suffix}-rg"
}

resource "azurerm_resource_group" "rg" {
  name     = local.rg_name
  location = var.location
}

# ---------- Azure OpenAI ----------
resource "azurerm_cognitive_account" "aoai" {
  name                  = "aoai${var.suffix}"
  resource_group_name   = azurerm_resource_group.rg.name
  location              = var.location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "aoai${var.suffix}" # required for Entra (keyless) auth
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = "chat" # deployment name the app calls
  cognitive_account_id = azurerm_cognitive_account.aoai.id
  model {
    format  = "OpenAI"
    name    = var.chat_model.name
    version = var.chat_model.version
  }
  sku {
    name     = var.chat_model.sku
    capacity = var.chat_model.capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_model.name
  cognitive_account_id = azurerm_cognitive_account.aoai.id
  model {
    format  = "OpenAI"
    name    = var.embedding_model.name
    version = var.embedding_model.version
  }
  sku {
    name     = var.embedding_model.sku
    capacity = var.embedding_model.capacity
  }
  depends_on = [azurerm_cognitive_deployment.chat] # avoid concurrent-deployment conflicts
}

# ---------- AI Search (free tier) ----------
resource "azurerm_search_service" "search" {
  name                         = "srch${var.suffix}"
  resource_group_name          = azurerm_resource_group.rg.name
  location                     = var.search_location
  sku                          = "free"
  local_authentication_enabled = true # keys + Entra (aadOrApiKey)
  authentication_failure_mode  = "http401WithBearerChallenge"
}

# ---------- Container Registry + AKS ----------
resource "azurerm_container_registry" "acr" {
  name                = "acrazureai${var.suffix}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "Basic"
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                      = "aks${var.suffix}"
  resource_group_name       = azurerm_resource_group.rg.name
  location                  = var.location
  dns_prefix                = "aks${var.suffix}"
  sku_tier                  = "Free"
  oidc_issuer_enabled       = true # token issuer for pods
  workload_identity_enabled = true # pod -> managed identity, no secrets

  default_node_pool {
    name       = "nodepool1"
    node_count = 1
    vm_size    = var.node_vm_size
  }

  identity {
    type = "SystemAssigned"
  }
}

# nodes may pull images from ACR (same as `az aks create --attach-acr`)
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = azurerm_container_registry.acr.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

# ---------- App identity (Workload Identity) ----------
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-ai-app${var.suffix}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
}

resource "azurerm_federated_identity_credential" "app" {
  name                = "fc-ai-app"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.app.id
  issuer              = azurerm_kubernetes_cluster.aks.oidc_issuer_url
  subject             = "system:serviceaccount:default:ai-app" # namespace:serviceaccount
  audience            = ["api://AzureADTokenExchange"]
}

# App identity: read-only on search, call models
resource "azurerm_role_assignment" "app_openai" {
  scope                = azurerm_cognitive_account.aoai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "app_search_read" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# You (for local runs + scripts/ingest.py)
resource "azurerm_role_assignment" "me_openai" {
  scope                = azurerm_cognitive_account.aoai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = data.azurerm_client_config.me.object_id
}

resource "azurerm_role_assignment" "me_search_service" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = data.azurerm_client_config.me.object_id
}

resource "azurerm_role_assignment" "me_search_data" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = data.azurerm_client_config.me.object_id
}
