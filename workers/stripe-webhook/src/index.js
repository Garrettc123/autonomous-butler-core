export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', worker: 'stripe-webhook', timestamp: new Date().toISOString() });
    }

    if (url.pathname === '/webhook' && request.method === 'POST') {
      const body = await request.text();
      const sig = request.headers.get('stripe-signature');
      if (!sig) return new Response('Missing stripe-signature', { status: 400 });

      const event = JSON.parse(body);
      const eventId = event.id ?? crypto.randomUUID();

      await env.DB.prepare(
        'INSERT OR IGNORE INTO stripe_events (id, type, payload, created_at) VALUES (?, ?, ?, ?)'
      ).bind(eventId, event.type ?? 'unknown', body, new Date().toISOString()).run();

      return Response.json({ received: true, id: eventId });
    }

    return new Response('Not Found', { status: 404 });
  },
};
