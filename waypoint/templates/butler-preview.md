# Template: butler-preview

**Purpose**: Short-lived preview / PR environments.

## Inputs

| Variable | Type | Default |
|----------|------|---------|
| environment | string | preview |
| image | string | (from CI sha tag) |
| replicas | number | 1 |
| namespace | string | autonomous-butler-preview |

Same Vault injection model as production. Destroy after merge.
