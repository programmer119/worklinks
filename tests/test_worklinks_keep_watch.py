#!/usr/bin/env python3
"""Server-side kept-job ownership and opt-in spectator regressions (no network)."""
import os,runpy,tempfile
os.environ['WORKLINKS_STATE_DB']=os.path.join(tempfile.mkdtemp(prefix='keep-watch-'),'members.sqlite3')
p=runpy.run_path(os.environ.get('WORKLINKS_G2B_SOURCE','server/g2b-proxy.py'),run_name='keep_watch_test')
ApiError=p['ApiError']
own=p['worklinks_keep_own']
put=p['worklinks_keep_update']
share=p['worklinks_keep_share']
members=p['worklinks_keep_members']
watch=p['worklinks_keep_watch']
snapshot={'title':'서울 SW 시스템 구축','url':'https://www.g2b.go.kr/notice',
          'org':'서울특별시','amount':'2억원','deadline':'2026.11.25',
          'privateMemo':'cannot_share_this'}
record={'id':'g2b-R26BK12345678-000','value':True,'snapshot':snapshot}
assert own('p47','member-11111111')['items']==[]
assert put('p47','member-11111111',record)['ok']
mine=own('p47','member-11111111')
assert len(mine['items'])==1
assert mine['items'][0]['title']=='서울 SW 시스템 구축'
assert 'privateMemo' not in mine['items'][0]
assert own('p47','member-22222222')['items']==[]
assert own('p48','member-11111111')['items']==[]
assert members('p47')['members']==[]
try:watch('p47','member-22222222','member-11111111')
except ApiError as e:assert e.status==404
else:raise AssertionError('private keep leaked before consent')
assert share('p47','member-11111111',{'enabled':True,'alias':'개발 1팀'})['shareEnabled']
directory=members('p47')['members']
assert len(directory)==1 and directory[0]['name']=='개발 1팀'
assert directory[0]['count']==1
shared=watch('p47','member-22222222','member-11111111')
assert shared['readOnly'] is True
assert shared['items']==mine['items']
assert shared['member']['name']=='개발 1팀'
# The same item ID belongs to the account derived from verified AuthHub JWT,
# not to a caller-chosen user ID.
assert put('p47','member-22222222',{'id':record['id'],'value':False})['ok']
assert len(own('p47','member-11111111')['items'])==1
assert len(own('p47','member-22222222')['items'])==0
assert put('p47','member-11111111',{'id':record['id'],'value':False})['ok']
assert own('p47','member-11111111')['items']==[]
assert members('p47')['members'][0]['count']==0
assert put('p47','member-11111111',record)['ok']
assert share('p47','member-11111111',{'enabled':False,'alias':'개발 1팀'})['shareEnabled'] is False
assert members('p47')['members']==[]
try:watch('p47','member-22222222','member-11111111')
except ApiError as e:assert e.status==404
else:raise AssertionError('revoked share still readable')
for invalid in [
    {'id':'../private','value':True,'snapshot':snapshot},
    {'id':'valid-item','value':'true','snapshot':snapshot},
    {'id':'valid-item','value':True,'snapshot':{'title':''}},
    {'id':'valid-item','value':True,'snapshot':{'title':'bad','amount':{}}},
]:
    try:put('p47','member-11111111',invalid)
    except ApiError as e:assert e.status==400
    else:raise AssertionError('invalid keep was stored')
try:share('p47','member-11111111',{'enabled':True,'alias':'A'*33})
except ApiError as e:assert e.status==400
else:raise AssertionError('invalid share alias allowed')
try:watch('p47','member-11111111','../other')
except ApiError as e:assert e.status==400
else:raise AssertionError('invalid watch target allowed')
# A deployed handler must expose the API routes, not just implementation functions.
import pathlib
source_path=pathlib.Path(os.environ.get('WORKLINKS_G2B_SOURCE','server/g2b-proxy.py'))
source=source_path.read_text(encoding='utf-8')
for route in ("if u.path in ('/api/g2b/worklinks-keep'",
              "if operation == '/api/g2b/worklinks-keep':",
              "if operation == '/api/g2b/worklinks-keep-share':",
              "worklinks_keep_watch(project, user_id, get('member'))"):
    assert route in source, 'keep API route missing: '+route
print('WORKLINKS_KEEP_WATCH_ROUTES=PASS')
print('WORKLINKS_KEEP_WATCH_ACCOUNT_ISOLATION=PASS')
