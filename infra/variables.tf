variable "suffix" {
  description = "Short unique suffix for globally-unique names (OpenAI, Search, ACR)."
  type        = string
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "search_location" {
  description = "AI Search free tier is capacity-limited; eastus2 was full."
  type        = string
  default     = "westus2"
}

variable "node_vm_size" {
  description = "Trial subscriptions only allow certain sizes (v6/v7 in eastus2)."
  type        = string
  default     = "Standard_D2as_v6"
}

variable "chat_model" {
  type = object({ name = string, version = string, sku = string, capacity = number })
  default = {
    name     = "gpt-4.1-mini"
    version  = "2025-04-14"
    sku      = "GlobalStandard"
    capacity = 10
  }
}

variable "embedding_model" {
  type = object({ name = string, version = string, sku = string, capacity = number })
  default = {
    name     = "text-embedding-3-small"
    version  = "1"
    sku      = "Standard"
    capacity = 10
  }
}
