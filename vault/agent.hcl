pid_file = "./pidfile"

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path   = "/vault/config/role-id"
      secret_id_file_path = "/vault/config/secret-id"
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
  source      = "/vault/config/templates/env.ctmpl"
  destination = "/vault/secrets/.env"
  perms       = "0600"
}

# Optional: continuous renewal
vault {
  address = "${VAULT_ADDR}"
}
