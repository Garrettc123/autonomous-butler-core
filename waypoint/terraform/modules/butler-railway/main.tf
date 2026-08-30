terraform {
  required_providers {
    # Railway provider is community; many teams drive Railway via CLI in Actions.
    # This module documents the intended interface for Waypoint.
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}

variable "environment" {
  type = string
}

variable "service_name" {
  type    = string
  default = "autonomous-butler-core"
}

variable "image" {
  type    = string
  default = "ghcr.io/garrettc123/autonomous-butler-core:latest"
}

# Placeholder resource — actual Railway deploy is performed by the
# existing GitHub Action (deploy-railway job) triggered via Waypoint Action.
resource "null_resource" "railway_marker" {
  triggers = {
    environment = var.environment
    image       = var.image
    service     = var.service_name
  }
}

output "service_name" {
  value = var.service_name
}

output "note" {
  value = "Railway deploy is executed by GitHub Actions workflow_dispatch (ci-cd.yml deploy-railway job). Secrets come from Vault."
}
