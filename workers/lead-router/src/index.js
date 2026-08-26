export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', worker: 'lead-router', timestamp: new Date().toISOString() });
    }

    if (url.pathname === '/leads' && request.method === 'POST') {
      const lead = await request.json();
      if (!lead.email) return new Response('Missing email', { status: 400 });

      const id = crypto.randomUUID();
      const now = new Date().toISOString();

      await env.DB.prepare(
        'INSERT INTO leads (id, email, source, payload, created_at) VALUES (?, ?, ?, ?, ?)'
      ).bind(id, lead.email, lead.source ?? 'unknown', JSON.stringify(lead), now).run();

      await env.LEADS_KV.put(`lead:${id}`, JSON.stringify({ ...lead, id, created_at: now }));

      return Response.json({ ok: true, id }, { status: 201 });
    }

    if (url.pathname === '/leads' && request.method === 'GET') {
      const { results } = await env.DB.prepare('SELECT id, email, source, created_at FROM leads ORDER BY created_at DESC LIMIT 50').all();
      return Response.json({ leads: results });
    }

    return new Response('Not Found', { status: 404 });
  },
};
