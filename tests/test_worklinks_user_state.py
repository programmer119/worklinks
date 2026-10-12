#!/usr/bin/env python3
"""Isolated WorkLinks account-state regressions: no live AuthHub/API credentials."""
import base64
import json
import os
import runpy
import tempfile
from unittest import mock

os.environ['WORKLINKS_STATE_DB']=os.path.join(tempfile.mkdtemp(prefix='worklinks-state-'),'status.sqlite3')
mod=runpy.run_path(os.environ.get('WORKLINKS_G2B_SOURCE','/app/g2b-proxy.py'),run_name='worklinks_state_tests')
put=mod['worklinks_state_put']
get=mod['worklinks_state_get']
ApiError=mod['ApiError']

record={'id':'example-contest-2026','kind':'applied','value':True,'title':'예시 대회','url':'https://example.org/call'}
assert put('p47','user-first',record)['ok'] is True
assert get('p47','user-first')['records'][0]['value'] is True
assert get('p47','user-second')['records']==[]
assert get('p48','user-first')['records']==[]
assert put('p47','user-first',{**record,'kind':'hidden'})['ok'] is True
assert put('p47','user-first',{**record,'kind':'business'})['ok'] is True
assert len(get('p47','user-first')['records'])==3
assert put('p47','user-first',{**record,'value':False})['value'] is False
records=get('p47','user-first')['records']
assert len(records)==3
assert next(x for x in records if x['kind']=='applied')['value'] is False
for bad in [{'id':'bad/../id','kind':'applied','value':True},
            {'id':'valid-id','kind':'admin','value':True},
            {'id':'valid-id','kind':'applied','value':'true'}]:
    try:put('p47','user-first',bad)
    except ApiError as exc:assert exc.status==400
    else:raise AssertionError('invalid state accepted')

# Identity boundary: even a valid-looking token is rejected if AuthHub /v1/me
# confirms a different project or authenticated user. Network is mocked.
def fake_token(claims):
    return 'e30.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.signature'
import time
token=fake_token({'sub':'user-first','project':'p47','exp':int(time.time())+3600})
class FakeResponse:
    def read(self,size):return json.dumps({'user':{'id':'user-first'},'membership':{'status':'active'}}).encode()
with mock.patch.dict(os.environ,{'WORKLINKS_AUTHHUB_PROJECT':'p47'}):
    with mock.patch.dict(mod['worklinks_verify_identity'].__globals__,{'urlopen':lambda *a,**k:FakeResponse()}):
        assert mod['worklinks_verify_identity']('Bearer '+token)==('p47','user-first')
        for claims in [{'sub':'user-first','project':'p48','exp':int(time.time())+3600},
                       {'sub':'user-other','project':'p47','exp':int(time.time())+3600},
                       {'sub':'user-first','project':'p47','exp':int(time.time())-1}]:
            try:mod['worklinks_verify_identity']('Bearer '+fake_token(claims))
            except ApiError as exc:assert exc.status==403
            else:raise AssertionError('mismatched token accepted')
print('WORKLINKS_AUTHHUB_STATE_TEST=PASS')
