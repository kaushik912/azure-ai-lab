terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Auth: uses your `az login` session. Set ARM_SUBSCRIPTION_ID (see README in infra/).
provider "azurerm" {
  features {}
  resource_provider_registrations = "none" # we registered providers via az already
}

data "azurerm_client_config" "me" {}
