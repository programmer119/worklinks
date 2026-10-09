// WorkLinks user-state API. Node.js >=20, no external packages.
// Run behind HTTPS reverse proxy. Data stays in a private directory, never GitHub Pages.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const PORT = Number(process.env.WORKLINKS_STATE_PORT || 18191);
const HOST = process.env.WORKLINKS_STATE_HOST || '127.0.0.1';
const DATA_DIR = process.env.WORKLINKS_STATE_DATA_DIR || '/home/worklinks/data/user-states';
const SECRET = process.env.WORKLINKS_SESSION_SECRET || '';
const allowedOrigins = (process.env.WORKLINKS_ALLOWED_ORIGINS || 'https://worklinks.suaveforge.com,https://programmer119.github.io')
  .split(',').map(x => x.trim()).filter(Boolean);
const users = JSON.parse(process.env.WORKLINKS_USERS_JSON || '{}');
const allowedFields = new Set(['status','hidden','business','outcomes']);
const loginAttempts = new Map();
const cookieName = 'wl_session_v1';

if (process.argv[2] === 'hash') {
  const pass = process.argv[3];
  if (!pass || pass.length < 12) { console.error('Usage: node worklinks-state-api.mjs hash "a password with 12+ characters"'); process.exit(1); }
  const salt = crypto.randomBytes(24).toString('hex');
  const hash = crypto.scryptSync(pass,salt,64).toString('hex');
  console.log('scrypt$' + salt + '$' + hash);
  process.exit(0);
}
if (SECRET.length < 32) throw Error('Set WORKLINKS_SESSION_SECRET to a random 32+ character value');
if (!Object.keys(users).length) throw Error('Set WORKLINKS_USERS_JSON with at least one login and its password hash');
fs.mkdirSync(DATA_DIR,{recursive:true,mode:0o700});

