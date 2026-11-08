'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const {select}=require('../startup-support/kimse-intake.js');
const now=new Date('2026-11-07T15:31:00+09:00');
function notice(id,title,deadline,overrides={}){
  return {
    id,title,deadline,url:'https://www.startup-plus.kr/project/PRJ007655',
    source:'서울 스타트업플러스 지원사업',freshness:'checked',
    deadlineState:'open_by_date',description:'공공 모집원문 검증 필요',...overrides
  };
}
function snap(...opportunities){
  return {generatedAt:'2026-11-07T15:17:33+09:00',opportunities};
}
test('accept future verified official KIMSE-domain opportunities with cautious eligibility',()=>{
  const a=select(snap(notice('h1','의료 AI 데이터 실증기업 모집','2026-11-20')),[],now);
  assert.equal(a.length,1);
  assert.equal(a[0].eligibility,'unknown');
  assert.equal(a[0].deadline,'2026-11-20');
  assert.match(a[0].condition,/원문/);
  assert.equal(a[0].category,'general');
});
test('never bring old or already closed sessions back',()=>{
  const a=select(snap(
    notice('old','헬스케어 기업 10월 교육','2026-10-21'),
    notice('closed','치매 돌봄 실증 모집','2026-11-19',{deadlineState:'closed'}),
    notice('sourceclosed','음성 바이오마커 데이터','2026-11-19',{sourceStatus:'closed'})
  ),[],now);
  assert.equal(a.length,0);
});
test('unknown deadline and stale source cannot outrank live D-DAY results',()=>{
  const a=select(snap(
    notice('unknown','의료 AI 실증 모집',null),
    notice('stale','의료 AI 데이터 모집','2026-11-22',{freshness:'stale'})
  ),[],now);
  assert.equal(a.length,0);
});
test('do not import unrelated medical patient subsidies',()=>{
  assert.equal(select(snap(notice('patient','치매 치료비 환급 신청','2026-11-20')),[],now).length,0);
});
test('do not import external or fabricated detail links',()=>{
  assert.equal(select(snap(notice('bad','의료 AI 협업 모집','2026-11-20',{url:'https://untrusted.example.com/view'})),[],now).length,0);
});
test('do not duplicate registered notices or a second copy in the same snapshot',()=>{
  const n=notice('one','헬스케어 AI 실증','2026-11-20');
  assert.equal(select(snap(n,n),[],now).length,1);
  assert.equal(select(snap(n),[{title:n.title}],now).length,0);
});
test('same ongoing KISA consulting under different title does not become another record',()=>{
  const n=notice('kisa','2026 위치정보 맞춤형 컨설팅 참여기업 모집(상시)','2026-12-31');
  assert.equal(select(snap(n),[{title:'2026 위치정보 맞춤형 컨설팅 참여기업 모집'}],now).length,0);
});
test('correct the verified Seoul BioHub registration deadline, not its event start',()=>{
  const n=notice('bio','2026 서울 바이오∙의료 오픈 콜라보','2026-11-17T10:00:00+09:00');
  const a=select(snap(n),[],now);
  assert.equal(a.length,1);
  assert.equal(a[0].deadline,'2026-11-16T23:57:00+09:00');
});
test('include independent IR slots without silently asserting investor funding',()=>{
  const n=notice('ir','디지털헬스케어파트너스 — DHP IR Day (2026-11-19)','2026-11-12',
    {url:'https://irchallenge.jointips.or.kr/apply',source:'도전의 IR 운영사별 프로그램',irDate:'2026-11-19'});
  const a=select(snap(n),[],now);
  assert.equal(a.length,1);
  assert.match(a[0].money,/보장 없음/);
  assert.match(a[0].period,/11-19/);
});
test('K-DATA verified official detail URL is importable but a fake domain is not',()=>{
  const base=notice('kdata','2026 데이터안심구역 의료 연구용 데이터 활용 지원','2026-11-20',
    {source:'K-DATA 데이터·안심구역 공지',
     url:'https://www.kdata.or.kr/kr/board/notice_01/boardView.do?bbsIdx=123456'});
  const good=select(snap(base),[],now);
  assert.equal(good.length,1);
  assert.equal(good[0].eligibility,'unknown');
  const bad=select(snap({...base,id:'evil',
    url:'https://other.example.kr/kr/board/notice_01/boardView.do?bbsIdx=123456'}),[],now);
  assert.equal(bad.length,0);
});
test('refuse stale snapshots instead of claiming no opportunities',()=>{
  assert.equal(select({generatedAt:'2026-10-01T15:17:33+09:00',opportunities:[notice('old','의료 실증','2026-11-20')]},[],now).length,0);
});
test('do not mutate original records, existing user choices, or sorting state',()=>{
  const n=notice('one','의료 AI 데이터 지원','2026-11-20');
  const x=snap(n),before=JSON.stringify(x),known=[{title:'기존 공고',applied:true}],old=JSON.stringify(known);
  select(x,known,now);
  assert.equal(JSON.stringify(x),before);
  assert.equal(JSON.stringify(known),old);
});
