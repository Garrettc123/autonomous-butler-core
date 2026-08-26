export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', worker: 'stripe-poller', timestamp: new Date().toISOString() });
    }

    if (url.pathname === '/poll' && request.method === 'POST') {
      const since = await env.CONFIG_KV.get('stripe_poller_last_event_id') ?? '';
      return Response.json({ ok: true, polled_since: since });
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(event, env) {
    const since = await env.CONFIG_KV.get('stripe_poller_last_event_id') ?? '';
    console.log(`stripe-poller scheduled tick, since=${since}`);
  },
};
