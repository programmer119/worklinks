'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
function sourceOf(name,next){
  const s=html.indexOf('function '+name+'(');
  const e=html.indexOf('\nfunction '+next+'(',s);
  assert.ok(s>=0&&e>s,'JS function '+name+' exists');
  return html.slice(s,e);
}
function ranking(){
  const code=sourceOf('sortRank','categoryItems');
  const current='2026-11-07';
  const ctx={
    saved:{},
    dayDiff:x=>x==='2026-11-09'?2:x==='2026-11-07'?0:x==null?null:-5,
    isDeadlineExpired:x=>x.deadline==='2026-10-21',
    isSessionEnded:x=>x.eventEndDate&&x.eventEndDate<current,
    earlyCloseReason:x=>!!x.early
  };
  return vm.runInNewContext(code+';sortRank',ctx);
}
test('known upcoming date outranks undated alleged early-close',()=>{
  const rank=ranking();
  const known={deadline:'2026-11-09',early:false};
  const unknown={deadline:null,early:true};
  assert.ok(rank(known)<rank(unknown));
});
test('old session is not a live early-close opportunity',()=>{
  const rank=ranking();
  const old={deadline:null,early:true,eventEndDate:'2026-10-21'};
  assert.ok(rank(old)>rank({deadline:'2026-11-09',early:false}));
});
test('today retains priority over upcoming applications',()=>{
  const rank=ranking();
  assert.ok(rank({deadline:'2026-11-07'})<rank({deadline:'2026-11-09'}));
});
test('dated early-close remains ahead of ordinary upcoming applications',()=>{
  const rank=ranking();
  assert.ok(rank({deadline:'2026-11-09',early:true})<rank({deadline:'2026-11-09',early:false}));
});
test('laser and four other actually ended event sessions are flagged',()=>{
  const m=html.match(/var items=(\[.*?\]);/s);
  assert.ok(m);
  const rows=JSON.parse(m[1]);
  const targets=[
    ['ddm-maker-co2-laser-20261021','2026-10-21'],
    ['ksa-tbt-practical-training-fourth-20261028','2026-10-28'],
    ['ksa-digital-trade-practical-training-third-20261029','2026-10-29'],
    ['soongsil-campustown-ai-basic-2026-1','2026-11-05'],
    ['seongdong-socialventure-investment-lecture-20261029','2026-10-29']
  ];
  for(const [id,day] of targets){
    assert.equal(rows.find(x=>x.id===id)?.eventEndDate,day,id);
  }
});
test('no extra filter, copy-button, or changed sort strategy',()=>{
  assert.ok(!html.includes('id="kimseFitOnly"'));
  assert.ok(!html.includes('support-url-copy'));
  assert.ok(html.includes('return sortRank(a)-sortRank(b)||String(a.id).localeCompare(String(b.id))'));
  assert.ok(html.includes('return worklinksPartnerAccess()&&!!window.WorkLinksKimseFit;'));
});