function hmac(input){return crypto.createHmac('sha256',SECRET).update(input).digest('base64url');}
function tokenFor(user){
  const payload=Buffer.from(JSON.stringify({u:user,exp:Date.now()+14*86400000})).toString('base64url');
  return payload+'.'+hmac(payload);
}
function verifyToken(token){
  if(!token||token.length>3000)return null;
  const i=token.lastIndexOf('.');if(i<1)return null;
  const body=token.slice(0,i),sig=token.slice(i+1),expect=hmac(body);
  if(sig.length!==expect.length||!crypto.timingSafeEqual(Buffer.from(sig),Buffer.from(expect)))return null;
  try{const t=JSON.parse(Buffer.from(body,'base64url').toString('utf8'));return t.exp>Date.now()&&Object.hasOwn(users,t.u)?t.u:null;}catch{return null;}
}
function getUser(req){
  const cookie=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(cookieName+'='));
  return verifyToken(cookie?cookie.slice(cookieName.length+1):'');
}
function validPassword(user,pass){
  const stored=users[user]||'';const parts=stored.split('$');
  if(parts.length!==3||parts[0]!=='scrypt')return false;
  const expected=Buffer.from(parts[2],'hex');
  if(!expected.length||expected.length!==64)return false;
  const derived=crypto.scryptSync(String(pass||''),parts[1],expected.length);
  return crypto.timingSafeEqual(expected,derived);
}
function json(res,code,body,headers={}){
  const content=JSON.stringify(body);
  res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Content-Length':Buffer.byteLength(content),...headers});
  res.end(content);
}
function defaultDb(){return{version:2,counter:0,status:{},hidden:{},business:{},outcomes:{},revisions:{status:{},hidden:{},business:{},outcomes:{}},migrations:[],seenOps:[]};}
function fileFor(user){return path.join(DATA_DIR,crypto.createHash('sha256').update(user).digest('hex')+'.json');}
function load(user){
  try{const db=JSON.parse(fs.readFileSync(fileFor(user),'utf8'));return{...defaultDb(),...db};}
  catch(e){if(e.code==='ENOENT')return defaultDb();throw e;}
}
function save(user,db){
  const file=fileFor(user),tmp=file+'.'+crypto.randomUUID()+'.tmp';
  try{fs.writeFileSync(tmp,JSON.stringify(db),{mode:0o600,flag:'wx'});if(fs.existsSync(file))fs.copyFileSync(file,file+'.bak');fs.renameSync(tmp,file);}
  finally{try{fs.unlinkSync(tmp);}catch{}}
}
function snapshot(db){return{status:db.status,hidden:db.hidden,business:db.business,outcomes:db.outcomes,revisions:db.revisions};}
function touch(db,field,key){db.counter=(db.counter||0)+1;db.revisions[field][key]=db.counter;}
function validKey(key){return typeof key==='string'&&key.length<=180&&/^[a-zA-Z0-9._:-]+$/.test(key);}
function permittedOrigin(req){
  const origin=req.headers.origin;
  return !origin||allowedOrigins.includes(origin);
}
async function readBody(req){
  let chunks=[],size=0;
  for await(const chunk of req){size+=chunk.length;if(size>131072)throw Error('payload too large');chunks.push(chunk);}
  return JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');
}
function loginAllowed(ip){
  const now=Date.now(),arr=(loginAttempts.get(ip)||[]).filter(t=>now-t<600000);
  loginAttempts.set(ip,arr);
  return arr.length<8;
}
function recordLoginFailure(ip){const arr=loginAttempts.get(ip)||[];arr.push(Date.now());loginAttempts.set(ip,arr);}
async function handle(req,res){
  const origin=req.headers.origin;
  if(origin&&allowedOrigins.includes(origin)){
    res.setHeader('Access-Control-Allow-Origin',origin);
    res.setHeader('Access-Control-Allow-Credentials','true');
    res.setHeader('Vary','Origin');
  }
  if(origin&&!permittedOrigin(req))return json(res,403,{error:'허용되지 않은 출처'});
  if(req.method==='OPTIONS'){
    res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers','Content-Type,X-Worklinks-Client');
    return res.writeHead(204).end();
  }
  if(!req.url?.startsWith('/api/worklinks/'))return json(res,404,{error:'Not found'});
  if(req.method==='POST'&&req.headers['x-worklinks-client']!=='web')return json(res,403,{error:'요청 검증 실패'});
  const route=req.url.split('?')[0].slice('/api/worklinks/'.length);
  if(route==='login'&&req.method==='POST'){
    const ip=req.socket.remoteAddress||'unknown';
    if(!loginAllowed(ip))return json(res,429,{error:'잠시 후 다시 시도해주세요'});
    const body=await readBody(req);
    const user=String(body.user||'').trim();
    if(!validPassword(user,body.password)) {
      recordLoginFailure(ip);return json(res,401,{error:'아이디 또는 비밀번호가 올바르지 않습니다'});
    }
    loginAttempts.delete(ip);
    const cookie=cookieName+'='+tokenFor(user)+'; HttpOnly; Secure; SameSite=None; Path=/api/worklinks; Max-Age=1209600';
    return json(res,200,{user},{'Set-Cookie':cookie});
  }
  const user=getUser(req);
  if(route==='session'&&req.method==='GET')return json(res,200,{user});
  if(route==='logout'&&req.method==='POST')return json(res,200,{ok:true},{'Set-Cookie':cookieName+'=; HttpOnly; Secure; SameSite=None; Path=/api/worklinks; Max-Age=0'});
  if(!user)return json(res,401,{error:'로그인이 필요합니다'});
  if(route==='state'&&req.method==='GET')return json(res,200,{state:snapshot(load(user))});
  if(route==='state/bootstrap'&&req.method==='POST'){
    const input=await readBody(req),migrationId=String(input.migrationId||'');
    if(!/^[a-zA-Z0-9:_-]{10,160}$/.test(migrationId))return json(res,400,{error:'Invalid migrationId'});
    const db=load(user);
    if(!db.migrations.includes(migrationId)){
      for(const field of ['status','hidden','business']){
        const src=input[field]||{};
        if(src&&typeof src==='object'&&!Array.isArray(src))
          for(const [key,val] of Object.entries(src))if(validKey(key)&&val===true&&db[field][key]!==true){db[field][key]=true;touch(db,field,key);}
      }
      const src=input.outcomes||{};
      if(src&&typeof src==='object'&&!Array.isArray(src))
        for(const [key,val] of Object.entries(src))if(validKey(key)&&['success','failure'].includes(val)&&!db.outcomes[key]){db.outcomes[key]=val;touch(db,'outcomes',key);}
      db.migrations.push(migrationId);if(db.migrations.length>3000)db.migrations.shift();
      save(user,db);
    }
    return json(res,200,{migrationId,state:snapshot(db)});
  }
  if(route==='state/patch'&&req.method==='POST'){
    const input=await readBody(req),ops=input.operations;
    if(!Array.isArray(ops)||ops.length>100)return json(res,400,{error:'Invalid operations'});
    for(const op of ops){
      if(!op||typeof op.id!=='string'||op.id.length>120||!validKey(op.key)||!allowedFields.has(op.field))return json(res,400,{error:'Invalid operation'});
      if(op.field==='outcomes'?!['pending','success','failure'].includes(op.value):typeof op.value!=='boolean')return json(res,400,{error:'Invalid value'});
      if(!Number.isSafeInteger(op.baseRevision)||op.baseRevision<0)return json(res,400,{error:'Invalid revision'});
    }
    const db=load(user),seen=new Set(db.seenOps),conflicts=[],accepted=[];
    for(const op of ops){
      if(seen.has(op.id)){accepted.push(op.id);continue;}
      const actual=db.revisions[op.field][op.key]||0;
      if(actual!==op.baseRevision&&db[op.field][op.key]!==op.value){
        conflicts.push({id:op.id,field:op.field,key:op.key,serverValue:db[op.field][op.key],serverRevision:actual});
        continue;
      }
      if(db[op.field][op.key]!==op.value){db[op.field][op.key]=op.value;touch(db,op.field,op.key);}
      db.seenOps.push(op.id);seen.add(op.id);accepted.push(op.id);
    }
    if(db.seenOps.length>3000)db.seenOps=db.seenOps.slice(-3000);
    if(accepted.length)save(user,db);
    return json(res,200,{state:snapshot(db),accepted,conflicts});
  }
  return json(res,404,{error:'Not found'});
}
http.createServer((req,res)=>{handle(req,res).catch(err=>{console.error('WorkLinks state API:',err);if(!res.headersSent)json(res,500,{error:'서버 내부 오류'});else res.end();});})
  .listen(PORT,HOST,()=>console.log('WorkLinks state API listening on '+HOST+':'+PORT));
