'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const prebid=fs.readFileSync(path.join(root,'startup-support/changcom-prebid.js'),'utf8');
const html=fs.readFileSync(path.join(root,'startup-support/index.html'),'utf8');
new vm.Script(prebid);
for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))if(m[1].trim())new vm.Script(m[1]);
const head=prebid.slice(0,prebid.indexOf('const partnerAwardFilters'));
assert.ok(head.includes('history.replaceState'),'must recover shared URL before stage initialization');
function sample(search){
 const u=new URL('https://worklinks.suaveforge.com/startup-support/'+search);
 const loc={href:u.href,search:u.search};
 const input={value:''};let replaced=0;
 const history={state:{},replaceState:(_state,_title,relative)=>{
  const next=new URL(relative,loc.href);loc.href=next.href;loc.search=next.search;replaced++;
 }};
 const ctx={window:{location:loc},history,location:loc,URL,URLSearchParams,document:{getElementById:id=>id==='partnerNoticeStage'?input:null}};
 vm.createContext(ctx);vm.runInContext(head,ctx);
 return {url:new URL(loc.href),replaced,stage:vm.runInContext('partnerNoticeStage',ctx),selected:input.value};
}
for(const [input,expect] of [
 ['?view=jobs&open=R26BD00301798',{view:'changcom',stage:'prespec',q:'R26BD00301798',replaced:1}],
 ['?view=jobs&open=R26BK01843011',{view:'changcom',stage:'bid',q:'R26BK01843011',replaced:1}],
 ['?view=jobs&open=R26BD00301798&utm_source=test',{view:'changcom',stage:'prespec',q:'R26BD00301798',replaced:1,utm:'test'}],
 ['?view=changcom&stage=prespec&q=R26BD00301798&open=R26BD00301798',{view:'changcom',stage:'prespec',q:'R26BD00301798',replaced:0}],
 ['?view=jobs&q=R26BK01843011',{view:'jobs',q:'R26BK01843011',replaced:0}],
 ['?view=jobs&open=bad-notice',{view:'jobs',replaced:0}]
]){
 const v=sample(input);
 assert.equal(v.url.searchParams.get('view'),expect.view,input);
 if(expect.stage)assert.equal(v.url.searchParams.get('stage'),expect.stage,input);
 if(expect.q)assert.equal(v.url.searchParams.get('q'),expect.q,input);
 if(expect.utm)assert.equal(v.url.searchParams.get('utm_source'),expect.utm,input);
 assert.equal(v.replaced,expect.replaced,input);
 if(expect.stage){assert.equal(v.stage,expect.stage,input);assert.equal(v.selected,expect.stage,input)}
}
const from=html.indexOf('function setWorkspaceView(view){');
const until=html.indexOf(' const target=document.getElementById(',from);
assert.ok(from>=0&&until>from);
const signature=html.slice(from,until);
const standalone=signature+' return {view,deferredPartnerRoute,pendingSharedNotice,requestedPartnerViewOnAuth};}';
for(const [view,authenticated,open,expected] of [
 ['changcom',false,'R26BD00301798',{view:'jobs',deferred:true,pending:true,requested:true}],
 ['jobs',false,'R26BD00301798',{view:'jobs',deferred:false,pending:true,requested:false}],
 ['jobs',false,'',{view:'jobs',deferred:false,pending:false,requested:false}],
 ['changcom',true,'R26BD00301798',{view:'changcom',deferred:false,pending:false,requested:false}]
]){
 const ctx={location:{search:open?'?open='+open:''},URLSearchParams,requestedPartnerViewOnAuth:false,worklinksPartnerAccess:()=>authenticated};
 vm.createContext(ctx);vm.runInContext(standalone,ctx);
 const result=vm.runInContext("setWorkspaceView("+JSON.stringify(view)+")",ctx);
 assert.deepEqual(JSON.parse(JSON.stringify(result)),{
  view:expected.view,deferredPartnerRoute:expected.deferred,
  pendingSharedNotice:expected.pending,requestedPartnerViewOnAuth:expected.requested
 });
}
assert.ok(html.includes('if(changed&&!deferredPartnerRoute&&!pendingSharedNotice){'));
assert.ok(html.includes('requestedPartnerViewOnAuth=false;\n  setWorkspaceView(\'changcom\');'),
 'only AuthHub grant restores the confidential workspace');
assert.ok(html.includes('./changcom-prebid.js?v=20261121-g2b-source-realname-v1'));
assert.ok(html.includes("if(!worklinksSharePendingId||!worklinksPartnerAccess()||!worklinksIsChangcomView())return;"),
 'shared notice may never bypass membership validation');
console.log('WORKLINK_AUTH_FAILCLOSED_SHARED_DEEPLINK=PASS');
