export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', worker: 'config-bus', timestamp: new Date().toISOString() });
    }

    if (url.pathname === '/config' && request.method === 'GET') {
      const key = url.searchParams.get('key');
      if (!key) return new Response('Missing key', { status: 400 });
      const value = await env.CONFIG_KV.get(key);
      if (value === null) return new Response('Not found', { status: 404 });
      return Response.json({ key, value });
    }

    if (url.pathname === '/config' && request.method === 'PUT') {
      const { key, value } = await request.json();
      if (!key || value === undefined) return new Response('Missing key or value', { status: 400 });
      await env.CONFIG_KV.put(key, String(value));
      return Response.json({ ok: true, key });
    }

    return new Response('Not Found', { status: 404 });
  },
};
