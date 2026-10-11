#!/usr/bin/env python3
# WorkLinks yearly repeat and awarded-vendor background enrichment.
# Only confirmed same agency + sufficiently similar named project are marked verified.
import datetime as dt,difflib,json,os,re,sqlite3,time,urllib.parse,urllib.request,random
DB=os.environ.get('G2B_DB_PATH','/app/data/bids.sqlite3')
KEY=os.environ.get('G2B_SECRET_PATH','/run/secrets/g2b.env')
ENDPOINT='https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
AWARD='https://apis.data.go.kr/1230000/as/ScsbidInfoService/getScsbidListSttusServc'
DELAY=float(os.environ.get('HISTORY_DELAY_SECONDS','0.5'))
KEYWORDS=re.compile(r'유지.?관리|유지.?보수|운영.?관리|운영.?유지|통합.?관리|정기.?유지',re.I)
RE_YEAR=re.compile(r'(?:20\d{2}\s*년?도?|[()（）]\s*(?:재공고|긴급|취소|변경)\s*[()（）])')
NOISE=re.compile(r'[\s·ㆍ_()\[\]{}【】<>,"\'/\\\-:.]+')
DATE=dt.datetime.utcnow().isoformat()+'Z'
def api_key():
 with open(KEY,encoding='utf-8') as f:
  for row in f:
   if row.startswith('G2B_SERVICE_KEY='):return row.split('=',1)[1].strip()
 raise RuntimeError('key_not_found')
def norm(s):
 s=RE_YEAR.sub('',str(s or ''))
 s=re.sub(r'재공고|긴급공고|입찰공고|변경공고|정정공고','',s)
 return NOISE.sub('',s).lower()
def agency(a):
 return NOISE.sub('',str(a or '')).lower()
def confidence(a,b):
 return difflib.SequenceMatcher(None,norm(a),norm(b)).ratio()
def request(op,key,params):
 args={'serviceKey':key,'pageNo':1,'numOfRows':100,'type':'json'}
 args.update(params)
 u=op+'?'+urllib.parse.urlencode(args)
 for trial in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers={'Accept':'application/json'}),timeout=18) as r:
    obj=json.loads(r.read().decode('utf8'))
   head=obj.get('response',{}).get('header',{})
   if str(head.get('resultCode')) not in ('00','0'):raise RuntimeError('upstream_result_'+str(head.get('resultCode')))
   body=obj['response'].get('body',{})
   data=body.get('items') or []
   if isinstance(data,dict):data=data.get('item') or []
   if not isinstance(data,list):data=[data]
   time.sleep(DELAY)
   return data,int(body.get('totalCount') or 0)
  except Exception as e:
   if trial==2:raise RuntimeError('request_failed_'+type(e).__name__)
   time.sleep(1+trial)
