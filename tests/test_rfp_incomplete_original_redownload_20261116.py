#!/usr/bin/env python3
"""Do not trust a SHA receipt for a structurally incomplete official response."""
import hashlib,io,sys,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rfp_download_worker as download

short=b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n'
full=short+b'startxref\n12\n%%EOF\n'
assert download._original_structure_issue_bytes(short)=='pdf_missing_eof'
assert download._original_structure_issue_bytes(full)==''
ole_bad=bytes.fromhex('D0CF11E0A1B11AE1')+b'\0'*510
assert download._original_structure_issue_bytes(ole_bad)=='ole_directory_unreadable'
z=io.BytesIO()
with zipfile.ZipFile(z,'w') as dst:dst.writestr('body.hwpx',b'abc')
assert download._original_structure_issue_bytes(z.getvalue())==''
assert download._original_structure_issue_bytes(b'PK\x03\x04corrupt')=='zip_central_directory_missing'

class Reply(io.BytesIO):
    status=200
    def __init__(self,raw):
        super().__init__(raw)
        self.headers={'Content-Length':str(len(raw))}
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class Ledger:
    def __init__(self,path,raw):
        self.path=Path(path)
        self.raw=raw
        self.calls=[]
    def verified_bytes_info(self,key):
        return {'bytes':len(self.raw),'sha256':hashlib.sha256(self.raw).hexdigest()}
    def get_bytes(self,key):return self.raw
    def link_attachment(self,*args):self.calls.append('link')
    def record(self,*args,**kwargs):self.calls.append(args[2])
    def save_file(self,key,path,**kwargs):
        self.raw=Path(path).read_bytes()
        self.calls.append('fresh_saved')
        return {'bytes':len(self.raw),'sha256':hashlib.sha256(self.raw).hexdigest()}

with tempfile.TemporaryDirectory() as folder:
    log=Ledger(Path(folder)/'ledger.sqlite3',short)
    called=[]
    def fresh_request(*args,**kwargs):
        called.append(1)
        return Reply(full)
    with patch.object(download.reader.OPENER,'open',side_effect=fresh_request):
        result=download.stream_original_to_verified_ledger(
            'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?id=valid',
            log,'R26BK00000001:000','2099-11-16')
    assert called==[1] and result['bytes']==len(full)
    assert log.raw==full and 'incomplete_original_refetch' in log.calls and 'fresh_saved' in log.calls

    # Once replaced by complete bytes, never GET the same original again.
    with patch.object(download.reader.OPENER,'open',side_effect=AssertionError('unneeded GET')):
        reused=download.stream_original_to_verified_ledger(
            'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?id=valid',
            log,'R26BK00000001:000','2099-11-16')
    assert reused['bytes']==len(full)
print('RFP_CORRUPT_SHA_CACHED_BYTES_FORCE_VALIDATED_REDOWNLOAD=PASS')
