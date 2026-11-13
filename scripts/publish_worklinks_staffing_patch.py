#!/usr/bin/env python3
"""Atomically merge verified offline staffing results without losing RFP history.

This has NO network I/O and does not label an ambiguous staff count as verified.
"""
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import re
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from staffing_facts import STAFF_REQUIREMENT_PATTERNS

_CONFUSING_ROLE=re.compile(r'전담\s*유지\s*보수|별도의?\s*담당자|기타\s*인력|부문별\s*대표자')
_OBVIOUS_SCORE=re.compile(r'평가\s*항목|평가\s*기준|배\s*점|점수|점\s*이상|산술한\s*수치')
ROLE_NUMBER_RE=re.compile(r'([1-9]\d?)\s*(?:명|인)(?=\s|$|[.,()·:;]|이상|이하|투입|상주)')

def defensible_staffing_row(item):
    """Require directly paired explicit persons or unambiguous 3-column row."""
    text=' '.join(str(item.get('sourceText') or '').split())
    role=' '.join(str(item.get('role') or '').split())
    try:count=int(item.get('count'))
    except (TypeError,ValueError):return False
    if not role or count<1 or count>99 or not text:return False
    if _OBVIOUS_SCORE.search(text) and ('|' in text or role=='기술자'):
        return False
    pair=re.search(re.escape(role)+r'(.{0,52}?)'+
                   re.escape(str(count))+r'\s*(?:명|인)(?=\s|$|[.,()·:;]|이상|이하|투입|상주)',text,re.I)
    if pair:
        middle=pair.group(1)
        # The number can belong to a DIFFERENT role referenced after this one.
        if _CONFUSING_ROLE.search(middle):return False
        if len(middle)>32 and not re.search(r'최소|이상|투입|필요|배치',middle):
            return False
        return True
    # Avoid annex numbers, year-of-experience values, MM and evaluation scores.
    # A tabular bare integer requires role, grade and 3 pipe-delimited cells.
    if re.fullmatch(re.escape(role)+r'\s+(?:특급|고급|중급|초급)\s+'+str(count),text):
        return True
    if len(text)>110 or text.count('|')<2 or re.search(r'경력|별지|서식|항목|번호|평가|점|년',text):
        return False
    segments=[x.strip() for x in text.split('|')]
    if len(segments)!=3 or not re.search(r'특급|고급|중급|초급',segments[1]):return False
    return (role in segments[0] and
            re.fullmatch(r'[1-9]\d?',segments[-1]) is not None and
            int(segments[-1])==count)

def defensible_staffing_fact(fact):
    """Guard headcount semantics before publishing cached source-derived facts."""
    if not isinstance(fact,dict):return False
    kind=str(fact.get('kind') or '')
    quote=' '.join(str(fact.get('sourceText') or '').split())
    file=str(fact.get('sourceFile') or '')
    if not quote or not file or len(quote)>240:return False
    if re.search(r'산정\s*예시|평가\s*배점|평가\s*점수',quote):return False
    if kind=='workload_role':
        try:
            months=float(fact['durationMonths'])
            rate=float(fact['allocationRate'])
            mm=float(fact['manMonths'])
        except (ValueError,TypeError,KeyError):return False
        return bool(fact.get('role') and fact.get('headcount') is None and
                    0<months<=36 and 0<=rate<=1 and
                    abs(months*rate-mm)<=0.0011)
    if kind=='workload_total':
        try:mm=float(fact['manMonths'])
        except (TypeError,ValueError,KeyError):return False
        return 0<mm<1000 and '총 투입공수' in quote
    if kind=='headcount_recommended':
        return bool(fact.get('mandatory') is False and
                    fact.get('minimum') is True and
                    isinstance(fact.get('count'),int) and
                    1<=fact['count']<=99 and
                    '권고' in quote)
    if kind=='staffing_plan_required':
        return fact.get('headcount') is None and fact.get('mandatory') is True
    if kind=='role_unspecified':
        return bool(fact.get('role') and fact.get('headcount') is None)
    if kind=='staffing_requirement':
        # A label without the corresponding official clause is NOT evidence.
        # Re-run the exact generic source clause matcher before publication.
        kind_label=str(fact.get('requirementType') or '')
        label=str(fact.get('label') or '')
        return (fact.get('headcount') is None and
                int(fact.get('sourceLine') or 0)>0 and
                any(kind_label==t and label==name and pattern.search(quote)
                    for t,name,pattern in STAFF_REQUIREMENT_PATTERNS))
    return False


def unique_facts(rows):
    result=[]
    seen=set()
    for fact in rows:
        if not defensible_staffing_fact(fact):continue
        key=(str(fact.get('kind')),str(fact.get('sourceFile')),
             str(fact.get('role')),str(fact.get('manMonths')),
             str(fact.get('sourceText')))
        if key in seen:continue
        seen.add(key)
        result.append(fact)
        if len(result)>=35:break
    return result


