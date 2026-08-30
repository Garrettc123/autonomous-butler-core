# Garcar Vault Secret Paths (KV v2)

All secrets live under the `secret/` mount (KV v2).

## Path Layout

```
secret/data/garcar/
├── ai/                  # ANTHROPIC_API_KEY, OPENAI_API_KEY, HUGGINGFACE_API_TOKEN, HF_*
├── github/              # GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, GITHUB_USERNAME, GITHUB_ORG
├── slack/               # SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SIGNING_SECRET, SLACK_WEBHOOK_URL, SLACK_CHANNEL_*
├── base/                # COINBASE_CDP_*, GARCAR_WALLET_ADDRESS, BASE_RPC_URL, USDC_BASE_CONTRACT
├── shopify/             # SHOPIFY_*
├── notion/              # NOTION_*
├── linear/              # LINEAR_*
├── supabase/            # SUPABASE_*
├── wix/                 # WIX_*
├── hubspot/             # HUBSPOT_*
├── apollo/              # APOLLO_*
├── docusign/            # DOCUSIGN_*
├── google/              # GOOGLE_*
├── clickup/             # CLICKUP_*
├── asana/               # ASANA_*
├── stripe/              # STRIPE_*
├── enrichment/          # CLEARBIT_API_KEY, HUNTER_API_KEY, ICP_KEYWORDS, LEAD_QUALIFY_SCORE
└── infra/               # AWS_*, KUBERNETES_*, KAFKA_*, REDIS_URL, POSTGRES_URL, PROMETHEUS_URL, PAGERDUTY_API_KEY, ENVIRONMENT, LOG_LEVEL, AUTO_*
```

## Example write commands

```bash
vault kv put secret/garcar/ai \
  ANTHROPIC_API_KEY="sk-ant-..." \
  OPENAI_API_KEY="sk-..." \
  HUGGINGFACE_API_TOKEN="hf_..." \
  HF_LEAD_SCORER_MODEL="Garrettc123/lead-scoring-model" \
  HF_DEAL_CLASSIFIER_MODEL="Garrettc123/deal-pipeline-classifier" \
  HF_INFERENCE_ENDPOINT="https://api-inference.huggingface.co/models"

vault kv put secret/garcar/github \
  GITHUB_TOKEN="ghp_..." \
  GITHUB_USERNAME="Garrettc123" \
  GITHUB_ORG="Garrettc123" \
  GITHUB_WEBHOOK_SECRET="$(openssl rand -hex 16)"

# ... repeat for every platform
```

## Reading in GitHub Actions

The `hashicorp/vault-action` step uses the wildcard syntax so every key becomes an environment variable automatically.
