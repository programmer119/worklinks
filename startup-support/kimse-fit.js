/* WorkLinks: lightweight KIMSE domain match hints, never eligibility or application advice.
 * Authentication and display are enforced by the WorkLinks page, not this classifier.
 */
(function(root,factory){
  var api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.WorkLinksKimseFit=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  var DIRECT_TITLE=/(치매|경도\s*인지|인지\s*(?:저하|건강|기능|지원|검사|훈련|재활)|고령|노인|실버테크|에이지테크|age[\s-]?tech|헬스케어|헬스\s*케어|디지털[\s-]?헬스|digital[\s-]?health|의료|의학|병원|임상|바이오마커|돌봄|장기요양|IRB|건강\s*데이터|보건의료|안심존)/i;
  var RELATED_TITLE=/(위치정보|\bLBS\b|\bGPS\b|음성|\bvoice\b|\bspeech\b|사회보장|보건복지|복지\s*데이터|생활\s*데이터|행동\s*데이터|헬스\s*데이터|AI[\s-]?허브|AI[\s-]?HUB|데이터\s*바우처|공공\s*데이터\s*활용)/i;
  var SUPPORT_HINT=/(치매|경도\s*인지|헬스케어|디지털[\s-]?헬스|의료\s*AI|의료\s*데이터|병원\s*연계|고령자|인지\s*기능|바이오마커)/i;
  function clean(value){return String(value==null?'':value).normalize('NFKC');}
  function assess(notice){
    if(!notice||typeof notice!=='object')return 'none';
    var title=clean(notice.title),support=clean(notice.support);
    if(DIRECT_TITLE.test(title))return 'direct';
    if(RELATED_TITLE.test(title)||SUPPORT_HINT.test(support))return 'related';
    return 'none';
  }
  return {assess:assess};
});
