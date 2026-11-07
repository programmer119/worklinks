/* Read-only bridge from the verified investment opportunity snapshot to the
 * existing WorkLinks support list. No filter, ordering, account, or server writes.
 * Every imported row remains subject to ordinary D-DAY sorting and user choices.
 */
(function(root,factory){
  'use strict';
  var api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.WorkLinksKimseIntake=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  var MAX_SNAPSHOT_AGE_MS=48*60*60*1000;
  var SOURCE_OK=new Set(['서울 스타트업플러스 지원사업','도전의 IR 운영사별 프로그램','한국보건의료정보원 공식 공지','한국보건의료정보원 실증·사업 공고']);
  var DOMAIN_FIT=/(치매|경도\s*인지|인지\s*(?:기능|저하|건강|지원)|고령|시니어|실버테크|에이지테크|에이징테크|age[-\s]?tech|의료|헬스케어|디지털\s*헬스|보건의료|병원|임상|데이터안심|위치정보|AI[-\s]?허브|음성\s*(?:AI|바이오마커))/i;
  var PATIENT_ONLY=/(치매\s*(?:치료비|의료비)|환자\s*(?:본인부담|급여))/i;
  var SOURCE_URL=/^https:\/\/(?:www\.)?startup-plus\.kr\/project\/PRJ\d{5,9}$/i;
  var IR_URL='https://irchallenge.jointips.or.kr/apply';
  var KHIS_URL=/^https:\/\/www\.khis\.kr\/board\.es\?act=view&bid=000[19]&list_no=\d{1,8}&mid=a1030[14]000000$/i;
  function normalize(value){
    return String(value||'').normalize('NFKC').replace(/[^0-9a-zA-Z가-힣]/g,'').toLowerCase();
  }
  function deadlineFor(x,name){
    // Seoul BioHub's original registration closes Nov 16 at 23:57. The public
    // startup-plus listing currently conflates event start Nov 17 with deadline.
    if(name.includes('2026서울바이오의료오픈콜라보'))
      return '2026-11-16T23:57:00+09:00';
    return String(x.deadline||'');
  }
  function validDeadline(deadline,now){
    if(!/^\d{4}-\d\d-\d\d(?:T\d\d:\d\d:00\+09:00)?$/.test(deadline))return false;
    var day=new Date(now.getTime()+32400000).toISOString().slice(0,10);
    if(deadline.slice(0,10)<day)return false;
    var value=Date.parse(deadline.length===10?deadline+'T23:59:59+09:00':deadline);
    return Number.isFinite(value)&&value>=now.getTime();
  }
  function select(snapshot,known,clock){
    var now=clock instanceof Date?clock:new Date(clock||Date.now());
    if(!Number.isFinite(now.getTime())||!snapshot||!Array.isArray(snapshot.opportunities))return [];
    var generated=Date.parse(String(snapshot.generatedAt||''));
    if(!Number.isFinite(generated)||Math.abs(now.getTime()-generated)>MAX_SNAPSHOT_AGE_MS)return [];
    var knownTitles=new Set((Array.isArray(known)?known:[]).map(x=>normalize(x&&x.title)));
    var seen=new Set(),result=[];
    for(var x of snapshot.opportunities){
      if(!x||!x.id||!x.title||x.freshness!=='checked'||x.sourceStatus==='closed'||x.deadlineState==='closed')continue;
      if(!SOURCE_OK.has(x.source)||!DOMAIN_FIT.test(x.title)||PATIENT_ONLY.test(x.title))continue;
      var title=normalize(x.title);
      if(!title||knownTitles.has(title)||seen.has(title))continue;
      if(title.includes('위치정보맞춤형컨설팅')&&Array.from(knownTitles).some(t=>t.includes('위치정보맞춤형컨설팅')))continue;
      var deadline=deadlineFor(x,title);
      if(!validDeadline(deadline,now))continue;
      var url=String(x.url||'');
      if(!SOURCE_URL.test(url)&&url!==IR_URL&&!KHIS_URL.test(url))continue;
      seen.add(title);
      var ir=x.source==='도전의 IR 운영사별 프로그램';
      var special=title.includes('2026서울바이오의료오픈콜라보');
      var detail=String(x.description||'').slice(0,340);
      result.push({
        id:'sourced-'+String(x.id).replace(/[^a-zA-Z0-9-]/g,'').slice(0,85),
        category:'general',title:String(x.title).slice(0,180),url:url,deadline:deadline,
        period:ir?('공식 IR 회차 '+String(x.irDate||'').slice(0,10)+' · 신청마감 '+deadline+' (시각 미확인)'):(special?'공식 신청마감 2026.11.16 23:57 · 행사 11.17':'공식 공개목록 기준 마감 '+deadline+' · 상세 재확인'),
        support:(ir?'공식 TIPS 운영사 투자제안·1:1 IR 검토. ':'공식 스타트업플러스 모집공고. ')+detail,
        money:ir?'투자상담·피칭 기회 · 지분투자/TIPS/현금지원 보장 없음':'지원·참가 비용 및 실질 혜택은 공고 원문 확인 필요',
        eligibility:'unknown',
        condition:ir?'예비창업 가능 여부·운영사별 대상·남은 신청횟수 및 최종 마감 원문 확인 필요':(special?'서울바이오허브 공식 접수마감 11.16 23:57 확인. 참가비·참가대상은 공식 신청폼 확인.':'기관 상세 공고 원문에서 개인/예비창업자 자격·접수상태·일정 최종 확인 필요'),
        applied:false,source:'investment-opportunities.json'
      });
      if(result.length>=40)break;
    }
    return result;
  }
  return {select:select};
});
