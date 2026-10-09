import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const server = path.join(root, 'server/worklinks-state-api.mjs');
const html = fs.readFileSync(path.join(root, 'startup-support/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];

test('HTML script compiles, old status keys and separate completed tab remain', () => {
  assert.ok(script, 'inline script exists');
  new vm.Script(script, {filename:'startup-support/index.html'});
  assert.match(html,/data-tab="applied"/);
  assert.doesNotMatch(html,/data-f="applied"/);
  assert.match(script,/externaltools_startup_support_status_v1/);
  assert.match(script,/worklinks_startup_support_hidden_v1/);
  assert.match(script,/worklinks_startup_support_business_v1/);
  assert.doesNotMatch(script,/localStorage\.clear\(/);
});

test('unknown deadlines never produce NaN or break ascending order; submitted excluded', () => {
  const start=script.indexOf('function deadlineMillis(');
  const end=script.indexOf('function renderPager(',start);
  assert.ok(start>0&&end>start);
  const fns=script.slice(start,end).replaceAll('Date.now()','clock');
  const derive=new Function('items','saved','hidden','business','category','filter','clock',
      fns+'; return {dayDiff,ddayHtml,visibleItems};');
  const items=[
    {id:'etri',deadline:'2026-10-16T18:00:00+09:00',category:'general'},
    {id:'water',deadline:'2026-10-19T18:00:00+09:00',category:'general'},
    {id:'road',deadline:'2026-10-28T18:00:00+09:00',category:'general'},
    {id:'comeup',deadline:'마감 시각 미확인',category:'general'},
    {id:'yongsan',deadline:'2026-10-11',category:'consulting'},
    {id:'submitted',deadline:'2026-10-10T18:00:00+09:00',category:'general'}
  ];
  const saved={submitted:true},clock=Date.parse('2026-10-09T11:59:00+09:00');
  const normal=derive(items,saved,{},{} ,'all','all',clock);
  assert.deepEqual(normal.visibleItems().map(x=>x.id),['yongsan','etri','water','road','comeup']);
  assert.equal(normal.dayDiff('2026-10-11'),2);
  assert.equal(normal.dayDiff('마감 시각 미확인'),null);
  assert.doesNotMatch(normal.ddayHtml(items[3]),/NaN/);
  const completed=derive(items,saved,{},{} ,'applied','all',clock);
  assert.deepEqual(completed.visibleItems().map(x=>x.id),['submitted']);
});

function freePort(){
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;socket.close(()=>resolve(port));});
  });
}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

test('authenticated server migrates historic values without deletion, stores and detects conflicts', {timeout:20000}, async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'worklinks-test-'));
  const password='integration test password 123';
  const hash=spawnSync(process.execPath,[server,'hash',password],{encoding:'utf8'});
  assert.equal(hash.status,0,hash.stderr);
  const port=await freePort();
  const child=spawn(process.execPath,[server],{
    env:{...process.env,WORKLINKS_STATE_PORT:String(port),WORKLINKS_STATE_DATA_DIR:dir,
      WORKLINKS_SESSION_SECRET:'32-chars-minimum-not-production-secret-0123456789',
      WORKLINKS_USERS_JSON:JSON.stringify({tester:hash.stdout.trim()}),
      WORKLINKS_ALLOWED_ORIGINS:'https://worklinks.suaveforge.com'},
    stdio:['ignore','pipe','pipe']
  });
  let logs='';
  child.stderr.on('data',v=>{logs+=v.toString();});
  const url='http://127.0.0.1:'+port+'/api/worklinks/';
  async function request(route,{method='GET',body,cookie}={}){
    const res=await fetch(url+route,{method,headers:{
      'Origin':'https://worklinks.suaveforge.com','X-Worklinks-Client':'web',
      ...(body?{'Content-Type':'application/json'}:{}),...(cookie?{'Cookie':cookie}:{})
    },body:body?JSON.stringify(body):undefined});
    return {status:res.status,data:await res.json(),headers:res.headers};
  }
  try{
    let started=false;
    for(let i=0;i<60;i++){
      if(child.exitCode!==null)break;
      try{const r=await request('session');if(r.status===200){started=true;break;}}catch{}
      await sleep(100);
    }
    assert.ok(started,logs);
    let unauth=await request('state');
    assert.equal(unauth.status,401);
    let logged=await request('login',{method:'POST',body:{user:'tester',password}});
    assert.equal(logged.status,200,JSON.stringify(logged.data));
    const cookie=logged.headers.get('set-cookie')?.split(';')[0];
    assert.ok(cookie?.startsWith('wl_session_v1='));
    const migrationId='legacy-browser-test-123456789';
    let original=await request('state/bootstrap',{method:'POST',cookie,body:{
      migrationId,status:{previouslyApplied:true},hidden:{hiddenBefore:true},
      business:{laterBusiness:true},outcomes:{previouslyApplied:'success'}
    }});
    assert.equal(original.status,200);
    assert.equal(original.data.state.status.previouslyApplied,true);
    assert.equal(original.data.state.hidden.hiddenBefore,true);
    assert.equal(original.data.state.outcomes.previouslyApplied,'success');
    const rev=original.data.state.revisions.status.previouslyApplied;
    // Repeated migrations cannot erase previously applied records.
    let duplicate=await request('state/bootstrap',{method:'POST',cookie,body:{
      migrationId,status:{previouslyApplied:false},hidden:{hiddenBefore:false},outcomes:{previouslyApplied:'failure'}
    }});
    assert.equal(duplicate.data.state.status.previouslyApplied,true);
    assert.equal(duplicate.data.state.outcomes.previouslyApplied,'success');
    const changed=await request('state/patch',{method:'POST',cookie,body:{
      operations:[{id:'op-1',field:'status',key:'previouslyApplied',value:false,baseRevision:rev}]
    }});
    assert.equal(changed.data.state.status.previouslyApplied,false);
    const stale=await request('state/patch',{method:'POST',cookie,body:{
      operations:[{id:'op-stale',field:'status',key:'previouslyApplied',value:true,baseRevision:rev}]
    }});
    assert.equal(stale.data.conflicts.length,1);
    assert.equal(stale.data.state.status.previouslyApplied,false,'stale browser must not overwrite a newer change');
    const latestRev=stale.data.state.revisions.status.previouslyApplied;
    const recovered=await request('state/patch',{method:'POST',cookie,body:{
      operations:[{id:'op-resolve',field:'status',key:'previouslyApplied',value:true,baseRevision:latestRev}]
    }});
    assert.equal(recovered.data.state.status.previouslyApplied,true);
    const persisted=await request('state',{cookie});
    assert.equal(persisted.data.state.status.previouslyApplied,true);
    assert.equal(persisted.data.state.business.laterBusiness,true);
    assert.ok(fs.readdirSync(dir).some(x=>x.endsWith('.bak')),'backup before replacement');
    const noCookie=await request('state');
    assert.equal(noCookie.status,401,'private user states must be protected');
  }finally{
    child.kill('SIGTERM');
    fs.rmSync(dir,{recursive:true,force:true});
  }
});
