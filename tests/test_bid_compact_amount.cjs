// Validate the production card formatter without changing detail/contract values.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const begin=src.indexOf('function jobAmountLabel(raw){');
const end=src.indexOf('function extractBudget(s){',begin);
assert.ok(begin>0&&end>begin,'budget formatter source exists');
const helpers=new Function('htmlEscape',
 src.slice(begin,end)+'\nreturn {jobAmountLabel,jobCardCompactBudget,jobCardAmountMarkup};'
)(x=>String(x));
const {jobAmountLabel,jobCardCompactBudget,jobCardAmountMarkup}=helpers;
for(const [input,expected] of [
 ['185990000','1.8억'],
 ['1억 8,599만원','1.8억'],
 ['1500000000','15억'],
 ['1520000000','15.2억'],
 ['15억 2,000만원','15.2억'],
 ['199999999','1.9억'],
 ['1599999999','15.9억'],
 ['100000000','1억']
]) {
 assert.equal(jobCardCompactBudget(input),expected,input);
 assert.equal(jobCardAmountMarkup({id:'g2b-'+input,amount:input}),expected,input);
}
assert.equal(jobCardCompactBudget('99900000'),jobAmountLabel('99900000'),
 'sub-1억 amounts keep existing display');
assert.equal(jobCardAmountMarkup({id:'external-job',amount:'월 670만원'}),'월 670만원',
 'monthly wages are not treated as bid amounts');
assert.equal(jobAmountLabel('185990000'),'1억 8,599만원',
 'details and the tooltip retain the exact budget');
assert.ok(src.includes('title="\'+htmlEscape(jobAmountLabel(x.amount))+\'"'),
 'card tooltip must preserve full original budget');
console.log('WORKLINKS_COMPACT_BID_AMOUNT=PASS');
