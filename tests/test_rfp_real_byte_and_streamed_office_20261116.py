#!/usr/bin/env python3
"""Verified-original format signatures and large OOXML streams (no HTTP)."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_worklinks_rfp as r

def archive(parts):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,contents in parts.items():z.writestr(name,contents)
    return buffer.getvalue()

hml=(b'<?xml version="1.0" encoding="UTF-8"?>'
     b'<HWPML><BINDATA>'+b'Z'*4000+b'</BINDATA><BODY>'
     b'<P><CHAR>Real government qualifying clause</CHAR></P></BODY></HWPML>')
for name in ('attachment.hwp','attachment.hwpx','attachment.hwtx'):
    output=r.extract(name,hml)
    assert 'Real government qualifying clause' in output
    assert 'ZZZZZZZ' not in output
    assert r.detected_source_format(name,hml)=='hwpml_xml'
z=archive({'rules.hwp':hml,'desktop.ini':'[.ShellClassInfo]',
           'formal.hwtx':archive({'Contents/section0.xml':
                '<section><p><t>Official template conditions</t></p></section>'})})
text=r.extract('renamed.hwp',z)
assert 'Real government qualifying clause' in text
assert 'Official template conditions' in text
assert 'desktop.ini' not in text
assert r.detected_source_format('renamed.hwp',z)=='zip_or_ooxml'

html=b'<html xmlns:o="urn:schemas-microsoft-com:office:office"><body><p>Official procurement pledge</p></body></html>'
assert r.detected_source_format('pledge.xls',html)=='html'
assert 'Official procurement pledge' in r.extract('pledge.xls',html)
# The actual official XLS is HTML, not well-formed XML: empty HTML tags
# and unclosed paragraph tags must still be parsed as ordinary HTML.
html_legacy=b'<html><head><meta charset=ks_c_5601-1987><body><p>Vendor pledge<p>Proof of qualification'
assert r.detected_source_format('bad.xls',html_legacy)=='html'
assert 'Proof of qualification' in r.extract('bad.xls',html_legacy)

with_cell=archive({'xl/workbook.xml':'<workbook/>',
                   'xl/worksheets/sheet1.xml':'<worksheet><sheetData><row><c t="inlineStr"><is><t>Genuine price list</t></is></c></row></sheetData></worksheet>'})
assert 'Genuine price list' in r.extract('schedule.cell',with_cell)
unsupported=archive({'HancomCell/document.dat':b'no supported worksheet'})
try:r.extract('schedule.cell',unsupported)
except ValueError as err:assert str(err)=='hancom_cell_converter_required',str(err)
else:raise AssertionError('Unrecognized CELL container was accepted')

# This authentic OOXML shape exceeds the old 6MB worksheet restriction, but
# the useful text remains small and is fully processed by the streaming reader.
sheet=('<worksheet><sheetData><row><c t="inlineStr"><is><t>Official tender text</t></is></c>'
       '</row></sheetData><!--'+(' '*6_100_000)+'--></worksheet>')
xlsx=archive({'xl/workbook.xml':'<workbook/>','xl/worksheets/sheet1.xml':sheet})
assert 'Official tender text' in r.extract('large.xlsx',xlsx)
# 1,214 ZIP members used to be rejected despite small decompressed payload.
many={'xl/workbook.xml':'<workbook/>',
      'xl/worksheets/sheet1.xml':'<worksheet><sheetData><row><c t="inlineStr"><is><t>Bid requirements</t></is></c></row></sheetData></worksheet>'}
for i in range(1212):many['xl/_rels/sheet'+str(i)+'.rels']='<Relationships/>'
assert 'Bid requirements' in r.extract('large-member-count.xlsx',archive(many))

# Never label a document fully reviewed if >1M chars exceed the scan cap.
over=archive({'xl/workbook.xml':'<workbook/>',
    'xl/worksheets/sheet1.xml':'<worksheet><sheetData><row><c t="inlineStr"><is><t>'+
        ('T'*1_000_100)+'</t></is></c></row></sheetData></worksheet>'})
try:r.extract('over-limit.xlsx',over)
except ValueError as err:assert str(err)=='source_text_scan_limit',str(err)
else:raise AssertionError('Over-limit source text silently passed')

print('WORKLINKS_REAL_FORMAT_RECURSION_AND_STREAMING_OOXML=PASS')
