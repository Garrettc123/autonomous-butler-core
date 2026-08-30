terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.25"
    }
  }
}

variable "environment" {
  type        = string
  description = "Environment name (production, staging, preview)"
}

variable "image" {
  type        = string
  description = "Full container image including tag"
  default     = "ghcr.io/garrettc123/autonomous-butler-core:latest"
}

variable "replicas" {
  type    = number
  default = 2
}

variable "namespace" {
  type    = string
  default = "autonomous-butler"
}

variable "vault_role" {
  type    = string
  default = "garcar-runtime"
}

resource "kubernetes_namespace" "butler" {
  metadata {
    name = var.namespace
    labels = {
      app         = "autonomous-butler"
      environment = var.environment
      managed-by  = "hcp-waypoint"
    }
  }
}

resource "kubernetes_deployment" "butler_core" {
  metadata {
    name      = "butler-core"
    namespace = kubernetes_namespace.butler.metadata[0].name
    labels = {
      app         = "butler-core"
      environment = var.environment
    }
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        app = "butler-core"
      }
    }

    template {
      metadata {
        labels = {
          app         = "butler-core"
          environment = var.environment
        }
        annotations = {
          # Vault Agent Injector — full-scale secrets injection
          "vault.hashicorp.com/agent-inject"            = "true"
          "vault.hashicorp.com/role"                    = var.vault_role
          "vault.hashicorp.com/agent-pre-populate"      = "true"
          "vault.hashicorp.com/agent-inject-status"     = "update"
          "vault.hashicorp.com/agent-inject-secret-env" = "secret/data/garcar/ai"
          "vault.hashicorp.com/agent-inject-file-env"   = ".env"
          # Additional platforms can be listed or use a consolidated path
          "vault.hashicorp.com/agent-inject-secret-stripe" = "secret/data/garcar/stripe"
          "vault.hashicorp.com/agent-inject-secret-slack"  = "secret/data/garcar/slack"
          "vault.hashicorp.com/agent-inject-secret-github" = "secret/data/garcar/github"
        }
      }

      spec {
        service_account_name = "butler-core"

        container {
          name  = "butler-core"
          image = var.image

          port {
            container_port = 8000
            name           = "http"
          }

          env {
            name  = "ENVIRONMENT"
            value = var.environment
          }

          env {
            name  = "DOTENV_PATH"
            value = "/vault/secrets/.env"
          }

          resources {
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1000m"
              memory = "1Gi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 15
            period_seconds        = 20
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "butler_core" {
  metadata {
    name      = "butler-core"
    namespace = kubernetes_namespace.butler.metadata[0].name
  }

  spec {
    selector = {
      app = "butler-core"
    }

    port {
      port        = 80
      target_port = 8000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "butler_core" {
  metadata {
    name      = "butler-core"
    namespace = kubernetes_namespace.butler.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.butler_core.metadata[0].name
    }

    min_replicas = var.replicas
    max_replicas = var.replicas * 4

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }
  }
}

output "namespace" {
  value = kubernetes_namespace.butler.metadata[0].name
}

output "service_name" {
  value = kubernetes_service.butler_core.metadata[0].name
}