def search_year(key,term,year):
 results=[]
 for mo in range(1,13):
  end=(dt.date(year+1,1,1)-dt.timedelta(days=1)) if mo==12 else (dt.date(year,mo+1,1)-dt.timedelta(days=1))
  frm=f'{year}{mo:02d}010000';to=end.strftime('%Y%m%d')+'2359'
  base={'inqryDiv':1,'inqryBgnDt':frm,'inqryEndDt':to,'bidNtceNm':term}
  first,total=request(ENDPOINT,key,base)
  if total>300:raise RuntimeError('overbroad_history_search')
  results+=first
  for page in range(2,(total+99)//100+1):
   rest,_=request(ENDPOINT,key,{**base,'pageNo':page});results+=rest
 return results
def match(cur,cand):
 if agency(cur.get('agency') or cur.get('org'))!=agency(cand.get('dminsttNm') or cand.get('ntceInsttNm')):return False
 if not norm(cur.get('title')) or not norm(cand.get('bidNtceNm')):return False
 return confidence(cur['title'],cand['bidNtceNm'])>=0.79
def lookup_winner(key,notice):
 try:
  data,total=request(AWARD,key,{'inqryDiv':4,'bidNtceNo':notice})
  matches=[x for x in data if str(x.get('bidNtceNo') or '')==notice]
  if not matches:return None
  m=next((x for x in matches if x.get('bidwinnrNm')),None)
  return str(m.get('bidwinnrNm')) if m else None
 except Exception:return None
def get_term(s):
 s=RE_YEAR.sub('',s)
 s=re.sub(r'\((재공고|긴급)\)|\[재공고\]','',s).strip()
 terms=re.findall(r'[가-힣A-Za-z0-9]{2,}',s)
 significant=[x for x in terms if len(x)>2 and x not in ('유지보수','유지관리','통합운영','용역','사업','운영')]
 term=' '.join(significant[:3])
 return term[:45] if len(term)>3 else None
def init(db):
 db.execute('PRAGMA busy_timeout=30000')
 db.execute('CREATE TABLE IF NOT EXISTS recurring_projects (kind TEXT NOT NULL,bid_no TEXT NOT NULL,history_json TEXT NOT NULL,repeat_years INTEGER NOT NULL,checked_at TEXT NOT NULL,error TEXT,PRIMARY KEY(kind,bid_no))')
 db.commit()
def work(db,key,item):
 kind,no,raw=item
 cur=json.loads(raw)
 year=int(str(cur.get('posted') or '')[:4] or dt.datetime.now().year)
 if not (2024<=year<=2030):year=dt.datetime.now().year
 label=str(cur.get('title') or '')
 term=get_term(label)
 hist=[{'year':year,'title':label,'awardee':None,'noticeUrl':cur.get('url') or '', 'verified':True}]
 if not term:return hist,0
 for y in range(year-1,max(year-4,2022),-1):
  found={}
  for p in search_year(key,term,y):
   no2=str(p.get('bidNtceNo') or '')
   if no2 and match(cur,p):
    found[no2]=p
  if found:
   p=max(found.values(),key=lambda x:str(x.get('bidNtceDt') or ''))
   no2=str(p.get('bidNtceNo') or '')
   winner=lookup_winner(key,no2)
   hist.append({'year':y,'title':p.get('bidNtceNm') or label,'noticeUrl':p.get('bidNtceDtlUrl') or 'https://www.g2b.go.kr/','bidNo':no2,'awardee':winner,'verified':True})
 seq=1
 for i in range(1,len(hist)):
  if int(hist[i-1]['year'])-int(hist[i]['year'])==1:seq+=1
  else:break
 return hist,seq if seq>=2 else 0
def main():
 key=api_key()
 db=sqlite3.connect(DB,timeout=30)
 init(db)
 while True:
  try:
   # Active/uncertain maintenance notice candidates first. Re-probe after 14 days.
   rows=db.execute("""SELECT b.kind,b.bid_no,b.payload FROM bid_notices b
     LEFT JOIN recurring_projects r ON r.kind=b.kind AND r.bid_no=b.bid_no
     WHERE b.kind='servc' AND b.sw_candidate=1
      AND (r.checked_at IS NULL OR r.checked_at < ?)
     ORDER BY CASE WHEN b.payload LIKE '%유지관리%' OR b.payload LIKE '%유지보수%' THEN 0 ELSE 1 END,
       b.last_seen DESC LIMIT 10""",
     ((dt.datetime.utcnow()-dt.timedelta(days=14)).isoformat()+'Z',)).fetchall()
   if not rows:
    print('HISTORY_IDLE',flush=True);time.sleep(3600);continue
   for item in rows:
    no=item[1]
    try:
     title=json.loads(item[2]).get('title') or ''
     if not KEYWORDS.search(title):
      hist=[];years=0
     else:hist,years=work(db,key,item)
     with db:db.execute('INSERT OR REPLACE INTO recurring_projects(kind,bid_no,history_json,repeat_years,checked_at,error) VALUES(?,?,?,?,?,NULL)',
      (item[0],no,json.dumps(hist,ensure_ascii=False),years,dt.datetime.utcnow().isoformat()+'Z'))
     print('HISTORY_DONE',no,'years',years,'records',len(hist),flush=True)
    except Exception as e:
     with db:db.execute('INSERT OR REPLACE INTO recurring_projects(kind,bid_no,history_json,repeat_years,checked_at,error) VALUES(?,?,?,?,?,?)',
      (item[0],no,'[]',0,dt.datetime.utcnow().isoformat()+'Z',type(e).__name__))
     print('HISTORY_ERR',no,type(e).__name__,flush=True)
    time.sleep(0.5)
  except Exception as e:
   print('HISTORY_CYCLE_ERR',type(e).__name__,flush=True);time.sleep(90)
if __name__=='__main__':main()
