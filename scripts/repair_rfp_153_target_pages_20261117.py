#!/usr/bin/env python3
"""Source-scoped OCR recovery for exactly five pages of one SHA-verified G2B PDF.

This does not change scan status or claims of completeness. It only creates
durable page OCR receipts using the schema and reader version of the existing
RFP PDF reader. The ordinary original-file scanner must validate all pages
again before the notice may be marked complete.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

NOTICE = 'R26BK01774133:000'
EXPECTED_SHA = 'a3a2a016e774ea9de16b670e28fd279d8556af01cdf9539b283737ae8c0d306e'
TARGET_PAGES = (2, 5, 107, 130, 132)
DATA = Path('/app/data')


def valid_source(key, digest, pages):
    return key == NOTICE and digest == EXPECTED_SHA and pages == 153


def sufficient_text(value, *, tiled=False):
    alnum = sum(c.isalnum() for c in value)
    hangul = sum('가' <= c <= '힣' for c in value)
    return alnum >= (500 if tiled else 60) and hangul >= (100 if tiled else 10)


def render_and_ocr(page, *, dpi, clip=None, timeout=16):
    import pymupdf
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0),
        clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
    if pix.width * pix.height > 2_000_000:
        raise ValueError('scoped_render_pixel_cap_exceeded')
    run = subprocess.run(
        ['tesseract', 'stdin', 'stdout', '-l', 'kor+eng',
         '--psm', '11', '--dpi', str(dpi)],
        input=pix.tobytes('png'), capture_output=True, check=False,
        timeout=timeout, env=dict(os.environ, OMP_THREAD_LIMIT='1'))
    if run.returncode != 0:
        raise ValueError('scoped_ocr_nonzero_exit')
    return run.stdout.decode('utf-8', 'replace')


def page_text(page, number):
    if (page.get_text('text') or '').strip():
        raise ValueError('unexpected_native_text_in_scoped_drawing')
    if number in (107, 130, 132):
        value = render_and_ocr(page, dpi=90)
        if not sufficient_text(value):
            raise ValueError('scoped_fullpage_ocr_text_insufficient')
        return value, {'method': 'full-page-90dpi-psm11',
                       'tiles': 1, 'chars': len(value)}
    if number not in (2, 5):
        raise ValueError('page_not_in_scoped_target')
    import pymupdf
    rect = page.rect
    w = rect.width / 3.0
    h = rect.height / 3.0
    pieces = []
    tiles = []
    for row in range(3):
        for col in range(3):
            clip = pymupdf.Rect(
                max(rect.x0, rect.x0 + col*w - 9),
                max(rect.y0, rect.y0 + row*h - 9),
                min(rect.x1, rect.x0 + (col+1)*w + 9),
                min(rect.y1, rect.y0 + (row+1)*h + 9))
            text = render_and_ocr(page, dpi=110, clip=clip, timeout=12)
            alnum=sum(c.isalnum() for c in text)
            hangul=sum('가' <= c <= '힣' for c in text)
            if alnum < 35 or hangul < 8:
                raise ValueError('scoped_tile_text_insufficient_r%dc%d' % (row, col))
            pieces.append(text)
            tiles.append({'row': row, 'column': col,
                          'alnum': alnum, 'hangul': hangul})
    # All nine clips overlap by 9 pt so no drawing edge is omitted.
    # Do NOT deduplicate uncertain OCR by inventing text; preserve source order
    # and explicitly record the method separately for the operator.
    value = '\n'.join(pieces)
    if len(tiles) != 9 or not sufficient_text(value, tiled=True):
        raise ValueError('scoped_tiled_ocr_insufficient')
    return value, {'method': '3x3-110dpi-psm11-9pt-overlap',
                   'tiles': tiles, 'chars': len(value),
                   'overlapMayRepeatText': True}


def run(*, commit=False, data_dir=DATA):
    import pymupdf
    import refresh_worklinks_rfp as reader
    import repair_open_rfp_cached_attachments as repair
    data_dir=Path(data_dir)
    if reader.PDF_OCR_PAGE_CACHE_VERSION != 1:
        raise ValueError('reader_page_cache_version_mismatch')
    with sqlite3.connect('file:'+str(data_dir/'rfp-dual-queue.sqlite3')+'?mode=ro',
                         uri=True,timeout=12) as db:
        row=db.execute(
            'SELECT download_status,metadata_json FROM rfp_dual_notices WHERE notice_key=?',
            (NOTICE,)).fetchone()
    if not row or row[0] != 'ready':
        raise ValueError('source_not_verified_download_ready')
    metadata=json.loads(row[1])
    source=next(x for x in metadata['attachments']['items']
                if '공사도면_안산송산' in x['name'] and x['name'].endswith('.pdf'))
    receipt=next(x for x in metadata['downloadVerifiedFiles']
                 if x['url'] == source['url'])
    if receipt['sha256'] != EXPECTED_SHA:
        raise ValueError('source_sha_receipt_changed')
    raw,_=repair.fetch_verified_raw(
        source,data_dir/'rfp-request-ledger.sqlite3',EXPECTED_SHA)
    if len(raw)>reader.MAX_FILE or hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:
        raise ValueError('verified_original_bytes_changed')
    cache_path=data_dir/'rfp-ocr-page-cache.sqlite3'
    if not cache_path.is_file():
        raise ValueError('existing_ocr_cache_missing')
    with pymupdf.open(stream=raw,filetype='pdf') as pdf:
        if not valid_source(NOTICE,EXPECTED_SHA,pdf.page_count):
            raise ValueError('source_scope_mismatch')
        with sqlite3.connect(str(cache_path),timeout=25) as db:
            existing={n for (n,) in db.execute(
                'SELECT DISTINCT page_index FROM rfp_pdf_ocr_page_receipts '
                'WHERE pdf_sha256=? AND reader_version IN (?,?)',
                (EXPECTED_SHA,reader.PDF_OCR_PAGE_CACHE_VERSION,
                 reader.SPARSE_OCR_PAGE_CACHE_VERSION))}
        report={'notice':NOTICE,'sourceSHA':EXPECTED_SHA,'pages':[],
                'newReceipts':0,'commit':commit,
                'upstreamRequests':0}
        for n in TARGET_PAGES:
            if n-1 in existing:
                report['pages'].append({'page':n,'status':'existing_receipt'})
                continue
            try:
                started=time.monotonic()
                value,profile=page_text(pdf.load_page(n-1),n)
                result={'page':n,'status':'ocr_verified_for_cache',
                        'seconds':round(time.monotonic()-started,2),
                        **profile}
                if commit:
                    encoded=value.encode('utf-8')
                    with sqlite3.connect(str(cache_path),timeout=25) as db:
                        db.execute('PRAGMA busy_timeout=25000')
                        db.execute(
                            'INSERT OR IGNORE INTO rfp_pdf_ocr_page_receipts '
                            '(pdf_sha256,page_index,reader_version,text,text_sha256,stored_at) '
                            'VALUES(?,?,?,?,?,?)',
                            (EXPECTED_SHA,n-1,reader.PDF_OCR_PAGE_CACHE_VERSION,
                             value,hashlib.sha256(encoded).hexdigest(),
                             dt.datetime.now(dt.timezone.utc).isoformat()))
                        changed=db.execute('SELECT changes()').fetchone()[0]
                        db.commit()
                    result['status']='receipt_saved' if changed else 'existing_receipt'
                    report['newReceipts']+=changed
                report['pages'].append(result)
            except (ValueError,subprocess.TimeoutExpired) as err:
                report['pages'].append({'page':n,'status':'still_incomplete',
                                        'reason':type(err).__name__+':'+str(err)[:130]})
            print('SCOPED_153_PAGE',json.dumps(report['pages'][-1],ensure_ascii=False),flush=True)
        with sqlite3.connect('file:'+str(cache_path)+'?mode=ro',uri=True) as db:
            report['receiptsAfter']=db.execute(
                'SELECT COUNT(DISTINCT page_index) FROM rfp_pdf_ocr_page_receipts '
                'WHERE pdf_sha256=? AND reader_version IN (?,?)',
                (EXPECTED_SHA,reader.PDF_OCR_PAGE_CACHE_VERSION,
                 reader.SPARSE_OCR_PAGE_CACHE_VERSION)).fetchone()[0]
        print('SCOPED_153_RESULT',json.dumps(report,ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--commit',action='store_true')
    ap.add_argument('--data-dir',default=str(DATA))
    args=ap.parse_args()
    run(commit=args.commit,data_dir=args.data_dir)
