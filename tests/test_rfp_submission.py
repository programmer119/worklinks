#!/usr/bin/env python3
"""Submission parser regression: source, timing, quantity and conservative defaults."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rfp_submission import extract_submission_items, submission_summary

def item(rows,name):
    return next((r for r in rows if r['label'].startswith(name)),None)

def test_bid_documents():
    text='입찰 시 제출서류: 제안서 6부, 입찰참가신청서 1부, 서약서 1부'
    rows,ok=extract_submission_items(text,'공고.pdf')
    assert ok
    assert item(rows,'제안서')['label']=='제안서 6부',rows
    assert item(rows,'입찰신청서')['stage']=='bid',rows
    assert item(rows,'서약서')['confidence']=='source',rows

def test_separate_stage():
    text='제출서류: 정성제안서 PDF, 정량제안서 PDF\n낙찰자만 제출: 별지 5~10\n발표 평가 시 제출: 발표자료 10부'
    rows,ok=extract_submission_items(text,'요청서.pdf')
    assert ok
    assert item(rows,'정성 PDF'),rows
    assert item(rows,'정량 PDF'),rows
    assert item(rows,'별지 5~10')['stage']=='post_award',rows
    assert item(rows,'발표자료')['stage']=='presentation',rows
    assert item(rows,'발표자료')['label']=='발표자료 10부',rows

def test_no_false_requirement():
    rows,_=extract_submission_items('평가항목: 제안서 평가 70점\n제안서 작성 방법 안내\n제출 불필요: 서약서','요청서.pdf')
    assert not rows,rows

def test_summary_preserves_source():
    rows,_=extract_submission_items('입찰 시 제출: 제안서 6부','요청서.pdf')
    summary=submission_summary({'files':[{'readable':True,'submissionItems':rows}]})
    assert summary[0]['sourceFile']=='요청서.pdf'
    assert summary[0]['label']=='제안서 6부'

if __name__=='__main__':
    test_bid_documents()
    test_separate_stage()
    test_no_false_requirement()
    test_summary_preserves_source()
    print('SUBMISSION_PARSER_REGRESSION=PASS')