def unique_rows(rows):
    unique=[]
    seen=set()
    for item in rows:
        if not isinstance(item,dict):continue
        try:count=int(item.get('count'))
        except (TypeError,ValueError):continue
        k=(str(item.get('role') or '').strip().lower(),str(item.get('grade') or ''),
           count,str(item.get('onsite') or ''),str(item.get('countKind') or ''))
        if k in seen:continue
        seen.add(k)
        unique.append(item)
        if len(unique)>=24:break
    return unique

def merge(index_path,patch_paths,report_paths):
    index_path=Path(index_path)
    original=json.loads(index_path.read_text(encoding='utf-8'))
    if not isinstance(original.get('byNotice'),dict) or original.get('ok') is not True:
        raise RuntimeError('INVALID_LIVE_COVERAGE_INDEX')
    entries=original['byNotice']
    keys_before=set(entries)
    patches=[json.loads(Path(p).read_text()) for p in patch_paths]
    reports=[json.loads(Path(p).read_text()) for p in report_paths]
    modified=set()
    skipped=0
    retained=0
    rejected=0
    for patch in patches:
        if patch.get('ok') is not True or not patch.get('updates'):
            continue
        for key,new in patch['updates'].items():
            old=entries.get(key)
            if not isinstance(old,dict):
                skipped+=1;continue
            signature=[(str(f.get('name') or ''),str(f.get('sourceSha256') or ''))
                       for f in old.get('files',[])]
            if signature!=[tuple(f) for f in patch.get('fingerprints',{}).get(key,[])]:
                skipped+=1;continue
            prior=unique_rows(old.get('staffingRoles') or [])
            proposed=unique_rows(new.get('staffingRoles') or [])
            trusted=[row for row in proposed if defensible_staffing_row(row)]
            rejected+=len(proposed)-len(trusted)
            retained+=len(trusted)
            old['staffingRoles']=unique_rows(trusted+prior)
            old['staffingFacts']=unique_facts(
                (new.get('staffingFacts') or [])+(old.get('staffingFacts') or []))
            old['staffingRoleScanComplete']=bool(
                old.get('staffingRoleScanComplete') is True or
                new.get('staffingRoleScanComplete') is True)
            # Exactly those verified readable attachments reparsed from
            # SHA-matched local bytes advance the independent fact version.
            for index,version in (new.get('staffingFactScanVersions') or {}).items():
                try:position=int(index)
                except (TypeError,ValueError):continue
                files=old.get('files') or []
                if 0<=position<len(files) and files[position].get('readable') is True:
                    files[position]['staffingFactScanVersion']=int(version)
            for field in ('staffingCachedReparseFiles','staffingCachedReparseAt',
                          'staffingCachedReparseVersion'):
                if field in new:old[field]=new[field]
            modified.add(key)
    assert set(entries)==keys_before
    assert len(entries)>=3500
    before=sum(bool(v.get('staffingRoles')) for v in entries.values() if isinstance(v,dict))
    complete=sum(v.get('staffingRoleScanComplete') is True for v in entries.values() if isinstance(v,dict))
    if modified:
        original['generatedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
        payload=(json.dumps(original,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        assert len(payload)<95_000_000
        with tempfile.NamedTemporaryFile(dir=index_path.parent,delete=False,
                                         prefix='.staffing-bak-') as temp:
            temp.write(payload)
            staged=Path(temp.name)
        stage_gz=Path(str(staged)+'.gz')
        with gzip.open(stage_gz,'wb',compresslevel=6) as stream:
            stream.write(payload)
        os.replace(staged,index_path)
        os.replace(stage_gz,Path(str(index_path)+'.gz'))
    result={'ok':True,'published':len(modified),'sourceChangedSkipped':skipped,
            'proposedRows':retained+rejected,'trustedRows':retained,
            'rejectedAmbiguousRows':rejected,'archiveNotices':len(entries),
            'withStaffingEvidence':before,'fullStaffingScans':complete,
            'governmentApiCalls':0,'newOfficialDownloads':0}
    for path in report_paths:
        report=json.loads(Path(path).read_text())
        report.update(publishedAt=original.get('generatedAt'),
                      postMerge=result)
        Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('OFFLINE_STAFFING_PUBLISHED',json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--index',required=True)
    p.add_argument('--patch',action='append',required=True)
    p.add_argument('--report',action='append',required=True)
    args=p.parse_args()
    if len(args.patch)!=len(args.report):raise SystemExit('PATCH_REPORT_COUNT_MISMATCH')
    merge(args.index,args.patch,args.report)

if __name__=='__main__':main()
