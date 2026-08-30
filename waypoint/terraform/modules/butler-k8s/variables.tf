variable "environment" {
  type        = string
  description = "Environment name"
}

variable "image" {
  type    = string
  default = "ghcr.io/garrettc123/autonomous-butler-core:latest"
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
