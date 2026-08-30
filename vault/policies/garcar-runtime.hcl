# Policy for runtime containers / Vault Agent
# Slightly broader than CI so services can renew leases if needed

path "secret/data/garcar/*" {
  capabilities = ["read"]
}

path "secret/metadata/garcar/*" {
  capabilities = ["list", "read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
