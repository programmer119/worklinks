#!/usr/bin/env python3
"""A SHA-verified cached HWP can still contain a truncated CFB sector chain."""
import io
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rfp_download_worker as download

class StreamFixture:
    def __init__(self,declared,data):
        self.declared=declared
        self.data=data
    def exists(self,name):
        return name=='FileHeader'
    def listdir(self,streams=True,storages=False):
        return [['BodyText','Section0']]
    def get_size(self,path):
        return self.declared
    def openstream(self,path):
        return io.BytesIO(self.data)

bad=StreamFixture(15433,b'')
assert download._hwp_ole_bodytext_issue(bad)=='hwp_bodytext_ole_sector_chain_truncated'
partial=StreamFixture(116846,b'X'*76713)
assert download._hwp_ole_bodytext_issue(partial)=='hwp_bodytext_ole_sector_chain_truncated'
complete=StreamFixture(15433,b'A'*15433)
assert download._hwp_ole_bodytext_issue(complete)==''
print('RFP_HWP_OLE_DIRECTORY_SIZE_MUST_MATCH_REAL_BODYTEXT_SECTORS=PASS')
