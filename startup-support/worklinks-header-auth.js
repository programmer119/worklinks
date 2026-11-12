import { AuthHubClient } from './authhub-client.js';

const PROJECT='p47';
const AUTH_API='https://api-authhub.suaveforge.com';
const CALLBACK='https://worklinks.suaveforge.com/startup-support/auth-callback.html';

export function worklinksHostedAuthUrl(mode='login'){
  const url=new URL('https://authhub.suaveforge.com/login/');
  url.searchParams.set('project',PROJECT);
  url.searchParams.set('environment','production');
  url.searchParams.set('redirect_uri',CALLBACK);
  url.searchParams.set('state','/startup-support/');
  url.searchParams.set('mode',mode);
  return url.href;
}
function element(tag,cls,label){
  const node=document.createElement(tag);
  if(cls)node.className=cls;
  if(label)node.textContent=label;
  return node;
}
export function renderWorklinksHeaderAuth({root,session=null,onLogout=null,onRecover=null}={}){
  if(!root)return;
  root.classList.add('worklinks-account-nav');
  root.setAttribute('aria-label','WorkLinks 계정');
  root.replaceChildren();
  if(!session){
    const login=element('a','worklinks-auth-button worklinks-auth-primary','로그인');
    login.href=worklinksHostedAuthUrl('login');
    const signup=element('a','worklinks-auth-button worklinks-auth-secondary','회원가입');
    signup.href=worklinksHostedAuthUrl('signup');
    root.append(login,signup);
    return;
  }
  const dropdown=element('details','worklinks-auth-dropdown');
  const summary=element('summary','worklinks-auth-summary','계정 ▾');
  summary.setAttribute('aria-label','로그인된 계정 메뉴 열기');
  const menu=element('div','worklinks-auth-popup');
  const email=element('div','worklinks-auth-user',session.email||'AuthHub 회원');
  email.title=session.email||'AuthHub 회원';
  menu.append(email);
  if(typeof onRecover==='function'){
    const recover=element('button','worklinks-auth-button','지원기록 점검');
    recover.type='button';
    recover.addEventListener('click',()=>{dropdown.open=false;onRecover()});
    menu.append(recover);
  }else{
    const list=element('a','worklinks-auth-button','지원내역 확인');
    list.href='./?view=support';
    menu.append(list);
  }
  const logout=element('button','worklinks-auth-button','로그아웃');
  logout.type='button';
  logout.addEventListener('click',async()=>{
    logout.disabled=true;
    try{if(onLogout)await onLogout()}
    finally{logout.disabled=false}
  });
  menu.append(logout);
  dropdown.append(summary,menu);
  root.append(dropdown);
  const closeOnOutside=(event)=>{
    if(!dropdown.isConnected){document.removeEventListener('click',closeOnOutside);return}
    if(!dropdown.contains(event.target))dropdown.open=false;
  };
  document.addEventListener('click',closeOnOutside);
}
async function verifySession(client){
  if(!client.session()?.accessToken)return null;
  try{
    let me;
    try{me=await client.me()}
    catch(error){
      if(error?.status!==401)throw error;
      await client.refresh();
      me=await client.me();
    }
    if(me?.membership?.status!=='active'||!me?.user?.id)return null;
    return {email:String(me.user.email||''),identity:String(me.user.id)};
  }catch{return null}
}
// Secondary read-only pages do not run the full saved-support-record sync module.
// The same AuthHub session is verified and displayed without changing account data.
export function initWorklinksStandaloneAuth(){
  const root=document.getElementById('worklinks-auth-header');
  if(!root)return;
  const client=new AuthHubClient({apiBase:AUTH_API,project:PROJECT,environment:'production'});
  const display=async()=>{
    const session=await verifySession(client);
    renderWorklinksHeaderAuth({root,session,onLogout:async()=>{
      try{await client.logout()}catch{}
      renderWorklinksHeaderAuth({root});
    }});
  };
  renderWorklinksHeaderAuth({root});
  display().catch(()=>{});
  window.addEventListener('storage',event=>{if(event.key===client.key)display().catch(()=>{})});
  window.addEventListener('focus',()=>display().catch(()=>{}));
}
if(document.getElementById('worklinks-auth-header')&&document.body.dataset.worklinksAccountModule!=='main'){
  initWorklinksStandaloneAuth();
}
