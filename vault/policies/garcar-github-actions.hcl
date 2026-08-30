# Policy for GitHub Actions runners (OIDC JWT)
# Grants read-only access to all garcar production secrets

path "secret/data/garcar/*" {
  capabilities = ["read"]
}

path "secret/metadata/garcar/*" {
  capabilities = ["list", "read"]
}

# Allow listing the top-level paths for validation workflows
path "secret/metadata/garcar" {
  capabilities = ["list"]
}
