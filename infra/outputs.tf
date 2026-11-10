output "resource_group" { value = azurerm_resource_group.rg.name }
output "aoai_endpoint" { value = azurerm_cognitive_account.aoai.endpoint }
output "search_endpoint" { value = "https://${azurerm_search_service.search.name}.search.windows.net" }
output "acr_login_server" { value = azurerm_container_registry.acr.login_server }
output "aks_name" { value = azurerm_kubernetes_cluster.aks.name }
output "app_identity_client_id" { value = azurerm_user_assigned_identity.app.client_id }
