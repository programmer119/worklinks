#!/usr/bin/env python3
"""No-network regression for G2B attachments whose names lie about content."""
import io
import sys
import zipfile
import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

source=Path(__file__).resolve().parents[1]/'scripts/refresh_worklinks_rfp.py'
spec=importlib.util.spec_from_file_location('rfp_magic',source)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# HWPX-labelled OLE HWP MUST take the HWP5 reader, not zipfile.ZipFile.
ole=bytes.fromhex('D0CF11E0A1B11AE1')+b'fake-ole-hwp-fixture'
def hwp_probe(cmd,**opts):
    assert cmd[0]=='hwp5txt',cmd
    assert Path(cmd[1]).read_bytes()==ole
    return SimpleNamespace(returncode=0,stdout=b'Official bid eligibility text')
with patch.object(mod.subprocess,'run',side_effect=hwp_probe):
    assert mod.extract('bid.hwpx',ole)=='Official bid eligibility text'
# PDF even if filename is .hwpx should invoke PDF reader.
class Page:
    def __init__(self,text):self.text=text
    def extract_text(self):return self.text
class Reader:
    def __init__(self,stream):
        source=stream.read()
        assert source.startswith(b'%PDF-'),source[:8]
        self.pages=[Page(source[5:].decode('utf-8'))]
with patch.dict(sys.modules,{'pypdf':SimpleNamespace(PdfReader=Reader)}):
    assert mod.extract('notice.hwpx',b'%PDF-actual pdf content')=='actual pdf content'
    # G2B's misnamed "support.pdf" is a ZIP with two separate PDFs.
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('contract.pdf',b'%PDF-first content')
        z.writestr('justification.pdf',b'%PDF-second content')
    result=mod.extract('support.pdf',stream.getvalue())
    assert 'FILE contract.pdf\nfirst content' in result,result
    assert 'FILE justification.pdf\nsecond content' in result,result
    assert result.count('FILE ') == 2,result

# A real ZIP-backed HWPX is still read as HWPX.
hwpx=io.BytesIO()
with zipfile.ZipFile(hwpx,'w') as z:
    z.writestr('Contents/section0.xml','''<?xml version="1.0" encoding="UTF-8"?>
      <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
        <hp:p><hp:t>Official HWPX clause</hp:t></hp:p>
      </hp:section>''')
assert mod.extract('report.pdf',hwpx.getvalue())=='Official HWPX clause'

# Continue rejecting unsafe ZIP archive paths, even if extension is .pdf.
bad=io.BytesIO()
with zipfile.ZipFile(bad,'w') as z:z.writestr('../evil.pdf',b'%PDF-bad')
try:
    mod.extract('z.pdf',bad.getvalue())
    raise AssertionError('unsafe ZIP path accepted')
except ValueError as exc:
    assert str(exc)=='unsafe_archive_path'
print('WORKLINKS_RFP_MAGIC_SIGNATURE_REGRESSION=PASS')
