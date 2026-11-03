/* WorkLinks year-end quick-win ordering.
 * A ranking for investigation, NOT a win-probability estimate or eligibility ruling.
 * No user state, remote requests, external APIs, or application mutations.
 */
(function(root,factory){
  var api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root)root.WorkLinksQuickWin=api;
})(typeof window!=="undefined"?window:null,function(){
 "use strict";
 function str(v){return String(v==null?"":v)}
 function joined(x){return [x.title,x.money,x.support,x.condition,x.period,x.benefitType].map(str).join(" ")}
 function koreaDate(now){
   return new Date((now instanceof Date?now:new Date(now||Date.now())).getTime()+32400000).toISOString().slice(0,10);
 }
 function endDate(value){
   var v=str(value),m=v.match(/^(20\d{2})[.\/-](\d{1,2})[.\/-](\d{1,2})/);
   if(!m)return null;
   var day=m[1]+"-"+m[2].padStart(2,"0")+"-"+m[3].padStart(2,"0");
   var parsed=Date.parse(day+"T00:00:00Z");
   if(!Number.isFinite(parsed)||new Date(parsed).toISOString().slice(0,10)!==day)return null;
   return day;
 }
 function deadlineState(x,now){
   var day=endDate(x.deadline);
   if(!day)return "unverified";
   var v=str(x.deadline);
   var hh=v.match(/^20\d{2}[.\/-]\d{1,2}[.\/-]\d{1,2}[T ]+(\d{1,2}):(\d{2})/);
   if(hh){
     var offset=v.match(/(?:Z|[+-]\d{2}:?\d{2})$/);
     var dt=Date.parse(day+"T"+hh[1].padStart(2,"0")+":"+hh[2]+":00"+(offset?offset[0]:"+09:00"));
     if(Number.isFinite(dt))return dt<=new Date(now||Date.now()).getTime()?"expired":"active";
   }
   return day<koreaDate(now)?"expired":"active";
 }
 function verifiedCompetitionHint(x){
   // "1,000 winners", "extra recruitment" or "few residents" are NOT
   // evidence of fewer applications than available spaces.
   var v=str(x.competitionEvidence);
   return /(접수|모집|신청자|지원자)\s*(미달|부족)|잔여\s*(?:인원|선정\s*인원)|유찰/.test(v) &&
          !/(확인 불가|미확인|단정\s*불가)/.test(v);
 }
 function obstacles(x){
   var v=joined(x),c=str(x.condition),title=str(x.title);
   var relocation=/(?:전입|이주|주민등록\s*이전|사업장\s*주소.*등록|본점\s*(?:주소\s*)?이전|지역\s*사업자등록\s*필수|사업자등록.*(?:이전|센터|입주))/.test(c);
   var onSite=/(?:입주|임대|점포|사무실|공간|보육센터|공유주방|제조주방|운영주방|직접\s*영업|주\s*\d+일.*영업)/.test(title+" "+c);
   var cost=/(?:자부담\s*(?:\d|있|필수)|현금\s*자부담|보증금|관리비|입주부담|구매인증|영수증\s*제출.*구매)/.test(v);
   var trainingOnly=/(?:무료\s*교육|교육\s*프로그램|네트워킹|투자\s*상담|멘토링\s*위주)/.test(title+" "+str(x.money))&&!/(?:지원금|상품권|바우처|특허\s*출원)/.test(str(x.money));
   var sector=/(?:음식점|식품\s*제조|수소산업|트레일|해양|관광\s*예비창업|건설\s*PoC|크라우드펀딩\s*교육|농업\s*창업)/.test(title);
   return {relocation:relocation,onSite:onSite,cost:cost,trainingOnly:trainingOnly,sectorMismatch:sector};
 }
 function benefitKind(x){
   var m=str(x.money),b=str(x.benefitType),title=str(x.title);
   if(/상품권|기프티콘|경품|답례품|모바일\s*교환권/.test(b+" "+m))return "gift";
   if(/실비절감|비용\s*감면|수수료|IP디딤돌|특허\s*출원|무료\s*(?:시험|분석|API)|크레딧|안심존|바우처/.test(b+" "+title+" "+m))return "savings";
   if(/(?:현금|상금|시상금|포상금|활동비|사업화\s*지원금|지원금)/.test(m))return "cash";
   return "unverified";
 }
 function easyApplication(x){
   var t=str(x.title),s=str(x.support),c=str(x.condition);
   if(/(?:설문|만족도\s*조사|선호도\s*투표|투표\s*참여|한줄\s*제안|상품권\s*이벤트|온라인\s*설문)/.test(t))return true;
   if(/(?:폼\s*작성|간단\s*참여|신청서\s*1장|구글\s*폼|네이버\s*폼)/.test(s+" "+c))return true;
   return false;
 }
 function broadAudience(x){
   var v=joined(x);
   if(/(?:국민\s*누구나|일반\s*국민|전\s*국민|전국\s*누구나|누구나\s*참여|지역\s*제한\s*없음)/.test(v))return true;
   if(/(?:예비\s*창업자\s*신청\s*가능|서울\s*(?:거주|지역)\s*예비\s*창업자)/.test(v)&&!/(?:이전\s*필수|전입\s*필수)/.test(v))return true;
   return false;
 }
 function deadlineDays(x,now){
   var day=endDate(x.deadline);
   if(!day)return 9999;
   var a=Date.parse(day+"T00:00:00Z"),b=Date.parse(koreaDate(now)+"T00:00:00Z");
   return Math.round((a-b)/86400000);
 }
 function decision(x,now){
   var state=deadlineState(x,now),o=obstacles(x),kind=benefitKind(x);
   var waiting=!!x.suspendedHint||x.quickWinTier==="waiting_reopen";
   var hard= x.eligibility==="ineligible"||o.relocation||o.onSite||o.cost||o.sectorMismatch||o.trainingOnly;
   var easy=easyApplication(x),broad=broadAudience(x);
   var low=verifiedCompetitionHint(x);
   var hasBenefit=kind!=="unverified";
   var priority=6,label="추가 확인",reason="신청 조건·혜택 확인 필요";
   // Keep all notices visible. Expired, onerous or confirmed-ineligible ones
   // belong below the inexpensive, potentially actionable items.
   if(state==="expired"||x.eligibility==="ineligible"){
     priority=9;label="마감·대상 제외";reason=state==="expired"?"마감일 경과":"신청 대상 아님";
   }else if(hard){
     priority=8;label="부담·조건 큼";reason=o.relocation?"사업장·거주 이전 조건":o.onSite?"입주·현장 운영 조건":o.cost?"추가 지출·자부담 조건":o.sectorMismatch?"업종 부적합": "실익 불명확";
   }else if(waiting){
     priority=7;label="재개 감시";reason="현재 접수 중지·재개 확인 필요";
   }else if(state==="unverified"){
     priority=5;label="마감 확인";reason="신청 종료일 확인 전 추천 보류";
   }else if(low&&hasBenefit&&broad&&easy){
     priority=0;label="미달 단서·간편";reason="미달/잔여 단서 있음 · 공식 경쟁률 검증 필요";
   }else if(easy&&broad&&kind==="gift"){
     priority=1;label="소액·간편 참여";reason="참여 대상 넓음 · 추첨 당첨률은 미확인";
   }else if(broad&&hasBenefit&&kind==="savings"){
     priority=2;label="실비절감 검토";reason="현금 대신 실제 비용절감 가능성 확인";
   }else if(broad&&hasBenefit&&kind==="cash"){
     priority=3;label="현금성 검토";reason="신청 가능·소요시간 확인";
   }else if(easy&&hasBenefit){
     priority=4;label="간편·자격 확인";reason="참여 대상 또는 추첨 확률 미확인";
   }else if(hasBenefit){
     priority=4;label="혜택·자격 확인";reason="경쟁률 및 신청비용 확인 필요";
   }
   // 1,000 winners is not a known win rate. Use only as a last tie-breaker,
   // with no probability label, and never outrank confirmed lower competition.
   var winners = (str(x.money)+" "+str(x.support)).match(/(\d{1,3}(?:,\d{3})*|\d+)\s*명\s*(?:에게|추첨|선정)/);
   var winnerCount=winners?Math.min(5000,Number(winners[1].replace(/,/g,""))):0;
   return {priority:priority,label:label,reason:reason,benefit:kind,easy:easy,
     broad:broad,competitionHint:low,competitionVerified:false,
     deadlineStatus:state,days:deadlineDays(x,now),winnerCount:winnerCount};
 }
 function compare(a,b,now){
   var x=decision(a,now),y=decision(b,now);
   if(x.priority!==y.priority)return x.priority-y.priority;
   if(x.priority===1||x.priority===4){
     // More award recipients is a transparent count, never proven odds.
     if(x.winnerCount!==y.winnerCount)return y.winnerCount-x.winnerCount;
   }
   if(x.days!==y.days)return x.days-y.days;
   return str(a.id||a.title).localeCompare(str(b.id||b.title),"ko");
 }
 return {decision:decision,compare:compare,deadlineState:deadlineState,verifiedCompetitionHint:verifiedCompetitionHint};
});
