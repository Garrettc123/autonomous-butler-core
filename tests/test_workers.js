import { describe, it, expect, beforeAll } from 'vitest';
import { unstable_dev } from 'wrangler';

// Miniflare-based integration tests for each Cloudflare Worker.
// These tests use wrangler's `unstable_dev` API which spins up a local
// worker runtime backed by Miniflare.

const WORKERS = [
  { name: 'config-bus',      dir: 'workers/config-bus' },
  { name: 'health-monitor',  dir: 'workers/health-monitor' },
  { name: 'stripe-webhook',  dir: 'workers/stripe-webhook' },
  { name: 'stripe-poller',   dir: 'workers/stripe-poller' },
  { name: 'lead-router',     dir: 'workers/lead-router' },
];

// ---------------------------------------------------------------------------
// /health endpoint — present on every worker
// ---------------------------------------------------------------------------
describe.each(WORKERS)('GET /health — $name', ({ name, dir }) => {
  let worker;

  beforeAll(async () => {
    worker = await unstable_dev(`${dir}/src/index.js`, {
      experimental: { disableExperimentalWarning: true },
      local: true,
    });
  });

  it('returns 200 with status ok', async () => {
    const res = await worker.fetch('/health');
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.worker).toBe(name);
    expect(typeof body.timestamp).toBe('string');
  });

  it('returns 404 for unknown routes', async () => {
    const res = await worker.fetch('/unknown-route');
    expect(res.status).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// config-bus specific
// ---------------------------------------------------------------------------
describe('config-bus — /config routing', () => {
  let worker;

  beforeAll(async () => {
    worker = await unstable_dev('workers/config-bus/src/index.js', {
      experimental: { disableExperimentalWarning: true },
      local: true,
      bindings: { CONFIG_KV: {} },
    });
  });

  it('GET /config without key returns 400', async () => {
    const res = await worker.fetch('/config');
    expect(res.status).toBe(400);
  });
});

// ---------------------------------------------------------------------------
// stripe-webhook specific
// ---------------------------------------------------------------------------
describe('stripe-webhook — /webhook routing', () => {
  let worker;

  beforeAll(async () => {
    worker = await unstable_dev('workers/stripe-webhook/src/index.js', {
      experimental: { disableExperimentalWarning: true },
      local: true,
    });
  });

  it('POST /webhook without stripe-signature returns 400', async () => {
    const res = await worker.fetch('/webhook', {
      method: 'POST',
      body: JSON.stringify({ id: 'evt_test', type: 'payment_intent.succeeded' }),
    });
    expect(res.status).toBe(400);
  });
});

// ---------------------------------------------------------------------------
// lead-router specific
// ---------------------------------------------------------------------------
describe('lead-router — /leads routing', () => {
  let worker;

  beforeAll(async () => {
    worker = await unstable_dev('workers/lead-router/src/index.js', {
      experimental: { disableExperimentalWarning: true },
      local: true,
    });
  });

  it('POST /leads without email returns 400', async () => {
    const res = await worker.fetch('/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'test' }),
    });
    expect(res.status).toBe(400);
  });
});
