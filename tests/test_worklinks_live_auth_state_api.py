#!/usr/bin/env python3
"""Read-only production contract smoke test; never uses a member credential."""
import json
import urllib.error
import urllib.request

BASE = 'https://api-suaveforge.suaveforge.com:18458/api/g2b'

def request(path, method='GET'):
    req = urllib.request.Request(
        BASE + path,
        data=(b'{"kind":"applied","id":"noauth-smoke","value":true}' if method == 'POST' else None),
        method=method,
        headers={
            'Accept': 'application/json',
            'Origin': 'https://worklinks.suaveforge.com',
            **({'Content-Type':'application/json'} if method == 'POST' else {})
        })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read().decode('utf-8'))

status, headers, config = request('/worklinks-auth-config')
assert status == 200, ('auth config HTTP', status)
assert config.get('ok') is True and config.get('enabled') is True, ('AuthHub project not active', config)
assert config.get('project') == 'p47', ('Unexpected AuthHub project', config.get('project'))
assert config.get('authApi') == 'https://api-authhub.suaveforge.com', ('Wrong AuthHub upstream', config.get('authApi'))
print('PRODUCTION_AUTH_CONFIG_P47=PASS', flush=True)

for method in ('GET','POST'):
    status, headers, body = request('/worklinks-state', method)
    assert status == 401, ('Missing auth boundary', method, status, body)
    assert body.get('ok') is False and body.get('error') == 'auth_required', ('Unexpected unauthenticated API response', method, body)
    cors = {key.lower():value for key,value in headers.items()}
    assert cors.get('access-control-allow-origin') == 'https://worklinks.suaveforge.com', ('Unexpected CORS', method, cors.get('access-control-allow-origin'))
    print('PRODUCTION_STATE_'+method+'_AUTH_BOUNDARY=PASS', flush=True)
