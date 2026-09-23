import http from 'node:http';
import fs from 'node:fs';
import crypto from 'node:crypto';

const ENV_PATH = '/home/worklinks/secrets/naver.env';
const BOOTSTRAP_PRIVATE = '/home/worklinks/bootstrap/private.pem';
const BOOTSTRAP_PUBLIC = '/home/worklinks/bootstrap/public.pem';
const PORT = Number(process.env.PORT || 18190);
const CACHE_MS = 60 * 60 * 1000;

const DEFAULT_QUERIES = [
  '엑셀 관리',
  '수기로 관리',
  '입금 확인',
  '예약 관리 힘들다',
  '이런 프로그램 없나요',
  '돈 내고라도',
  '유료라도 프로그램',
  '단톡방 관리',
  '회원관리 회비',
  '대회 접수',
  '업체 추천 홈페이지',
  '자동으로 안되나'
];

let cacheAt = 0;
let cacheData = null;
let scanPromise = null;

function configured() {
  try { return fs.statSync(ENV_PATH).isFile() && fs.statSync(ENV_PATH).size > 10; }
  catch { return false; }
}

function credentials() {
  const raw = fs.readFileSync(ENV_PATH, 'utf8');
  const env = {};
  for (const line of raw.split(/\r?\n/)) {
    if (!line || line.startsWith('#')) continue;
    const i = line.indexOf('=');
    if (i > 0) env[line.slice(0, i)] = line.slice(i + 1);
  }
  if (!env.NAVER_CLIENT_ID || !env.NAVER_CLIENT_SECRET) throw new Error('NAVER credentials missing');
  return { id: env.NAVER_CLIENT_ID, secret: env.NAVER_CLIENT_SECRET };
}

function clean(s='') {
  return String(s)
    .replace(/<[^>]*>/g, '')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

async function searchCafe(query, display=20, start=1, sort='date') {
  const { id, secret } = credentials();
  const url = new URL('https://openapi.naver.com/v1/search/cafearticle.json');
  url.searchParams.set('query', query);
  url.searchParams.set('display', String(Math.max(1, Math.min(100, display))));
  url.searchParams.set('start', String(Math.max(1, Math.min(1000, start))));
  url.searchParams.set('sort', sort === 'sim' ? 'sim' : 'date');
  const r = await fetch(url, {
    headers: {
      'X-Naver-Client-Id': id,
      'X-Naver-Client-Secret': secret
    },
    signal: AbortSignal.timeout(15000)
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`NAVER_API_${r.status}:${text.slice(0, 180)}`);
  const d = JSON.parse(text);
  return {
    query,
    total: Number(d.total || 0),
    start: Number(d.start || start),
    display: Number(d.display || display),
    items: (d.items || []).map(x => ({
      title: clean(x.title),
      link: x.link,
      description: clean(x.description),
      cafename: clean(x.cafename),
      cafeurl: x.cafeurl
    }))
  };
}

async function runScan(force=false) {
  const now = Date.now();
  if (!force && cacheData && now - cacheAt < CACHE_MS) return cacheData;
  if (scanPromise) return scanPromise;
  scanPromise = (async () => {
    const buckets = [];
    for (const q of DEFAULT_QUERIES) {
      try { buckets.push(await searchCafe(q, 20, 1, 'date')); }
      catch (e) { buckets.push({ query:q, error:String(e.message || e), total:0, items:[] }); }
    }
    const seen = new Set();
    const items = [];
    for (const b of buckets) {
      for (const item of (b.items || [])) {
        const key = item.link || `${item.cafename}|${item.title}`;
        if (seen.has(key)) continue;
        seen.add(key);
        items.push({ ...item, matched_query:b.query });
      }
    }
    cacheData = {
      ok: true,
      generated_at: new Date().toISOString(),
      cache_seconds: CACHE_MS / 1000,
      query_count: DEFAULT_QUERIES.length,
      item_count: items.length,
      queries: buckets.map(b => ({
        query:b.query, total:b.total, error:b.error || null, count:(b.items || []).length
      })),
      items: items.slice(0, 200)
    };
    cacheAt = Date.now();
    return cacheData;
  })();
  try { return await scanPromise; } finally { scanPromise = null; }
}

function loopback(req) {
  const a = req.socket.remoteAddress || '';
  return a === '127.0.0.1' || a === '::1' || a === '::ffff:127.0.0.1';
}

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'content-type':'application/json; charset=utf-8',
    'cache-control':'no-store',
    'x-content-type-options':'nosniff'
  });
  res.end(body);
}

