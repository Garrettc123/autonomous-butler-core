export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', worker: 'health-monitor', timestamp: new Date().toISOString() });
    }

    if (url.pathname === '/status' && request.method === 'GET') {
      const { results } = await env.DB.prepare('SELECT COUNT(*) AS cnt FROM sqlite_master').all();
      return Response.json({ status: 'ok', db_tables: results[0].cnt });
    }

    return new Response('Not Found', { status: 404 });
  },
};
