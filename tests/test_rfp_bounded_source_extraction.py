#!/usr/bin/env python3
"""Stage-3 scanning must not let a CPU-heavy file hang the 8-notice batch."""
import io,json,os,sqlite3,subprocess,sys,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import rfp_live_activity as live

# Real local child-process path: DOCX extracted in a separate subprocess.
with io.BytesIO() as buff:
    with zipfile.ZipFile(buff,'w') as out:
        out.writestr('word/document.xml',
          '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:body><w:p><w:r><w:t>official local RFP staffing requirements</w:t>'
          '</w:r></w:p></w:body></w:document>')
    docx=buff.getvalue()

with patch.dict(os.environ,{'WORKLINKS_RFP_EXTRACT_TIMEOUT_SECONDS':'12'}):
    text,evidence=reader.bounded_source_extract('requirements.docx',docx)
    assert 'official local RFP staffing requirements' in text,repr(text)
    assert evidence['sourceComplete'] is True,evidence

# A pathological parser is killed by subprocess.run's timeout and categorized
# as INCOMPLETE source extraction, not silently marked as successful.
with patch.dict(os.environ,{'WORKLINKS_RFP_EXTRACT_TIMEOUT_SECONDS':'1'}),\
     patch.object(reader.subprocess,'run',side_effect=subprocess.TimeoutExpired(['python'],1)):
    try:
        reader.bounded_source_extract('oversized-vector.pdf',b'%PDF-slow')
        raise AssertionError('timeout should reject the document')
    except ValueError as err:
        assert str(err)=='source_extraction_timeout_deferred',str(err)
        assert reader.classify_failure(err)=='source_extraction_timeout_deferred'

# A genuine file-progress signal must clear stale "waiting_for_download"
# even though the parent scheduler is blocked while the child scans.
with tempfile.TemporaryDirectory() as tmp:
    p=str(Path(tmp)/'live.sqlite3')
    with patch.dict(os.environ,{'WORKLINKS_RFP_DUAL_QUEUE_DB':p}):
        live.worker('scan','retry','waiting_for_download')
        live.record('scan','R26BK01234567:000',file_name='verified.pdf',
                    phase='텍스트 추출',status='working')
        with sqlite3.connect(p) as db:
            status,error=db.execute("SELECT status,error_text FROM rfp_live_workers WHERE lane='scan'").fetchone()
        assert (status,error)==('running',''),(status,error)

print('RFP_BOUNDED_FILE_EXTRACTION_AND_SCAN_HEARTBEAT=PASS')
