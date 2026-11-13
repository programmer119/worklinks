#!/usr/bin/env python3
"""One-shot OFFLINE source-backed staffing reparse of previously saved official RFPs.

Reads cumulative RFP index, rolling detail, and verified attachment-byte ledger.
Does NOT download, query any API, rescan missing source files, or invent headcounts.
Only writes a small per-notice patch and an audit report; caller merges atomically.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import zlib
from itertools import chain
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

from refresh_worklinks_rfp import (
    STAFFING_ROLE_SCAN_VERSION,
    STAFFING_ROLE_TEXT_LIMIT,
    extract_staffing_roles,
    extract_staffing_facts,
    extract_with_source_status,
    normalize_extracted_text,
    staffing_from_saved_excerpts,
    staffing_scan_pending,
)

# Give the visible, near-term tender cards first chance at cached source reparse.
PRIORITY = [
    'R26BK01807134:000',  # Yongin
    'R26BK01818412:000',  # LX platform
    'R26BK01797739:000',  # exercise system
    'R26BK01810095:001',  # Seoul energy
    'R26BK01813685:000',  # safety platform
]

def read_json(path, default):
    try:
        with open(path,encoding='utf-8') as stream:
            value=json.load(stream)
        return value if isinstance(value,dict) else default
    except (ValueError,OSError,TypeError):
        return default

def is_sha(value):
    return bool(re.fullmatch(r'[a-f0-9]{64}',str(value or ''),re.I))

def uniq_roles(rows):
    result=[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict):continue
        role=str(row.get('role') or '').strip()
        try:count=int(row.get('count'))
        except (ValueError,TypeError):continue
        if not role or not 1<=count<=99:continue
        signature=(role.casefold(),str(row.get('grade') or '').casefold(),
                   count,str(row.get('onsite') or ''),str(row.get('countKind') or 'specified'))
        if signature in seen:continue
        seen.add(signature)
        result.append({
            'role':role[:64],'grade':str(row.get('grade') or '')[:15],
            'count':count,'countKind':str(row.get('countKind') or 'specified')[:20],
            'onsite':str(row.get('onsite') or '')[:15],
            'manMonths':row.get('manMonths'),
            'sourceFile':str(row.get('sourceFile') or '')[:160],
            'sourceLine':int(row.get('sourceLine') or 0),
            'sourceText':str(row.get('sourceText') or '')[:240],
            'scope':str(row.get('scope') or 'excerpt')[:20],
            'sourceUrl':str(row.get('sourceUrl') or '')[:500]
                if str(row.get('sourceUrl') or '').startswith('https://www.g2b.go.kr/') else '',
        })
        if len(result)>=24:break
    return result

def run(index_path, detail_path, ledger_path, patch_path, report_path,
        max_files=120, max_seconds=700, priority_only=False):
    started=time.monotonic()
    snapshot=read_json(index_path,{})
    index=snapshot.get('byNotice') or {}
    if snapshot.get('ok') is not True or not isinstance(index,dict) or not index:
        raise ValueError('RFP_INDEX_NOT_FOUND_OR_EMPTY')
    detailed=read_json(detail_path,{}).get('byNotice') or {}
    by_sha={}
    before_evidence=sum(bool(v.get('staffingRoles')) for v in index.values() if isinstance(v,dict))
    before_complete=sum(v.get('staffingRoleScanComplete') is True for v in index.values() if isinstance(v,dict))
    eligible_records=0
    missing_sha=0
    for key,row in index.items():
        if not isinstance(row,dict):continue
        if priority_only and key not in PRIORITY:continue
        if row.get('status')!='text_extracted_requires_review':continue
        if row.get('staffingRoleScanComplete') is True and not staffing_scan_pending(row):continue
        eligible_records+=1
        for position,f in enumerate(row.get('files') or []):
            if not isinstance(f,dict) or f.get('readable') is not True:continue
            sha=str(f.get('sourceSha256') or '').lower()
            if not is_sha(sha):
                missing_sha+=1
                continue
            by_sha.setdefault(sha,[]).append((key,position,str(f.get('name') or '')))
    old_sha=set(by_sha)
    candidates={}
    for sha, refs in by_sha.items():
        candidates[sha]=sorted(refs,key=lambda r:
            (0 if r[0] in PRIORITY else 1,PRIORITY.index(r[0])
                if r[0] in PRIORITY else 999, r[0],r[1]))
    all_priority={ref[0] for refs in candidates.values() for ref in refs if ref[0] in PRIORITY}
    # Query SHA fingerprints via SQLite without any CallLedger methods (which
    # would append audit writes). The verified raw bytes are never exported.
    if not ledger_path.is_file():
        raise ValueError('RFP_LEDGER_FILE_MISSING')
    uri='file:'+str(ledger_path.resolve())+'?mode=ro'
    db=sqlite3.connect(uri,uri=True,timeout=30)
    db.execute('PRAGMA query_only=ON')
    source_count=int(db.execute("SELECT COUNT(*) FROM verified_cache WHERE media_type='bytes'").fetchone()[0])
    available=set()
    for (sha,) in db.execute("SELECT sha256 FROM verified_cache WHERE media_type='bytes'"):
        if sha in candidates:available.add(sha)
    selected=sorted(available,key=lambda sha: (
        0 if any(row[0] in PRIORITY for row in candidates[sha]) else 1,
        min([PRIORITY.index(row[0]) for row in candidates[sha] if row[0] in PRIORITY] or [999]),
        sha))
    # Avoid a table scan per file: single streaming pass, with a bounded
    # verified candidate dictionary. Parsed text is never persisted wholesale.
    target=set(selected)
    scanned={}
    failures={}
    processed_sha=set()
    total_files=0
    cached_binary_match=0
    # A streaming cache table is stored in insertion order; explicitly fetch
    # priority notices FIRST, or they can be starved by the max-files budget.
    urgent_sha=[sha for sha in selected if any(ref[0] in PRIORITY for ref in candidates[sha])]
    urgent_rows=[]
    for sha in urgent_sha:
        row=db.execute("SELECT sha256,payload FROM verified_cache WHERE media_type='bytes' AND sha256=? LIMIT 1",
                       (sha,)).fetchone()
        if row:urgent_rows.append(row)
    source_rows=chain(urgent_rows,
        db.execute("SELECT sha256,payload FROM verified_cache WHERE media_type='bytes'"))
    for sha,payload in source_rows:
        if sha not in target or sha in processed_sha:continue
        if total_files>=max_files or time.monotonic()-started>max_seconds:break
        processed_sha.add(sha)
        try:
            raw=zlib.decompress(payload)
            if len(raw)>12_000_000 or hashlib.sha256(raw).hexdigest()!=sha:
                raise ValueError('cached_binary_integrity_mismatch')
        except Exception as exc:
            failures[sha]=type(exc).__name__+':'+str(exc)[:90]
            continue
        cached_binary_match+=1
        by_ext={}
        for key,position,name in candidates[sha]:
            if total_files>=max_files or time.monotonic()-started>max_seconds:break
            ext=Path(name).suffix.lower()
            if ext not in by_ext:
                try:
                    parsed,evidence=extract_with_source_status(name,raw)
                    text=normalize_extracted_text(parsed)
                    if not evidence.get('sourceComplete'):
                        raise ValueError('source_ocr_or_extraction_incomplete')
                    by_ext[ext]=(text,None)
                except Exception as exc:
                    by_ext[ext]=(None,type(exc).__name__+':'+str(exc)[:95])
            text,error=by_ext[ext]
            if error:
                failures[key+'#'+str(position)]=error
                continue
            role_rows=extract_staffing_roles(text,name)
            fact_rows=extract_staffing_facts(text,name)
            proof=next((f for f in (detailed.get(key) or {}).get('files',[])
                if f.get('name')==name and f.get('sourceSha256')==sha),{})
            url=str(proof.get('sourceUrl') or '')
            if not url.startswith('https://www.g2b.go.kr/'):url=''
            for row in role_rows+fact_rows:
                row['sourceUrl']=url
            scanned[(key,position)]=dict(rows=role_rows,facts=fact_rows,truncated=len(text)>STAFFING_ROLE_TEXT_LIMIT)
            total_files+=1
        del raw
        if total_files%20==0 and total_files:
            print('STAFFING_REPARSE_PROGRESS',total_files,'roles_found_in_files',
                  sum(bool(v['rows']) for v in scanned.values()),flush=True)
    db.close()
    updates={}
    affected={}
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    for key,row in index.items():
        if not isinstance(row,dict):continue
        files=row.get('files') or []
        performed=[scanned.get((key,i)) for i in range(len(files))]
        if not any(performed):continue
        new_roles=[]
        new_facts=[]
        for info in performed:
            if info:
                new_roles.extend(info['rows'])
                new_facts.extend(info['facts'])
        previous=uniq_roles(row.get('staffingRoles') or [])
        roles=uniq_roles(new_roles+previous)
        prior_facts=[x for x in row.get('staffingFacts') or [] if isinstance(x,dict)]
        facts=[]
        seen_facts=set()
        for fact in new_facts+prior_facts:
            if not isinstance(fact,dict) or not fact.get('kind') or not fact.get('sourceText'):
                continue
            signature=(str(fact.get('kind')),str(fact.get('role')),
                       str(fact.get('manMonths')),str(fact.get('sourceText')))
            if signature in seen_facts:continue
            seen_facts.add(signature)
            facts.append(fact)
            if len(facts)>=35:break
        # HWP counterpart deliberately skipped as a different format does not
        # prove identical legal content, so do not certify a full-document scan.
        complete=bool(row.get('manifestComplete') is True and len(files)>0 and
            all(isinstance(f,dict) and f.get('readable') is True and
                (scanned.get((key,i)) is not None and
                 not scanned[(key,i)]['truncated'])
                for i,f in enumerate(files)))
        updates[key]={
            'staffingRoles':roles,
            'staffingFacts':facts,
            'staffingRoleScanComplete':complete,
            'staffingCachedReparseFiles':sum(bool(x) for x in performed),
            'staffingCachedReparseAt':now,
            'staffingCachedReparseVersion':STAFFING_ROLE_SCAN_VERSION,
        }
        affected[key]={
            'scanned':sum(bool(x) for x in performed),
            'files':len(files),
            'roles':len(roles),'facts':len(facts),'full':complete,
        }
    after_evidence=sum(bool(updates.get(key,{}).get('staffingRoles',row.get('staffingRoles')))
        for key,row in index.items() if isinstance(row,dict))
    after_complete=sum((updates.get(key,{}).get('staffingRoleScanComplete',
        row.get('staffingRoleScanComplete')) is True)
        for key,row in index.items() if isinstance(row,dict))
    report={
        'ok':True,'kind':'cached_offline_staffing_reparse',
        'at':now,'governmentApiCalls':0,'officialFileDownloads':0,
        'scannedNotices':len(index),'eligibleForReparse':eligible_records,
        'cacheBinaryEntries':source_count,
        'noticeSourceShaCandidates':len(old_sha),
        'sourceShaMatchingCache':len(available),
        'sourceShaMissingCache':len(old_sha-available),
        'eligibleFilesMissingSha':missing_sha,
        'matchingCacheBinariesProcessed':cached_binary_match,
        'filesReparsed':total_files,'noticePatches':len(updates),
        'withRoleEvidenceBefore':before_evidence,'withRoleEvidenceAfter':after_evidence,
        'fullStaffingScanBefore':before_complete,'fullStaffingScanAfter':after_complete,
        'priorityNoticesInArchive':sorted(k for k in PRIORITY if k in index),
        'priorityNoticesWithAvailableBinary':sorted(all_priority),
        'priorityResults':{k:{'state':'cached_reparsed' if k in updates else
                            'no_matching_binary_or_scan_not_finished',
                              **affected.get(k,{})} for k in PRIORITY if k in index},
        'sampleVerifiedRoles':[
            {'notice':k,'roles':[dict(role=r['role'],count=r['count'],
              sourceFile=r['sourceFile'],sourceText=r['sourceText'][:140])
              for r in u['staffingRoles'][:4]]}
            for k,u in updates.items() if u['staffingRoles']][:12],
        'failureByReason':{},
        'elapsedSeconds':round(time.monotonic()-started,1),
    }
    for reason in failures.values():
        report['failureByReason'][reason]=report['failureByReason'].get(reason,0)+1
    patch_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.parent.mkdir(parents=True,exist_ok=True)
    fingerprints={key:[(str(f.get('name') or ''),str(f.get('sourceSha256') or ''))
        for f in (index[key].get('files') or [])]
        for key in updates}
    patch_path.write_text(json.dumps({'ok':True,'baseGeneratedAt':snapshot.get('generatedAt'),
        'sourceKeys':len(index),'fingerprints':fingerprints,
        'updates':updates},ensure_ascii=False,separators=(',',':'))+'\n')
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('STAFFING_REPARSE_REPORT',json.dumps(report,ensure_ascii=False),flush=True)
    if not total_files:
        print('STAFFING_ZERO_CACHED_FILES_REPARSED: only existing excerpts may be available',flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--index',required=True,type=Path)
    p.add_argument('--detail',required=True,type=Path)
    p.add_argument('--ledger',required=True,type=Path)
    p.add_argument('--patch',required=True,type=Path)
    p.add_argument('--report',required=True,type=Path)
    p.add_argument('--max-files',type=int,default=120)
    p.add_argument('--max-seconds',type=int,default=700)
    p.add_argument('--priority-only',action='store_true')
    a=p.parse_args()
    run(a.index,a.detail,a.ledger,a.patch,a.report,
        max(1,min(a.max_files,500)),max(20,min(a.max_seconds,1800)),a.priority_only)

if __name__=='__main__':main()
