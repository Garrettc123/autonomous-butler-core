# Garcar Multiplex — GitHub Secrets Setup Guide

All credentials must be stored as **GitHub Actions Secrets** — never in code files.

Go to: **Settings → Secrets and variables → Actions → New repository secret**

> 🔗 Direct link: https://github.com/Garrettc123/autonomous-butler-core/settings/secrets/actions

---

## Required Secrets — Add These Now

### GitHub
| Secret Name | Where to Get It |
|---|---|
| `GARCAR_GITHUB_TOKEN` | https://github.com/settings/tokens → New token (classic) → `repo`, `workflow`, `admin:org` scopes |

### Slack
| Secret Name | Where to Get It |
|---|---|
| `SLACK_BOT_TOKEN` | https://api.slack.com/apps → Your App → OAuth & Permissions → Bot User OAuth Token |
| `SLACK_WEBHOOK_URL` | https://api.slack.com/apps → Your App → Incoming Webhooks |
| `SLACK_CHANNEL_REVENUE` | Slack channel ID (e.g., `C0XXXXXXX`) for revenue alerts |
| `SLACK_CHANNEL_OPS` | Slack channel ID for ops/integration reports |
| `SLACK_CHANNEL_ALERTS` | Slack channel ID for critical alerts |

### Base by Coinbase
| Secret Name | Where to Get It |
|---|---|
| `COINBASE_CDP_API_KEY_NAME` | https://portal.cdp.coinbase.com → API Keys → Key Name |
| `COINBASE_CDP_PRIVATE_KEY` | https://portal.cdp.coinbase.com → API Keys → Private Key (PEM) |
| `BASE_NETWORK_RPC_URL` | `https://mainnet.base.org` (public) or your private RPC |
| `BASE_WALLET_ADDRESS` | Your Base L2 wallet address (0x...) |
| `COINBASE_COMMERCE_API_KEY` | https://beta.commerce.coinbase.com/settings/security |

### Shopify
| Secret Name | Where to Get It |
|---|---|
| `SHOPIFY_STORE_DOMAIN` | e.g., `your-store.myshopify.com` |
| `SHOPIFY_ADMIN_API_TOKEN` | Shopify Admin → Apps → Private Apps → Admin API access token |
| `SHOPIFY_STOREFRONT_TOKEN` | Shopify Admin → Apps → Storefront API access token |
| `SHOPIFY_WEBHOOK_SECRET` | Shopify Admin → Settings → Notifications → Webhooks → Secret |

### Notion
| Secret Name | Where to Get It |
|---|---|
| `NOTION_API_KEY` | https://www.notion.so/my-integrations → New integration → Secret |
| `NOTION_REVENUE_DB_ID` | Open your Revenue database in Notion → copy ID from URL |
| `NOTION_OPS_DB_ID` | Open your Ops database in Notion → copy ID from URL |
| `NOTION_LEADS_DB_ID` | Open your Leads database in Notion → copy ID from URL |

### Linear
| Secret Name | Where to Get It |
|---|---|
| `LINEAR_API_KEY` | https://linear.app/settings/api → Personal API keys → New key |
| `LINEAR_TEAM_ID` | Linear → Settings → Teams → copy team ID from URL |
| `LINEAR_PROJECT_ID` | Linear → Projects → copy project ID from URL (optional) |
| `LINEAR_WEBHOOK_SECRET` | Linear → Settings → API → Webhooks → Secret |

### Supabase
| Secret Name | Where to Get It |
|---|---|
| `SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API → anon public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API → service_role key |
| `SUPABASE_DB_URL` | Supabase Dashboard → Settings → Database → Connection string |

### Hugging Face
| Secret Name | Where to Get It |
|---|---|
| `HUGGINGFACE_TOKEN` | https://huggingface.co/settings/tokens → New token (write access) |
| `HUGGINGFACE_SPACE_ID` | Your Space ID (e.g., `Garrettc123/my-space`) |
| `HUGGINGFACE_MODEL_REPO` | Your model repo ID (e.g., `Garrettc123/my-model`) |

### Stripe (Revenue Core)
| Secret Name | Where to Get It |
|---|---|
| `STRIPE_SECRET_KEY` | https://dashboard.stripe.com/apikeys → Secret key (`sk_live_...`) |
| `STRIPE_WEBHOOK_SECRET` | https://dashboard.stripe.com/webhooks → Signing secret (`whsec_...`) |
| `STRIPE_PUBLISHABLE_KEY` | https://dashboard.stripe.com/apikeys → Publishable key (`pk_live_...`) |

### AI Providers
| Secret Name | Where to Get It |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |

---

## Supabase Tables Required

Run these in your Supabase SQL editor:

```sql
-- Revenue events ledger (all platforms write here)
CREATE TABLE IF NOT EXISTS gc_revenue_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source TEXT NOT NULL,
  amount_usd NUMERIC(12, 2) NOT NULL DEFAULT 0,
  order_count INTEGER DEFAULT 0,
  metadata JSONB DEFAULT '{}',
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- HuggingFace model registry
CREATE TABLE IF NOT EXISTS hf_model_registry (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  space_id TEXT UNIQUE,
  name TEXT,
  sdk TEXT,
  downloads INTEGER DEFAULT 0,
  synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE gc_revenue_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE hf_model_registry ENABLE ROW LEVEL SECURITY;
```

---

## Verify Setup

After adding all secrets, manually trigger the workflow:

https://github.com/Garrettc123/autonomous-butler-core/actions/workflows/garcar-multiplex-integration.yml

Set **mode = health-check** first to validate all credentials before running the full sync.
