#!/usr/bin/env python3
"""Regression: truthful source-reading progress and bounded complete OOXML."""
import io
import os
import pathlib
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import rfp_live_activity as live
import refresh_worklinks_rfp as rfp


def office_xml(chars):
    rowtext='A'*4096
    count=(chars+4095)//4096
    rows=''.join(
        '<row><c t="inlineStr"><is><t>'+rowtext+'</t></is></c></row>'
        for _ in range(count))
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/workbook.xml','<workbook/>')
        archive.writestr('xl/worksheets/sheet1.xml',
                         '<worksheet>'+rows+'</worksheet>')
    return raw.getvalue()


def test_full_source_ceiling():
    assert rfp.RFP_QUALIFICATION_TEXT_LIMIT == 4_000_000
    verified=rfp.extract_office_xml_stream(office_xml(1_050_000),'.xlsx')
    assert len(verified)>1_000_000
    assert len(verified)<=rfp.RFP_QUALIFICATION_TEXT_LIMIT
    assert verified[-8:] == 'A'*8
    # Do not silently skip unprocessed XML rows or claim partial scan success.
    try:
        rfp.extract_office_xml_stream(office_xml(4_100_000),'.xlsx')
    except ValueError as error:
        assert str(error)=='source_text_scan_limit',error
    else:
        raise AssertionError('oversized source was improperly considered complete')


def test_scan_file_lifecycle():
    with tempfile.TemporaryDirectory() as directory:
        filename=str(pathlib.Path(directory)/'activities.sqlite3')
        os.environ['WORKLINKS_RFP_DUAL_QUEUE_DB']=filename
        key='R26BK01767174:000'
        other='R26BK01817748:000'
        with live.connect(filename) as db:
            db.execute('CREATE TABLE rfp_dual_notices(notice_key TEXT PRIMARY KEY, scan_status TEXT)')
            db.executemany('INSERT INTO rfp_dual_notices VALUES (?,?)',
                           [(key,'retry'),(other,'scanning')])
        live.record('scan',key,file_key='f1',file_name='old.hwp',
                    phase='텍스트 추출 준비',status='working')
        live.record('scan',other,file_key='f2',file_name='live.hwp',
                    phase='텍스트 추출',status='working')
        view=live.snapshot(filename)
        assert not any(i['noticeKey']==key and i['status']=='working'
                       for i in view['items']),view
        assert any(i['noticeKey']==other and i['status']=='working'
                   for i in view['items']),view
        # Starting an attempt retires all historical working files first.
        with live.connect(filename) as db:
            db.execute("UPDATE rfp_dual_notices SET scan_status='scanning' WHERE notice_key=?",(key,))
        assert live.begin_scan_notice(key)==1
        live.record('scan',key,file_key='f3',file_name='new.hwp',
                    phase='텍스트 추출',status='working')
        live.record('scan',key,file_key='e1',file_name='broken.pdf',
                    phase='판독 오류',status='retry',error='pdf_ocr_incomplete')
        assert live.finish_scan_notice(key)==1
        with live.connect(filename) as db:
            events=db.execute('SELECT file_key,status,error_text FROM rfp_live_events WHERE notice_key=?',(key,)).fetchall()
        bykey={row[0]:(row[1],row[2]) for row in events}
        assert bykey['f1'][0]=='skipped'
        assert bykey['f3'][0]=='skipped'
        assert bykey['e1']==('retry','pdf_ocr_incomplete')
        # A stale scan event cannot survive when the durable scan queue exits.
        with live.connect(filename) as db:
            db.execute("UPDATE rfp_dual_notices SET scan_status='retry' WHERE notice_key=?",(key,))
        view=live.snapshot(filename)
        assert not any(i['noticeKey']==key and i['status']=='working'
                       for i in view['items'])


if __name__ == '__main__':
    test_full_source_ceiling()
    test_scan_file_lifecycle()
    print('RFP_LARGE_SOURCE_AND_ACTIVITY_LIFECYCLE=PASS',flush=True)
