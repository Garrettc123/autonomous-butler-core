# Unprecedented Automater — Vault Agent configuration (Docker Compose / non-K8s)
pid_file = "./pidfile"

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path                   = "/vault/config/role-id"
      secret_id_file_path                 = "/vault/config/secret-id"
      remove_secret_id_file_after_reading = false
    }
  }

  sink "file" {
    config = {
      path = "/vault/token/token"
    }
  }
}

template {
  source      = "/vault/config/templates/all-platforms.ctmpl"
  destination = "/vault/secrets/.env"
  perms       = "0600"
  # Re-render on any change; application can watch the file or re-source
}

# Optional: keep a separate raw JSON dump for debugging
template {
  source      = "/vault/config/templates/all-platforms.ctmpl"
  destination = "/vault/secrets/all.json"
  perms       = "0600"
}

vault {
  address = "${VAULT_ADDR}"
}
