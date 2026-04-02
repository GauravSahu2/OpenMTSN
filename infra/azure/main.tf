# ══════════════════════════════════════════════════════════
# OpenMTSN — Azure Free Tier Deployment
# ══════════════════════════════════════════════════════════
# Provisions: App Service (F1 Free) + IoT Hub (Free)
# Cost: $0 (within Azure Free Tier limits)
# ══════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {}
}

# ── Variables ─────────────────────────────────────────────

variable "location" {
  description = "Azure region"
  type        = string
  default     = "East US"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "openmtsn"
}

variable "ghcr_image_api" {
  description = "GHCR image for the API"
  type        = string
  default     = "ghcr.io/openmtsn/openmtsn/api:latest"
}

variable "ghcr_image_dashboard" {
  description = "GHCR image for the Dashboard"
  type        = string
  default     = "ghcr.io/openmtsn/openmtsn/dashboard:latest"
}

# ── Resource Group ────────────────────────────────────────

resource "azurerm_resource_group" "mtsn" {
  name     = "${var.project_name}-rg"
  location = var.location

  tags = {
    Project     = "OpenMTSN"
    Environment = "production"
  }
}

# ── App Service Plan (F1 Free Tier) ──────────────────────

resource "azurerm_service_plan" "mtsn" {
  name                = "${var.project_name}-plan"
  resource_group_name = azurerm_resource_group.mtsn.name
  location            = azurerm_resource_group.mtsn.location
  os_type             = "Linux"
  sku_name            = "F1"

  tags = {
    Project = "OpenMTSN"
  }
}

# ── App Service: API (Control Plane) ─────────────────────

resource "azurerm_linux_web_app" "api" {
  name                = "${var.project_name}-api"
  resource_group_name = azurerm_resource_group.mtsn.name
  location            = azurerm_resource_group.mtsn.location
  service_plan_id     = azurerm_service_plan.mtsn.id

  site_config {
    always_on = false   # F1 tier does not support always_on

    application_stack {
      docker_image_name   = var.ghcr_image_api
      docker_registry_url = "https://ghcr.io"
    }
  }

  app_settings = {
    "MTSN_REDIS_URL"                  = "redis://${azurerm_redis_cache.mtsn.hostname}:${azurerm_redis_cache.mtsn.ssl_port}"
    "MTSN_LOG_LEVEL"                  = "INFO"
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
    "DOCKER_ENABLE_CI"                = "true"
  }

  tags = {
    Project   = "OpenMTSN"
    Component = "api"
  }
}

# ── App Service: Dashboard ───────────────────────────────

resource "azurerm_linux_web_app" "dashboard" {
  name                = "${var.project_name}-dashboard"
  resource_group_name = azurerm_resource_group.mtsn.name
  location            = azurerm_resource_group.mtsn.location
  service_plan_id     = azurerm_service_plan.mtsn.id

  site_config {
    always_on = false

    application_stack {
      docker_image_name   = var.ghcr_image_dashboard
      docker_registry_url = "https://ghcr.io"
    }
  }

  app_settings = {
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
  }

  tags = {
    Project   = "OpenMTSN"
    Component = "dashboard"
  }
}

# ── Azure Cache for Redis (Basic C0 — smallest tier) ─────

resource "azurerm_redis_cache" "mtsn" {
  name                = "${var.project_name}-redis"
  location            = azurerm_resource_group.mtsn.location
  resource_group_name = azurerm_resource_group.mtsn.name
  capacity            = 0
  family              = "C"
  sku_name            = "Basic"
  minimum_tls_version = "1.2"

  redis_configuration {
    maxmemory_policy = "allkeys-lru"
  }

  tags = {
    Project = "OpenMTSN"
  }
}

# ── Azure IoT Hub (Free Tier) ────────────────────────────

resource "azurerm_iothub" "mtsn" {
  name                = "${var.project_name}-iothub"
  resource_group_name = azurerm_resource_group.mtsn.name
  location            = azurerm_resource_group.mtsn.location

  sku {
    name     = "F1"
    capacity = 1
  }

  cloud_to_device {
    max_delivery_count = 10
    default_ttl        = "PT1H"
  }

  tags = {
    Project   = "OpenMTSN"
    Component = "iot"
  }
}

# ── IoT Hub Route: Telemetry → Built-in Endpoint ─────────

resource "azurerm_iothub_route" "telemetry" {
  resource_group_name = azurerm_resource_group.mtsn.name
  iothub_name         = azurerm_iothub.mtsn.name
  name                = "telemetry-route"
  source              = "DeviceMessages"
  condition           = "true"
  endpoint_names      = ["events"]
  enabled             = true
}

# ── Outputs ──────────────────────────────────────────────

output "api_url" {
  description = "URL for the OpenMTSN API"
  value       = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "dashboard_url" {
  description = "URL for the Command Center dashboard"
  value       = "https://${azurerm_linux_web_app.dashboard.default_hostname}"
}

output "iothub_hostname" {
  description = "Azure IoT Hub hostname for edge agent connections"
  value       = azurerm_iothub.mtsn.hostname
}

output "redis_hostname" {
  description = "Azure Redis Cache hostname"
  value       = azurerm_redis_cache.mtsn.hostname
}
