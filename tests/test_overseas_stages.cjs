const assert=require("node:assert/strict");
const S=require("../overseas/stages.js");
const cases=[
["uk","planning","UK2","consult"],["uk","planning","UK3","plan"],["uk","planning","","other"],["uk","tender","UK4","bid"],["uk","award | contract","UK5","direct"],["uk","award | contract","UK6","award"],["uk","tenderCancellation","UK12","other"],
["eu","pmc","","consult"],["eu","pin-only","","plan"],["eu","pin-rtl","","plan"],["eu","pin-cfc-standard","","bid"],["eu","cn-standard","","bid"],["eu","can-standard","","award"],["eu","veat","","direct"],["eu","compl","","award"],["eu","unknown","","other"],
["ca","Request for Information","","consult"],["ca","Notice of Proposed Procurement","","plan"],["ca","Request for Proposal","","bid"],["ca","Advance Contract Award Notice","","direct"],["ca","Contract Award Notice","","award"],["ca","","","other"]
];
const rows=cases.map(([source,stage,noticeType,expected])=>{const r={source,stage,noticeType};assert.equal(S.classify(r),expected,JSON.stringify(r));return r});
assert.equal(S.classify({source:"ca",title:"RFI – Software development"}),"consult");
assert.equal(S.classify({source:"ca",title:"Software development",deadline:"2027-01-01"}),"other");
const counts=S.counts(rows);assert.equal(counts.all,rows.length);assert.equal(Object.entries(counts).filter(([k])=>k!=="all").reduce((n,[,v])=>n+v,0),rows.length);
console.log("OVERSEAS_STAGE_REGRESSION_PASS",cases.length+3,JSON.stringify(counts));
