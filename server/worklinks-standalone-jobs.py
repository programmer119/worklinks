#!/usr/bin/env python3
"""Independent WorkLinks server123 source-poll, QA and scheduled public-data jobs.

This daemon does not use GitHub Actions and NEVER pushes data to GitHub.
Source comes from read-only Git, output lives in the existing durable snapshot
directory and is served without extra procurement API calls.
"""
import datetime as dt
import fcntl
import gzip
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

DATA=Path(os.environ.get('WORKLINKS_DATA','/app/data'))
SRC=DATA/'standalone-worktree'
SNAP=Path(os.environ.get('WORKLINKS_SNAPSHOT_DIR',str(DATA/'snapshots')))
STATE=DATA/'standalone-jobs-state.json'
LOCK=DATA/'standalone-jobs.lock'
REPO_URL=os.environ.get('WORKLINKS_SOURCE_REPO','https://github.com/programmer119/worklinks.git')
CHROMIUM=os.environ.get('WORKLINKS_CHROMIUM_PATH','/usr/bin/chromium')

# Source collectors must be independent of the browser and authenticated UI.
JOBS={
    'localBudget':{'period':3600,'timeout':1140,'script':'worklinks_local_budget.py',
                   'output':'year-end-local-budget.json'},
    'changcom200':{'period':10800,'timeout':240,'script':'build_changcom_200_source_audit.py',
                    'output':'audits/changcom-200-official-evidence-20261111.csv'},
    'kimseDeep':{'period':43200,'timeout':1980,'script':'worklinks_kimse_deep_audit.py',
                 'output':'kimse-deep-audit.json'},
    'investment':{'period':43200,'timeout':1560,'script':'refresh_worklinks_investment.py',
                  'output':'investment-opportunities.json'},
    'healthLive':{'period':43200,'timeout':340,'script':'worklinks_health_live_audit.py',
                  'output':'health-live-audit.json','stdout':True},
    'smeCert':{'period':86400,'timeout':420,'script':'worklinks_sme_cert_snapshot.py',
              'output':'sme-cert-snapshot.json'},
    'directProduction':{'period':2592000,'timeout':600,
                        'script':'worklinks_direct_production_snapshot.py',
                        'output':'direct-production-snapshot.json'}
}
SEED_FILES=('startup-support/index.html',
            'startup-support/investment-opportunities.json',
            'startup-support/year-end-local-budget.json',
            'startup-support/kimse-deep-audit.json',
            'startup-support/sme-cert-snapshot.json',
            'startup-support/direct-production-snapshot.json',
            'startup-support/audits/changcom-200-screening-20261110.csv',
            'startup-support/audits/changcom-200-personnel-blockers-20261110.csv')
CI_TESTS=(
    ('python','-m','py_compile',
     'server/g2b-proxy.py',
     'server/worklinks-server123-pipeline.py',
     'server/worklinks-standalone-jobs.py',
     'scripts/refresh_worklinks_investment.py',
     'scripts/worklinks_local_budget.py',
     'scripts/worklinks_kimse_deep_audit.py',
     'scripts/worklinks_sme_cert_snapshot.py',
     'scripts/worklinks_direct_production_snapshot.py'),
    ('python','tests/test_worklinks_local_budget.py'),
    ('python','tests/test_worklinks_open_award_fallback.py'),
    ('python','tests/test_worklinks_server123_pipeline.py'),
    ('python','tests/test_rfp_failures.py'),
    ('python','tests/test_worklinks_standalone_jobs.py'),
    ('python','tests/test_worklinks_site_mirror.py'),
    ('node','tests/worklinks-jobs-regression.cjs'),
)

