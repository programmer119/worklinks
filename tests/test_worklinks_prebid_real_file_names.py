#!/usr/bin/env python3
"""No-network regression: filename must come from verified G2B GET headers."""
import os,runpy,sqlite3,json,tempfile
from urllib.parse import quote

root=tempfile.mkdtemp(prefix='worklinks-prebid-files-')
os.environ['G2B_DB_PATH']=os.path.join(root,'bids.sqlite3')
p=runpy.run_path('server/g2b-proxy.py',run_name='prebid_names_test')
assert p['prebid_original_filename']('attachment;filename='+quote('붙임 제안요청서.hwpx')+';')=='붙임 제안요청서.hwpx'
assert p['prebid_original_filename']("attachment;filename*=UTF-8''"+quote('붙임 제출서식.hwpx'))=='붙임 제출서식.hwpx'
assert p['prebid_original_filename']('inline;filename=deceptive.pdf')==''
assert p['prebid_original_filename']('attachment;filename=..%2Fsecrets.pdf')=='secrets.pdf'
number='R26BD00302593'
base='https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do'
urls=[base+'?bfSpecRegNo='+number+'&fileType=BFDTL&fileSeq='+str(i) for i in (1,2,3)]
assert all(p['prebid_official_attachment'](u,number) for u in urls)
assert not p['prebid_official_attachment']('https://evil.example.com/download?bfSpecRegNo='+number,number)
assert not p['prebid_official_attachment'](urls[0].replace('bfSpecRegNo='+number,'bfSpecRegNo=OTHER'),number)
db=sqlite3.connect(os.path.join(root,'g2b-prebid.sqlite3'))
db.executescript("""CREATE TABLE prebid_records(stage TEXT,kind TEXT,item_id TEXT,payload TEXT,first_seen TEXT,last_seen TEXT,PRIMARY KEY(stage,kind,item_id));
CREATE TABLE prebid_windows(stage TEXT,kind TEXT,day TEXT,last_success REAL,source_total INTEGER,stored INTEGER,failed TEXT);""")
row={'id':number,'stage':'prespec','kind':'servc','title':'2026 문화선도산단 남동하루 홈페이지 구축','files':urls}
db.execute('INSERT INTO prebid_records VALUES(?,?,?,?,?,?)',('prespec','servc',number,json.dumps(row),'2026','2026'))
db.execute('INSERT INTO prebid_windows VALUES(?,?,?,?,?,?,?)',('prespec','servc','20261118',100,1,1,''))
db.commit();db.close()
class Response:
    def __init__(self,url):self.url=url;self.headers={'Content-Disposition':'attachment;filename='+quote({1:'붙임 제안요청서.hwpx',2:'붙임 제출서식.hwpx',3:'붙임 긴급입찰사유서.hwpx'}[int(url[-1])])+';'}
    def geturl(self):return self.url
    def close(self):pass
calls=[]
def fake_urlopen(req,timeout):
    assert timeout<=6
    calls.append(req.full_url)
    assert req.get_method()=='GET'  # official G2B HEAD is 403
    return Response(req.full_url)
p['prebid_probe_original_filename'].__globals__['urlopen']=fake_urlopen
first=p['query_prebid_file_names']('prespec','servc',number)
assert first['fileNames']==['붙임 제안요청서.hwpx','붙임 제출서식.hwpx','붙임 긴급입찰사유서.hwpx']
assert first['complete'] and first['officialApiCalls']==0 and first['officialFileHeaderChecks']==3
assert len(calls)==3
second=p['query_prebid_file_names']('prespec','servc',number)
assert second['fileNames']==first['fileNames'] and second['officialFileHeaderChecks']==0
assert len(calls)==3
listing=p['query_prebid_records']('prespec',500,0)
assert listing['items'][0]['fileNames']==first['fileNames']
try:p['query_prebid_file_names']('prespec','servc','R26BD00000000')
except p['ApiError'] as e:assert e.status==404
else:raise AssertionError('nonexistent ID should be refused')
try:p['query_prebid_file_names']('plan','servc',number)
except p['ApiError'] as e:assert e.status==400
else:raise AssertionError('plan cannot hit attachment metadata endpoint')
print('WORKLINKS_G2B_REAL_FILENAME_FROM_GET_HEADERS_PASS')
