#!/usr/bin/env python3
"""No-network prebid collection and official-source-read-only API regression."""
import ast
import datetime as dt
import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prebid',ROOT/'scripts/g2b_prebid_collector.py')
prebid=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prebid)

with tempfile.TemporaryDirectory() as temp:
 prebid.DATA=pathlib.Path(temp)/'g2b-prebid.sqlite3'
 prebid.KEY_PATH=pathlib.Path(temp)/'operating.env'
 prebid.KEY_PATH.write_text('G2B_STANDARD_SERVICE_KEY=AUTHORIZED_TEST_KEY\n',encoding='utf-8')
 assert prebid.key()=='AUTHORIZED_TEST_KEY'
 api_src=(ROOT/'server/g2b-proxy.py').read_text(encoding='utf-8')
 tree=ast.parse(api_src)
 func=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
           and n.name=='query_prebid_records')
 class ApiError(Exception):pass
 scope={'os':os,'sqlite3':sqlite3,'json':json,'datetime':dt,
        'G2B_DB_PATH':str(pathlib.Path(temp)/'bids.sqlite3'),'ApiError':ApiError}
 exec(compile(ast.Module(body=[func],type_ignores=[]),'test-api','exec'),scope)
 read=scope['query_prebid_records']
 initial=read('plan')
 assert initial['ok'] and not initial['ready'] and initial['total']==0
 try:read('unsafe')
 except ApiError:pass
 else:raise AssertionError('invalid stage accepted')
 plan={'orderPlanUntyNo':'R26DD00099999','bizNm':'정보시스템 고도화 구축',
       'orderInsttNm':'발주청','sumOrderAmt':'220000000',
       'orderYear':'2027','orderMnth':'2','nticeDt':'202611192000'}
 spec_row={'bfSpecRgstNo':'R26BD00099999','prdctClsfcNoNm':'소프트웨어 플랫폼 개발',
           'asignBdgtAmt':'85000000','orderInsttNm':'수요기관','rgstDt':'202611191200',
           'opninRgstClseDt':'202611251800',
           'specDocFileUrl1':'https://www.g2b.go.kr/file/spec.pdf',
           'specDocFileUrl2':'https://attacker.example/key'}
 assert prebid.normalize('plan','servc',plan)['plannedMonth']=='2027-02'
 assert prebid.normalize('prespec','servc',spec_row)['files']==['https://www.g2b.go.kr/file/spec.pdf']
 non_sw=prebid.normalize('plan','servc',{'orderPlanUntyNo':'NONSWSAMPLE','bizNm':'사무용 의자 구매'})
 assert non_sw['swCandidate'] is False and non_sw['swFlagSource']=='none'
 assert prebid.normalize('plan','servc',{'bizNm':'번호 없는 공고'}) is None
 assert prebid.normalize('plan','servc',{'orderPlanUntyNo':'1','bizNm':'일반 물품',
        'swBizObjYn':'Y'})['swFlagSource']=='official'
 db=prebid.connect()
 today=dt.datetime.now(prebid.KST).strftime('%Y%m%d')
 def fake_fetch(db,key,stage,kind,day,page):
  assert page==1
  return (1,[plan] if stage=='plan' else [spec_row])
 with mock.patch.object(prebid,'fetch_page',side_effect=fake_fetch):
  assert prebid.collect_window(db,'FAKE','plan','servc',today).startswith('ok:')
  assert prebid.collect_window(db,'FAKE','prespec','servc',today).startswith('ok:')
  assert prebid.collect_window(db,'FAKE','plan','servc',today)=='skipped'
 valid=read('plan')
 assert valid['ready'] and valid['total']==1 and len(valid['items'])==1,valid
 assert valid['items'][0]['id']=='R26DD00099999'
 assert valid['noGovernmentApiCalls'] is True
 assert read('prespec')['items'][0]['opinionDeadline']=='202611251800'
 assert read('plan',limit=1,offset=1)['items']==[]
 # Access-denied source must be retained and never hammered every 30 minutes.
 with mock.patch.object(prebid,'fetch_page',side_effect=RuntimeError('prebid_official_http_403')) as call:
  assert prebid.collect_window(db,'FAKE','plan','thng',today)=='failed:prebid_official_http_403'
  assert prebid.collect_window(db,'FAKE','plan','thng',today)=='blocked:prebid_official_http_403'
  assert call.call_count==1,call.call_count
 # Denied plan API must not prevent an independently authorized spec API.
 with mock.patch.object(prebid,'fetch_page',side_effect=fake_fetch) as call:
  assert prebid.collect_window(db,'FAKE','prespec','thng',today).startswith('ok:')
  assert call.call_count==1
 # Deployment key rotation immediately unblocks old legacy 403 snapshots
 # without deleting prior successful source windows or resetting call quota.
 prebid.reset_auth_gates_on_key_change(db,'AUTHORIZED_TEST_KEY')
 with mock.patch.object(prebid,'fetch_page',side_effect=fake_fetch) as retry:
  assert prebid.collect_window(db,'AUTHORIZED_TEST_KEY','plan','thng',today).startswith('ok:')
  assert retry.call_count==1
 # Future repeated startup with same key never alters saved success.
 prebid.reset_auth_gates_on_key_change(db,'AUTHORIZED_TEST_KEY')
 assert prebid.collect_window(db,'AUTHORIZED_TEST_KEY','plan','thng',today)=='skipped'
 # V1 SW-only windows must be recrawled once on upgrade despite a recent
 # successful window, still using the existing daily quota counter.
 db.execute("UPDATE prebid_windows SET scope_version=1 WHERE stage='plan' AND kind='servc' AND day=?",(today,))
 db.commit()
 with mock.patch.object(prebid,'fetch_page',side_effect=fake_fetch) as refresh:
  assert prebid.collect_window(db,'AUTHORIZED_TEST_KEY','plan','servc',today).startswith('ok:')
  assert refresh.call_count==1
 assert db.execute("SELECT scope_version FROM prebid_windows WHERE stage='plan' AND kind='servc' AND day=?",(today,)).fetchone()[0]==2
 # Official non-SW rows remain accessible in the same stage without being
 # mislabeled as SW candidates. Unrelated RFP tables are untouched.
 plain={'orderPlanUntyNo':'NONSW0001','bizNm':'사무실 책상 구매',
        'orderInsttNm':'가상기관','nticeDt':'202611191100'}
 yesterday=(dt.datetime.now(prebid.KST).date()-dt.timedelta(days=1)).strftime('%Y%m%d')
 with mock.patch.object(prebid,'fetch_page',return_value=(1,[plain])) as full:
  assert prebid.collect_window(db,'AUTHORIZED_TEST_KEY','plan','thng',yesterday).startswith('ok:')
  assert full.call_count==1
 current=read('plan')
 assert current['total']==2, current
 assert any(x['id']=='NONSW0001' and x['swFlagSource']=='none' for x in current['items'])
 db.close()
print('WORKLINKS_PREBID_COLLECTOR_API_CONTRACT_PASS')
