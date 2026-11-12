#!/usr/bin/env python3
"""No-network regression: search the 123 saved procurement archive, never the upstream G2B API."""
import json,os,pathlib,runpy,tempfile

root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as t:
    old=os.environ.get('G2B_DB_PATH')
    old_snapshot=os.environ.get('WORKLINKS_SNAPSHOT_DIR')
    os.environ['G2B_DB_PATH']=str(pathlib.Path(t)/'saved.sqlite3')
    os.environ['WORKLINKS_SNAPSHOT_DIR']=str(pathlib.Path(t)/'snapshots')
    pathlib.Path(os.environ['WORKLINKS_SNAPSHOT_DIR']).mkdir()
    (pathlib.Path(t)/'snapshots'/'rfp-coverage-index.json').write_text(
      json.dumps({'ok':True,'byNotice':{
        'R26BK01792736:000':{'status':'text_extracted_requires_review',
          'manifestComplete':True,'files':[{'readable':True}],
          'changcomClauseEvidence':{'clauseCandidates':{
            'industry_code':[{'text':'입찰참가자격: 컴퓨터관련서비스사업 1468 등록 필수',
                               'sourceFile':'공식입찰공고.pdf','codes':['1468']}]
          }}}}}))
    try:
        m=runpy.run_path(str(root/'server/g2b-proxy.py'),run_name='offline_search_test')
        persist=m['persist_bids']
        search=m['query_saved_bids']
        a='R26BK01792736'
        b='R26BK01824348'
        results=persist([
          {'kind':'servc','bidNo':a,'order':'000','title':'2026년 에너지온실가스 기술정보 플랫폼 기능개발',
           'org':'검증 발주기관','closes':'2026-11-11 10:00:00','budget':'50000000'},
          {'kind':'servc','bidNo':b,'order':'000','title':'AI OCR 기반 지능형 문서처리 시스템 스크립트 개발 및 안정화 용역',
           'org':'다른 발주기관','closes':'2026-11-11 17:00:00','budget':'20000000'},
          {'kind':'thng','bidNo':'R26BK01800001','order':'000','title':'키오스크 장비 구매',
           'org':'장비 기관'}])
        with m['open_bid_db']() as db:
            db.execute("UPDATE bid_notices SET sw_candidate=1")
            db.commit()
        exact=search(10,0,True,a)
        assert exact['searchMode']=='saved_only'
        assert exact['totalCount']==1 and exact['items'][0]['bidNo']==a,exact
        assert exact['items'][0]['rfpSavedState']['complete'] is True,exact
        quotes=exact['items'][0]['rfpSavedState']['excerpts']
        assert len(quotes)==1 and '1468' in quotes[0]['text'],exact
        assert quotes[0]['sourceFile']=='공식입찰공고.pdf'
        korean=search(10,0,True,'문서처리')
        assert korean['totalCount']==1 and korean['items'][0]['bidNo']==b,korean
        assert korean['items'][0]['rfpSavedState']['seen'] is False,korean
        org=search(10,0,True,'검증 발주기관')
        assert org['totalCount']==1 and org['items'][0]['bidNo']==a,org
        literal=search(10,0,True,'%')
        assert literal['totalCount']==0,literal
        unexpected=search(10,0,True,'UNKNOWNNOTICE')
        assert unexpected['totalCount']==0,unexpected
        all_=search(10,0,True)
        assert all_['totalCount']==3 and all_['searchMode']=='none',all_
        try:search(10,0,True,'A'*81)
        except m['ApiError']:pass
        else:raise AssertionError('long search query accepted')
    finally:
        if old is None:os.environ.pop('G2B_DB_PATH',None)
        else:os.environ['G2B_DB_PATH']=old
        if old_snapshot is None:os.environ.pop('WORKLINKS_SNAPSHOT_DIR',None)
        else:os.environ['WORKLINKS_SNAPSHOT_DIR']=old_snapshot
print('WORKLINKS_READ_ONLY_SAVED_TENDER_SEARCH=PASS')
