/* Pure quick-win rank regression; must never claim unknown odds are low. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Q = require('../startup-support/quickwin-ranking.js');
const NOW = new Date('2026-11-04T00:00:00+09:00');
const base = {
  id: 'sample', title: '전국 누구나 간단 설문조사 이벤트',
  deadline: '2026-11-10', money: '1만원 기프티콘 1,000명 추첨',
  condition: '일반 국민 참여 가능, 구매 의무 없음',
  support: '온라인 설문조사 참여', benefitType: '상품권·참여보상',
  eligibility: 'unknown', competitionEvidence: '당첨자 1,000명 공지(응모자 수 미확인)'
};
function x(extra){return {...base,...extra};}
test('1,000 prizes is not evidence of low competition',()=>{
  assert.equal(Q.verifiedCompetitionHint(base),false);
  const d=Q.decision(base,NOW);
  assert.equal(d.priority,1);
  assert.equal(d.competitionVerified,false);
  assert.match(d.reason,/미확인/);
});
test('documented recruitment shortage is prioritized above an unknown-odds lottery',()=>{
  const scarce=x({id:'shortage',competitionEvidence:'공식 공고: 접수 미달',money:'포상금 5만원'});
  assert.equal(Q.decision(scarce,NOW).priority,0);
  assert.ok(Q.compare(scarce,base,NOW)<0);
});
test('ranking never assumes odds from a large cash prize',()=>{
  const huge=x({id:'huge',title:'군 소재 기업 사업화 7,000만원',money:'사업화 지원금 최대 7,000만원',condition:'지역 사업자등록 필수, 전입 후 점포 입주 필요',benefitType:'상금·활동비·현금'});
  assert.equal(Q.decision(huge,NOW).priority,8);
  assert.ok(Q.compare(base,huge,NOW)<0);
});
test('suspended patent relief stays below active simple opportunities',()=>{
  const stopped=x({id:'ip',title:'서울 IP디딤돌 특허출원',deadline:'',money:'특허출원 수수료 최대 170만원',
    suspendedHint:true,quickWinTier:'waiting_reopen',benefitType:'실비절감·서비스'});
  assert.equal(Q.decision(stopped,NOW).priority,7);
});
test('declared exact time closes but date-only lasts through its day',()=>{
  assert.equal(Q.deadlineState(x({deadline:'2026-11-03'}),NOW),'expired');
  assert.equal(Q.deadlineState(x({deadline:'2026-11-04'}),NOW),'active');
  assert.equal(Q.deadlineState(x({deadline:'2026-11-03T23:59:00+09:00'}),NOW),'expired');
  assert.equal(Q.deadlineState(x({deadline:'미확인'}),NOW),'unverified');
});
test('no deadline is not mistaken for an open announcement',()=>{
  const unk=x({deadline:'',id:'unknown'});
  assert.equal(Q.decision(unk,NOW).priority,5);
  assert.ok(Q.compare(base,unk,NOW)<0);
});
test('eligibility unknown is not shown as approved, confirmed ineligible stays last',()=>{
  assert.equal(Q.decision(base,NOW).competitionVerified,false);
  const ban=x({eligibility:'ineligible'});
  assert.equal(Q.decision(ban,NOW).priority,9);
});
test('lightly qualified 20-person draw is still not a validated win rate',()=>{
  const small=x({money:'상품권 2만원, 20명 추첨',id:'20'});
  assert.equal(Q.decision(small,NOW).priority,1);
  assert.equal(Q.decision(small,NOW).competitionHint,false);
  assert.ok(Q.compare(base,small,NOW)<0);
});
test('only low competition evidence gives the low-competition class',()=>{
  const reannounce=x({id:'reannounce',title:'지역 사업 추가모집 간편 설문',competitionEvidence:'재공고만 확인, 경쟁률 미확인'});
  assert.equal(Q.verifiedCompetitionHint(reannounce),false);
});
test('existing page integrates the ordering without changing applied or search history',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
  assert.match(html,/quickwin-ranking\.js/);
  assert.match(html,/window\.WorkLinksQuickWin\.compare/);
  assert.match(html,/function quickWinHintHtml/);
  assert.match(html,/if\(supportSearchText\.trim\(\)\)/);
  assert.match(html,/if\(filter==="applied"\)/);
  const m=html.match(/^var items=(.*);$/m);
  assert.ok(m,'registered items array');
  const items=JSON.parse(m[1]);
  const kto=items.find(i=>i.id==='kto-data-lab-survey-20261110');
  assert.ok(kto);
  assert.equal(kto.deadline,'2026-11-10');
  assert.equal(Q.verifiedCompetitionHint(kto),false);
  const local=items.filter(i=>i.monitorTrack==='yearEndLocalBudget');
  assert.ok(local.length>=18);
  const ranked=[...local].sort((a,b)=>Q.compare(a,b,NOW));
  assert.ok(ranked.length>0);
  assert.ok(Q.decision(ranked[0],NOW).priority<8);
  assert.ok(ranked.findIndex(i=>i.id===kto.id)<ranked.findIndex(i=>/창업보육센터.*입주/.test(i.title)));
});
test('collected snapshot and latest registered items preserve unscreened candidates',()=>{
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../startup-support/year-end-local-budget.json'),'utf8'));
  for(const candidate of data.opportunities){
    assert.ok(typeof Q.decision(candidate,NOW).priority==='number');
    assert.ok(candidate.competitionLevel==='unknown' || candidate.competitionLevel===undefined);
  }
});
