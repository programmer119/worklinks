#!/usr/bin/env python3
"""Server123 site mirror read-only, no path traversal or upstream API calls."""
import importlib.util
import io
import pathlib
import tempfile
import json

root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g2bsite',root/'server/g2b-proxy.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as t:
    site=pathlib.Path(t)/'public'
    snapshot=pathlib.Path(t)/'snapshots'
    (site/'startup-support').mkdir(parents=True)
    snapshot.mkdir()
    (site/'startup-support/index.html').write_text('TEST_SITE_INDEX',encoding='utf-8')
    (site/'startup-support/app.js').write_text('const a=1;',encoding='utf-8')
    (snapshot/'investment-opportunities.json').write_text(
        '{"schemaVersion":1,"opportunities":[]}',encoding='utf-8')
    m.STATIC_WORKTREE=str(site)
    m.SNAPSHOT_ROOT=str(snapshot)
    class Handler(m.Handler):
        def __init__(self):
            self.headers={}
            self.status=0
            self.output=io.BytesIO()
            self.wfile=self.output
        def send_response(self,code,*a):self.status=code
        def send_header(self,*a):pass
        def end_headers(self):pass
    for path,expected in (
        ('/startup-support/','TEST_SITE_INDEX'),
        ('/startup-support/app.js','const a=1;')):
        h=Handler()
        h.reply_worklinks_site(path)
        assert h.status==200,(path,h.status)
        assert h.output.getvalue().decode()==expected
    h=Handler()
    h.reply_worklinks_site('/startup-support/investment-opportunities.json')
    assert h.status==200
    assert json.loads(h.output.getvalue())['schemaVersion']==1
    for path in ('/startup-support/.git/config',
                 '/startup-support/../secrets/g2b.env',
                 '/startup-support/%2e%2e/secrets/g2b.env',
                 '/startup-support/evil.py'):
        h=Handler()
        h.reply_worklinks_site(path)
        assert h.status in (400,404),(path,h.status)
print('WORKLINKS_123_STATIC_SITE_MIRROR_SAFETY=PASS')
