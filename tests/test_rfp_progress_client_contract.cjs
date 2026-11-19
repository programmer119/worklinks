const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../startup-support/index.html'),'utf8');
const start=html.indexOf('function rfpProgressTotalsConsistent(counts){');
const end=html.indexOf('\n}',start)+2;
assert.ok(start>=0&&end>start,'RFP client progress count validator must exist');
const check=new Function(html.slice(start,end)+';return rfpProgressTotalsConsistent;')();
const real={total:2347,eligible:2295,excluded:52,completed:2051,remaining:244,
  legacy:0,rescanRequired:0};
assert.equal(check(real),true,'production counts with 52 excluded must pass');
assert.equal(check({...real,excluded:0}),false,'excluded cannot be silently lost');
assert.equal(check({...real,eligible:2347}),false,'eligible count must exclude 52');
assert.equal(check({...real,remaining:245}),false,'bad scan remaining count must fail');
assert.equal(check({...real,completed:2052}),false,'completed count cannot exceed actual');
assert.equal(check({...real,rescanRequired:1}),false,'legacy rescan mismatch must fail');
assert.equal(check({...real,total:NaN}),false,'NaN cannot bypass count validation');
assert.equal(check({...real,excluded:-1}),false,'negative counts are rejected');
assert.equal(check({...real,excluded:'52'}),false,'numeric strings cannot bypass contract');
assert.equal(check(null),false,'missing totals must fail');
const withoutExclusions={total:100,eligible:100,excluded:0,completed:85,
 remaining:15,legacy:2,rescanRequired:2};
assert.equal(check(withoutExclusions),true,'no-exclusions cohort must still pass');
const protectedSources={total:2200,eligible:2179,excluded:18,sourceRestricted:3,
 completed:2178,remaining:1,legacy:0,rescanRequired:0};
assert.equal(check(protectedSources),true,'source holds separately counted');
assert.equal(check({...protectedSources,sourceRestricted:0}),false,'cannot hide protected originals');
assert.equal(check({...protectedSources,eligible:2182}),false,'protected originals not scan work');
assert.equal(check({...protectedSources,completed:2181}),false,'protected originals never fake successes');
assert.equal(check({...protectedSources,sourceRestricted:-1}),false,'negative source holds invalid');
// New response retains schema-v1 total=eligible+excluded so an already-open
// browser can keep polling; protected holds remain an explicit subcategory.
const liveCompatible={total:2041,eligible:2022,excluded:19,
 excludedNoAttachments:16,sourceRestricted:3,completed:2022,remaining:0,
 legacy:0,rescanRequired:0};
assert.equal(check(liveCompatible),true,'schema-v1 compatible protected source split passes');
assert.equal(liveCompatible.total,liveCompatible.eligible+liveCompatible.excluded,
 'legacy live-tab validation must accept a freshly deployed API');
assert.equal(check({...liveCompatible,excluded:16}),false,'protected holds must remain accounted');
assert.equal(check({...liveCompatible,sourceRestricted:0}),false,'protected breakdown must be consistent');
assert.equal(check({...liveCompatible,excludedNoAttachments:-1}),false,'invalid excluded breakdown fails');
assert.equal(check({...liveCompatible,excludedNoAttachments:19}),false,'cannot relabel protected files as empty');

assert.ok(html.includes("!rfpProgressTotalsConsistent(report?.counts)"),
 'progress fetch must use the tested validator');
assert.ok(!html.includes('report.counts.total!==report.counts.completed+report.counts.remaining'),
 'obsolete totals validation must never reject valid exclusion cohorts');
console.log('WORKLINKS_RFP_PROGRESS_EXCLUSION_CLIENT_CONTRACT=PASS');