function bootstrap(payload) {
  if (configured()) return { code:409, body:{ok:false,error:'already_configured'} };
  if (!fs.existsSync(BOOTSTRAP_PRIVATE)) return { code:410, body:{ok:false,error:'bootstrap_closed'} };
  if (!payload || payload.length > 2000) return { code:400, body:{ok:false,error:'invalid_payload'} };
  const privateKey = fs.readFileSync(BOOTSTRAP_PRIVATE);
  let plain;
  try {
    plain = crypto.privateDecrypt(
      { key:privateKey, padding:crypto.constants.RSA_PKCS1_OAEP_PADDING, oaepHash:'sha256' },
      Buffer.from(payload, 'base64')
    ).toString('utf8');
  } catch {
    return { code:400, body:{ok:false,error:'decrypt_failed'} };
  }
  const lines = plain.split(/\r?\n/).filter(Boolean);
  const id = lines.find(x => x.startsWith('NAVER_CLIENT_ID='))?.slice('NAVER_CLIENT_ID='.length);
  const secret = lines.find(x => x.startsWith('NAVER_CLIENT_SECRET='))?.slice('NAVER_CLIENT_SECRET='.length);
  if (!id || !secret || /\s/.test(id) || /\s/.test(secret) || id.length > 200 || secret.length > 200) {
    return { code:400, body:{ok:false,error:'credential_format_invalid'} };
  }
  fs.mkdirSync('/home/worklinks/secrets', { recursive:true, mode:0o700 });
  const tmp = ENV_PATH + '.tmp';
  fs.writeFileSync(tmp, `NAVER_CLIENT_ID=${id}\nNAVER_CLIENT_SECRET=${secret}\n`, { mode:0o600 });
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, ENV_PATH);
  fs.chmodSync(ENV_PATH, 0o600);
  for (const p of [BOOTSTRAP_PRIVATE, BOOTSTRAP_PUBLIC]) {
    try { fs.unlinkSync(p); } catch {}
  }
  cacheAt = 0;
  cacheData = null;
  return { code:200, body:{ok:true,configured:true} };
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, 'http://localhost');
    if (u.pathname === '/health') {
      return send(res, 200, {ok:true, service:'worklinks-naver-cafe', configured:configured()});
    }
    if (u.pathname === '/bootstrap') {
      const r = bootstrap(u.searchParams.get('payload') || '');
      return send(res, r.code, r.body);
    }
    if (u.pathname === '/api/naver-cafe-scan') {
      if (!configured()) return send(res, 503, {ok:false,error:'not_configured'});
      const force = loopback(req) && u.searchParams.get('force') === '1';
      return send(res, 200, await runScan(force));
    }
    if (u.pathname === '/internal/search') {
      if (!loopback(req)) return send(res, 403, {ok:false,error:'forbidden'});
      if (!configured()) return send(res, 503, {ok:false,error:'not_configured'});
      const q = (u.searchParams.get('q') || '').trim();
      if (!q || q.length > 100) return send(res, 400, {ok:false,error:'invalid_query'});
      const display = Number(u.searchParams.get('display') || 10);
      return send(res, 200, {ok:true, ...(await searchCafe(q, display, 1, 'date'))});
    }
    return send(res, 404, {ok:false,error:'not_found'});
  } catch (e) {
    return send(res, 502, {ok:false,error:String(e.message || e).slice(0,240)});
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`worklinks-naver-cafe listening on 127.0.0.1:${PORT}`);
});
