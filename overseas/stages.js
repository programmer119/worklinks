/* Official notice codes, not procurement title keyword guesses. */
(function(root){
"use strict";
const groups=[["all","전체"],["bid","일반공고"],["consult","사전규격·시장협의"],["plan","발주준비"],["award","낙찰·계약"],["direct","수의계약 예고"],["other","기타·미분류"]];
const names=Object.fromEntries(groups);
function classify(r){
 const type=String(r.noticeType||"").trim().toLowerCase(), raw=String(r.stage||"").trim().toLowerCase();
 if(r.source==="uk"){
  if(["uk1","uk3","f01","f04","f16","f21","f22"].includes(type))return "plan";
  if(type==="uk2")return "consult";
  if(["uk4","f02","f05","f17","f24","f25"].includes(type))return "bid";
  if(["uk5","f15"].includes(type))return "direct";
  if(["uk6","uk7","uk8","uk9","uk10","uk11","uk17","f03","f06","f18","f20"].includes(type))return "award";
  if(type)return "other";
  const tags=raw.split(/\s*\|\s*/);
  if(tags.some(t=>["tendercancellation","tenderwithdrawal"].includes(t)))return "other";
  if(tags.some(t=>["award","awardupdate","contract","contractupdate","contractamendment","contracttermination"].includes(t)))return "award";
  if(tags.some(t=>["tender","tenderupdate"].includes(t)))return "bid";
  // UK2 and UK3 share planning/planningUpdate, so no guess.
  return "other";
 }
 if(r.source==="eu"){
  const t=type||raw;
  if(t==="pmc")return "consult";
  if(["pin-buyer","pin-only","pin-rtl"].includes(t))return "plan";
  if(t.startsWith("cn-")||["pin-cfc","pin-cfc-standard","pin-cfc-social","qu-sy","subco","cei"].includes(t))return "bid";
  if(t==="veat")return "direct";
  if(t.startsWith("can-")||t==="compl")return "award";
  return "other";
 }
 if(r.source==="ca"){
  const t=raw.replace(/\s+/g," ");
  if(/^(?:request for information|request for information \(rfi\)|rfi|market sounding|industry consultation|draft request for proposal[s]?|draft rfp)$/.test(t))return "consult";
  if(/^(?:notice of proposed procurement|advance procurement notice|planned procurement|future procurement|procurement plan|notice of upcoming procurement|notice of intended procurement)$/.test(t))return "plan";
  if(/^(?:advance contract award notice(?: \(acan\))?|acan|notice of intent to award|notice of intent)$/.test(t))return "direct";
  if(/^(?:contract award(?: notice)?|award notice|contract history|contract award results)$/.test(t))return "award";
  if(/^(?:request for proposal[s]?(?: \(rfp\))?|rfp|invitation to tender(?: \(itt\))?|itt|request for quotation[s]?(?: \(rfq\))?|rfq|request for standing offer[s]?|request for supply arrangement[s]?|request for qualification[s]?|notice of tender|tender notice|request for bid[s]?|invitation to bid|competitive bid)$/.test(t))return "bid";
  // CanadaBuys sometimes omits notice type; explicit title markers can
  // indicate a candidate stage, but never use generic words or deadlines.
  if(!t){
    const title=String(r.title||"");
    if(/\b(?:request for information|RFI)\b/i.test(title))return "consult";
    if(/\b(?:advance contract award notice|ACAN)\b/i.test(title))return "direct";
    if(/\b(?:request for proposals?|RFP|invitation to tender|ITT|request for quotations?|RFQ)\b/i.test(title))return "bid";
  }
 }
 return "other";
}
function counts(rows){const out=Object.fromEntries(groups.map(([k])=>[k,0]));out.all=rows.length;for(const r of rows)out[classify(r)]++;return out}
const api={groups,names,classify,counts};
if(typeof module==="object"&&module.exports)module.exports=api;else root.OverseasStage=api;
})(typeof globalThis==="object"?globalThis:this);