# Former GitHub push-triggered gates. These remain independently visible but
# cannot suppress unrelated collection because a third-party website is down.
SUPPLEMENTAL_QA=(
 ('python','tests/test_worklinks_user_state.py'),
 ('python','tests/test_worklinks_priority_health.py'),
 ('python','tests/test_worklinks_health_sources.py'),
 ('python','tests/test_worklinks_kimse_deep_audit.py'),
 ('python','tests/test_dynamic_sources.py'),
 ('python','tests/test_investment_monitor.py'),
 ('python','tests/test_global_accelerators.py'),
 ('python','tests/test_kised.py'),
 ('python','tests/test_worklinks_kimse_merge_audit.py'),
 ('python','tests/test_worklinks_rfp_coverage.py'),
 ('python','tests/test_bid_evidence.py'),
 ('python','tests/test_g2b_eligibility_worker.py'),
 ('node','tests/test_worklinks_kimse_intake.cjs'),
 ('node','tests/test_worklinks_support_sort.cjs'),
 ('python','tests/test_worklinks_mobile_bootstrap.py'),
 ('python','tests/test_worklinks_guest_auto_migration.py'),
 ('python','tests/test_worklinks_live_auth_state_api.py'),
 ('python','tests/test_worklinks_user_state.py'),
)

def log(*args):
    print(dt.datetime.now(dt.timezone.utc).isoformat(),*args,flush=True)

