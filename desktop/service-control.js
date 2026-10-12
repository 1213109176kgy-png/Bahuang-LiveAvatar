const http = require('node:http');
// Keep the controller alive when the voice/web server has been stopped.
function listen({port = 17860, webPort, perform}) {
  let busy = false;
  const server = http.createServer(async (req, res) => {
    const origins = [`http://localhost:${webPort()}`, `http://127.0.0.1:${webPort()}`];
    const origin = req.headers.origin;
    const allowed = origins.includes(origin);
    if (allowed) {
      res.setHeader('Access-Control-Allow-Origin', origin);
      res.setHeader('Vary', 'Origin');
      res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const reply = (code, data) => {res.writeHead(code); res.end(JSON.stringify(data));};
    if (!allowed) return reply(403, {ok:false,message:'无效页面来源'});
    if (req.url !== '/services') return reply(404, {ok:false});
    if (req.method === 'OPTIONS') {res.writeHead(204); return res.end();}
    if (req.method !== 'POST' || !req.headers['content-type']?.startsWith('application/json')) return reply(405, {ok:false});
    if (busy) return reply(409, {ok:false,message:'服务正在切换，请稍等'});
    let body = '';
    for await (const chunk of req) {
      body += chunk;
      if (body.length > 1024) return reply(413, {ok:false});
    }
    try {
      const {action} = JSON.parse(body);
      if (!['stop','restart'].includes(action)) return reply(400, {ok:false,message:'无效操作'});
      busy = true;
      reply(200, await perform(action));
    } catch (error) {reply(500, {ok:false,message:error.message});}
    finally {busy = false;}
  });
  return new Promise((resolve,reject) => {
    server.once('error',reject);
    server.listen(port,'127.0.0.1',()=>resolve(server));
  });
}
module.exports = {listen};
