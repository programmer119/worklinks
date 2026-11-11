#!/usr/bin/env python3
"""No-network RFP repair: a failed sibling must not redownload a good file."""
import pathlib
import runpy

module=runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1]/
                        'scripts/refresh_worklinks_rfp.py'),run_name='rfp_partial_test')
process=module['process']
g=process.__globals__
good='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/good'
missing='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/retry'
prev={'classificationVersion':module['CLASSIFICATION_VERSION'],
      'hwpxReaderVersion':module['HWPX_READER_VERSION'],
      'files':[{'name':'original.pdf','sourceUrl':good,'readable':True,
                'sourceSha256':'e'*64,'textSha256':'f'*64,
                'clauseCandidates':[{'type':'industry_code',
                                     'sourceText':'정보시스템 업종 1468'}]},
               {'name':'retry.pdf','sourceUrl':missing,'readable':False,
                'errorCategory':'file_download_http_503'}]}
meta={'attachments':{'ok':True,'complete':True,'count':2,'eorderCount':0,
                     'items':[{'name':'original.pdf','url':good},
                              {'name':'retry.pdf','url':missing}]},
      'noticeDocuments':{'ok':True,'complete':True,'items':[]}}
calls=[]
original_download=g['download']
original_extract=g['extract']
try:
    def fake_download(url):
        calls.append(url)
        return b'valid-pdf-binary'
    g['download']=fake_download
    g['extract']=lambda name,raw: ('입찰 참가 자격 업종 1468 직접생산 확인. '*10)
    repaired=process('R26BK01816467','000',meta,prev)
    assert calls==[missing],calls
    assert repaired['readableDocumentCount']==2,repaired
    assert repaired['files'][0]['sourceSha256']=='e'*64
    assert repaired['files'][1]['sourceSha256']!='e'*64
    # A changed attachment URL is not the same official file, so do not reuse.
    changed='https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/newrevision'
    meta['attachments']['items'][0]['url']=changed
    calls.clear()
    process('R26BK01816467','000',meta,prev)
    assert calls==[changed,missing],calls
    print('RFP_PARTIAL_ATTACHMENT_REUSE_NO_NETWORK=PASS')
finally:
    g['download']=original_download
    g['extract']=original_extract
