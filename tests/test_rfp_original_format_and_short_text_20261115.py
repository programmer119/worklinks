#!/usr/bin/env python3
"""Actual OLE XLS, HML and HTML parsing without a government network request."""
import io
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_worklinks_rfp as reader
import repair_open_rfp_cached_attachments as repair

# Real 97-2003 workbook bytes, not a fake extension or fabricated PDF body.
import xlwt
workbook=xlwt.Workbook(encoding='utf-8')
sheet=workbook.add_sheet('인원')
sheet.write(0,0,'직무')
sheet.write(0,1,'인원')
sheet.write(1,0,'PM')
sheet.write(1,1,1)
sheet.write(2,0,'개발자')
sheet.write(2,1,2)
stream=io.BytesIO()
workbook.save(stream)
raw=stream.getvalue()
assert raw.startswith(reader._OLE_HEADER)
assert reader.ole_document_kind('role.xls',raw)=='.xls'
assert reader.detected_source_format('role.xls',raw)=='xls'
xls=reader.extract('role.xls',raw)
assert '개발자' in xls and 'PM' in xls,xls
# Misnamed Office document must still use the binary's workbook stream.
assert '개발자' in reader.extract('incorrect.hwp',raw)

xml=b'''<?xml version="1.0" encoding="utf-8"?>
<HML><BODY><P>Bid qualification</P><P>Technical staffing 2 persons</P></BODY></HML>'''
hml=reader.extract('notice.hml',xml)
assert 'Bid qualification' in hml and 'Technical staffing' in hml,hml

html=b'<html><body><p>Bid qualification for applicants</p><script>malicious()</script><p>Technical staffing team</p></body></html>'
markup=reader.extract('notice.htm',html)
assert 'Bid qualification' in markup and 'Technical staffing' in markup,markup
assert 'malicious' not in markup,markup

# A failed old reader is eligible again after upgrading the reader, but cannot
# lead to a direct government GET. The separate stage-2 receipt test guards that.
old={'files':[{'name':'role.xls','readable':False,
               'errorCategory':'hwp5txt_failed',
               'lastReaderAttemptVersion':'pdf24-image-zip-hwpx-v3'}]}
assert len(repair.reader_retry_files(old))==1
old['files'][0]['lastReaderAttemptVersion']=repair.READER_ATTEMPT_VERSION
assert repair.reader_retry_files(old)==[]

# Compact status retains the original detected format and specific exception
# for forensic repair. A generic file_extract_failure alone is insufficient.
compact=reader.compact_coverage({
    'status':'text_extracted_requires_review','manifestComplete':True,
    'files':[{'name':'role.xls','readable':False,'detectedFormat':'xls',
              'errorCategory':'legacy_xls_reader_failed',
              'error':'XLRDError: actual stream read failed'}]})
assert compact['files'][0]['detectedFormat']=='xls'
assert 'XLRDError' in compact['files'][0]['errorDetail']

print('RFP_REAL_XLS_AND_MARKUP_MAGIC_REGRESSION=PASS')