def write_atomic(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.'+path.name+'.writing')
    try:
        tmp.write_bytes(body)
        os.replace(tmp,path)
    finally:
        try:tmp.unlink()
        except FileNotFoundError:pass

def state_load():
    try:
        data=json.loads(STATE.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}

def state_save(data):
    write_atomic(STATE,(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode())

def call(cmd,cwd=None,timeout=60,env=None):
    return subprocess.run(cmd,cwd=cwd,timeout=timeout,capture_output=True,text=True,env=env)

def source_head():
    p=call(['git','rev-parse','HEAD'],cwd=str(SRC),timeout=15)
    return p.stdout.strip() if p.returncode==0 else ''

def test_source(root):
    """Run source checks on change; never publish collector results from failed QA."""
    result=[]
    for command in CI_TESTS:
        cmd=[sys.executable if x=='python' else x for x in command]
        try:
            p=call(cmd,cwd=str(root),timeout=160)
            result.append({'command':command[1] if len(command)>1 else command[0],
                           'ok':p.returncode==0,'tail':(p.stderr or p.stdout)[-240:]})
            if p.returncode!=0:
                return False,result
        except (OSError,subprocess.TimeoutExpired) as exc:
            result.append({'command':str(command[0]),'ok':False,'error':type(exc).__name__})
            return False,result
    return True,result

def test_diagnostics(root, commands):
    checks=[]
    for command in commands:
        argv=[sys.executable if x=='python' else x for x in command]
        if not (root/command[1]).is_file():
            checks.append({'name':command[1],'ok':False,'error':'test_source_missing'})
            continue
        try:
            result=call(argv,cwd=str(root),timeout=100)
            checks.append({'name':command[1],'ok':result.returncode==0,
                           'tail':(result.stderr or result.stdout)[-180:]})
        except (OSError,subprocess.TimeoutExpired) as err:
            checks.append({'name':command[1],'ok':False,
                           'error':type(err).__name__})
    return checks

def update_source():
    """Read-only GitHub source synchronization; no credentials or git pushes."""
    if not (SRC/'.git').is_dir():
        if SRC.exists() and any(SRC.iterdir()):
            raise RuntimeError('source_directory_nonempty_without_git')
        SRC.parent.mkdir(parents=True,exist_ok=True)
        p=call(['git','clone','--depth','2','--single-branch','--branch','main',REPO_URL,str(SRC)],
               timeout=240)
        if p.returncode:raise RuntimeError('source_clone_failed_'+p.stderr[-170:])
        return True,source_head()
    before=source_head()
    p=call(['git','fetch','--depth','2','origin','main'],cwd=str(SRC),timeout=130)
    if p.returncode:raise RuntimeError('source_fetch_failed_'+p.stderr[-170:])
    target=call(['git','rev-parse','FETCH_HEAD'],cwd=str(SRC),timeout=12).stdout.strip()
    if not target or target==before:return False,before
    p=call(['git','reset','--hard',target],cwd=str(SRC),timeout=100)
    if p.returncode:raise RuntimeError('source_checkout_failed')
    return True,target

def prepare_workspace(tmp):
    root=Path(tmp)/'worklinks'
    (root/'scripts').mkdir(parents=True)
    (root/'startup-support').mkdir(parents=True)
    shutil.copytree(SRC/'scripts',root/'scripts',dirs_exist_ok=True)
    for name in SEED_FILES:
        original=SRC/name
        if original.is_file():
            dest=root/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(original,dest)
    # Live server snapshots always supersede stale GitHub seed snapshots.
    for info in JOBS.values():
        name=info['output']
        source=SNAP/name
        if source.is_file():
            target=root/'startup-support'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
    coverage=SNAP/'rfp-coverage-index.json'
    if coverage.is_file():
        shutil.copy2(coverage,root/'startup-support/rfp-coverage-index.json')
    return root

def validate(job,data):
    """A failed or partial source response is NEVER equivalent to zero notices."""
    if not isinstance(data,dict):
        raise ValueError('output_not_object')
    if job=='localBudget':
        if not isinstance(data.get('opportunities'),list) or not isinstance(data.get('stats'),dict):
            raise ValueError('invalid_local_budget')
        sources=data.get('sources') or []
        if not any(isinstance(x,dict) and x.get('status') in ('ok','partial') for x in sources):
            raise ValueError('all_local_budget_sources_failed')
    elif job=='investment':
        if data.get('schemaVersion')!=1 or not isinstance(data.get('opportunities'),list):
            raise ValueError('invalid_investment_snapshot')
        sources=data.get('sources') or []
        if not any(isinstance(x,dict) and x.get('status') in ('ok','partial') for x in sources):
            raise ValueError('all_investment_sources_failed')
    elif job=='kimseDeep':
        summary=data.get('summary') or {}
        if int(summary.get('sources') or 0)!=10:
            raise ValueError('kimse_deep_sources_not_exhaustive')
        if not isinstance(data.get('audits'),list) and not isinstance(data.get('sources'),list):
            raise ValueError('kimse_deep_shape_missing')
    elif job=='healthLive':
        coverage=data.get('coverage') or {}
        if not isinstance(data.get('results'),list) or coverage.get('listingDegraded'):
            raise ValueError('health_official_lists_degraded')
    elif job=='smeCert':
        if data.get('ok') is not True or not isinstance(data.get('recordsByBizno'),dict):
            raise ValueError('sme_source_not_verified')
        if not data.get('recordsByBizno'):raise ValueError('sme_empty_partners')
    elif job=='directProduction':
        if data.get('ok') is not True or data.get('complete') is not True:
            raise ValueError('direct_production_unverified')
        if int(data.get('recordCount') or 0)<20000:
            raise ValueError('direct_production_corpus_too_small')
        if not isinstance(data.get('recordsByBizno'),dict):
            raise ValueError('direct_production_records_missing')
    else:raise ValueError('unknown_worklinks_job')
    return True

def publish(job,body):
    name=JOBS[job]['output']
    path=SNAP/name
    if path.is_file() and job in ('smeCert','directProduction'):
        previous=json.loads(path.read_text(encoding='utf-8'))
        newer=json.loads(body)
        oldstamp=str(previous.get('checkedAt') or previous.get('snapshotDate') or '')
        newstamp=str(newer.get('checkedAt') or newer.get('snapshotDate') or '')
        if oldstamp and newstamp and oldstamp>newstamp:
            raise ValueError('older_verified_source_must_not_replace_fresher')
    # Atomic individual output; all readers get either entire old or entire new.
    temp=path.with_name('.'+name+'.gz.next')
    SNAP.mkdir(parents=True,exist_ok=True)
    try:
        with gzip.open(temp,'wb',compresslevel=6) as gz:gz.write(body)
        write_atomic(path,body)
        os.replace(temp,Path(str(path)+'.gz'))
    finally:
        try:temp.unlink()
        except FileNotFoundError:pass
    return hashlib.sha256(body).hexdigest()

def run_job(job):
    info=JOBS[job]
    with tempfile.TemporaryDirectory(prefix='wl-standalone-',dir=str(DATA)) as tmp:
        root=prepare_workspace(tmp)
        env=dict(os.environ)
        env['WORKLINKS_CHROMIUM_PATH']=CHROMIUM
        env.pop('GITHUB_STEP_SUMMARY',None)
        cmd=[sys.executable,str(root/'scripts'/info['script'])]
        p=call(cmd,cwd=str(root),timeout=info['timeout'],env=env)
        if p.returncode!=0:
            raise RuntimeError('collector_exit_'+str(p.returncode)+' '+(p.stderr or p.stdout)[-200:])
        if job=='changcom200':
            report=root/'startup-support/audits/changcom-200-official-evidence-20261111.csv'
            md=root/'startup-support/audits/changcom-200-official-evidence-20261111.md'
            if not report.is_file() or not md.is_file():
                raise ValueError('changcom_200_source_audit_outputs_missing')
            with report.open(encoding='utf-8-sig',newline='') as input_csv:
                rows=list(csv.DictReader(input_csv))
            if (len(rows)!=200 or
                    len({str(x.get('공고번호') or '') for x in rows})!=200 or
                    [int(x.get('원본순위') or 0) for x in rows]!=list(range(1,201))):
                raise ValueError('changcom_200_membership_or_order_invalid')
            for item in (report,md):
                rel=item.relative_to(root/'startup-support')
                dest=SNAP/rel
                blob=item.read_bytes()
                archive=dest.with_name(dest.name+'.gz.next')
                dest.parent.mkdir(parents=True,exist_ok=True)
                try:
                    with gzip.open(archive,'wb',compresslevel=6) as out:out.write(blob)
                    write_atomic(dest,blob)
                    os.replace(archive,str(dest)+'.gz')
                finally:
                    try:archive.unlink()
                    except FileNotFoundError:pass
            log('WORKLINKS_STANDALONE_CHANGCOM_200_PUBLISHED',len(rows),
                'citable',sum(int(row.get('공식원문발췌수') or 0)>0 for row in rows))
            return
        if info.get('stdout'):
            from json import JSONDecoder
            payload=p.stdout.lstrip()
            data,offset=JSONDecoder().raw_decode(payload)
            body=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
        else:
            output=root/'startup-support'/info['output']
            if not output.is_file():raise ValueError('collector_output_missing')
            body=output.read_bytes()
            data=json.loads(body)
        validate(job,data)
        sha=publish(job,body)
        log('WORKLINKS_STANDALONE_PUBLISHED',job,info['output'],'bytes',len(body),'sha',sha[:12])

# Popen children let the parent keep polling Git and collecting independent
# sources even while one official site stalls for its configured timeout.
RUNNING = {}
MAX_CONCURRENT = 2

def start_job(job):
    if job not in JOBS:
        raise ValueError('unknown_worklinks_job')
    return subprocess.Popen([sys.executable, os.path.abspath(__file__), '--single', job],
                            cwd=str(SRC), env=dict(os.environ))

def iterate(now=None):
    now=time.time() if now is None else now
    st=state_load()
    # Child completion must update durable status before new decisions are made.
    for job,child in list(RUNNING.items()):
        code=child.poll()
        if code is None:
            continue
        record=st.get(job) or {}
        if code==0:
            record['status']='ok'
            record['lastSuccessEpoch']=time.time()
            record.pop('error',None)
            log('WORKLINKS_STANDALONE_CHILD_OK',job)
        else:
            record['status']='failed'
            record['error']='collector_child_exit_'+str(code)
            log('WORKLINKS_STANDALONE_CHILD_FAILED',job,code)
        st[job]=record
        del RUNNING[job]
        state_save(st)
    if now-float(st.get('_lastSourcePoll') or 0)>300 or not SRC.exists():
        st['_lastSourcePoll']=now
        try:
            changed,sha=update_source()
            if changed or not st.get('checkedHead'):
                good,results=test_source(SRC)
                st['lastQa']={'ok':good,'head':sha,'results':results}
                if good:
                    st['checkedHead']=sha
                    st['lastSupplementalQa']={'head':sha,'results':[],
                                              'complete':False}
                else:log('WORKLINKS_STANDALONE_SOURCE_QA_FAILED',sha,results[-1])
            st['sourceHead']=sha
        except Exception as exc:
            log('WORKLINKS_STANDALONE_SOURCE_UPDATE_FAILED',type(exc).__name__,str(exc)[:200])
            st['sourceError']=type(exc).__name__
        state_save(st)
    if not st.get('checkedHead') or st.get('checkedHead')!=source_head():
        return st
    # Insert each attempt timestamp BEFORE execution to prevent unlimited restart loops.
    # Jobs are staggered in this order to feed KIMSE verified dates to investment.
    order=('localBudget','changcom200','kimseDeep','investment',
           'smeCert','directProduction','healthLive')
    for job in order:
        if job in RUNNING:
            continue
        if len(RUNNING)>=MAX_CONCURRENT:
            break
        prev=st.get(job) or {}
        period=JOBS[job]['period']
        # A killed process leaves status=started. Retry it after a short
        # bounded cooldown, not a full month or a 12-hour schedule.
        delay=(period if prev.get('status')=='ok' else
               min(21600,max(300,period//6)))
        if now-float(prev.get('attemptEpoch') or 0)<delay:continue
        record={'attemptEpoch':now,'status':'started','sourceHead':st['checkedHead'],
                'lastSuccessEpoch':prev.get('lastSuccessEpoch')}
        st[job]=record
        state_save(st)
        try:
            RUNNING[job]=start_job(job)
            log('WORKLINKS_STANDALONE_CHILD_STARTED',job,'pid',RUNNING[job].pid)
        except Exception as exc:
            record['status']='failed'
            record['error']=type(exc).__name__+': '+str(exc)[:190]
            log('WORKLINKS_STANDALONE_FAILED',job,record['error'])
            st[job]=record
            state_save(st)
    # Optional source gates are metered one per cycle, AFTER critical collectors.
    extra=st.get('lastSupplementalQa') or {}
    if (extra.get('head')==st.get('checkedHead') and
            not extra.get('complete') and
            len(extra.get('results') or [])<len(SUPPLEMENTAL_QA)):
        idx=len(extra.get('results') or [])
        extra['results']=(extra.get('results') or [])+test_diagnostics(SRC,[SUPPLEMENTAL_QA[idx]])
        extra['complete']=len(extra['results'])==len(SUPPLEMENTAL_QA)
        st['lastSupplementalQa']=extra
        state_save(st)
    return st

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    SNAP.mkdir(parents=True,exist_ok=True)
    with LOCK.open('a') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            log('WORKLINKS_STANDALONE_ALREADY_RUNNING')
            return 1
        log('WORKLINKS_STANDALONE_START','jobs',list(JOBS),'gitPollSeconds',300)
        while True:
            try:iterate()
            except Exception as exc:
                log('WORKLINKS_STANDALONE_LOOP_FAILED',type(exc).__name__,str(exc)[:250])
            time.sleep(80)
if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--single':
        if sys.argv[2] not in JOBS:
            raise SystemExit(2)
        try:
            run_job(sys.argv[2])
        except Exception as exc:
            log('WORKLINKS_STANDALONE_SINGLE_FAILED',sys.argv[2],
                type(exc).__name__,str(exc)[:170])
            raise SystemExit(1)
    else:
        sys.exit(main())
