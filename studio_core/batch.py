"""One persistent scheduler shared by CLI and Windows Forms."""
import json
import os
import time
from contextlib import contextmanager
import subprocess
import uuid
from datetime import datetime,timezone
from pathlib import Path
from .catalog import ROOT,LIBRARY,read_catalog,scan_emotes,select_version
from .storage import atomic_json,locked
from .cache import Context,find_current,valid_output,inspect_cache,reuse_profile_revision
from .models import validation_session

QUEUE=LIBRARY/'queue.json'


@contextmanager
def montage_mode(enabled):
    previous=os.environ.get('WDS_MONTAGE_PREVIEW')
    try:
        if enabled is not None:
            if enabled: os.environ['WDS_MONTAGE_PREVIEW']='1'
            else: os.environ.pop('WDS_MONTAGE_PREVIEW',None)
        yield
    finally:
        if previous is None: os.environ.pop('WDS_MONTAGE_PREVIEW',None)
        else: os.environ['WDS_MONTAGE_PREVIEW']=previous


def now(): return datetime.now(timezone.utc).isoformat()


def read_queue():
    return json.loads(QUEUE.read_text(encoding='utf-8')) if QUEUE.exists() else dict(schema=3,mode='paused',jobs=[])


def update(function):
    with locked(QUEUE.with_suffix('.lock'),timeout=3):
        queue=read_queue(); result=function(queue); queue['updated_at']=now(); atomic_json(QUEUE,queue)
        return result


def summary():
    queue=read_queue(); jobs=[j for j in queue['jobs'] if j.get('batch')==queue.get('batch')]
    count=lambda states:sum(j['status'] in states for j in jobs)
    running=next((j for j in jobs if j['status']=='Running'),None)
    return dict(mode=queue['mode'],total=len(jobs),completed=count({'Converted – Review Needed','Approved'}),
                skipped=count({'Skipped – Up to Date'}),failed=count({'Failed'}),blocked=count({'Blocked – Missing Requirements'}),
                cancelled=count({'Cancelled'}),remaining=count({'Pending','Running'}),current=running['emote'] if running else None,jobs=jobs)


class PreparationCancelled(RuntimeError):
    pass


@validation_session()
def enqueue(args,emit=print,cancelled=None):
    with locked(QUEUE.with_suffix('.prepare.lock'),timeout=0):
        return _prepare_enqueue(args,emit,cancelled)


def _prepare_enqueue(args,emit,cancelled):
    identifier=uuid.uuid4().hex
    def begin(queue):
        if any(j['status'] in {'Running','Pending'} for j in queue['jobs']):
            raise ValueError('Resume or cancel the existing queue before preparing another batch')
        queue['preparation']=dict(id=identifier,status='running',cancel_requested=False)
    update(begin)
    next_check=0
    def checkpoint(force=False):
        nonlocal next_check
        if not force and time.monotonic()<next_check:return
        next_check=time.monotonic()+.1
        preparation=read_queue().get('preparation',{})
        if preparation.get('id')!=identifier or preparation.get('cancel_requested') or (cancelled and cancelled()):
            raise PreparationCancelled()
    status='failed'
    try:
        result=_enqueue(args,emit,checkpoint)
        status='complete'
        return result
    except PreparationCancelled:
        status='cancelled'
        emit('STUDIO: Preparation cancelled; no new conversion batch started. Saved conversions are preserved.')
        return dict(summary(),preparation_cancelled=True)
    finally:
        def finish(queue):
            if queue.get('preparation',{}).get('id')==identifier:queue['preparation']['status']=status
        update(finish)


def _enqueue(args,emit,checkpoint):
    emit('STUDIO: Scanning exported emotes before queue preparation')
    scan_emotes(args.emotes,checkpoint=checkpoint)
    checkpoint(True)
    catalog=read_catalog()
    ids=[identifier.strip() for identifier in args.emote.split(',') if identifier.strip()] if args.emote else [e['id'] for e in catalog['emotes']]
    force=bool(args.force and getattr(args,'command',None)!='convert-missing')
    try: context=Context(args.blender,args.scene); context_error=None
    except (ValueError,OSError) as error: context=None; context_error=str(error)
    batch=uuid.uuid4().hex
    entries=[]
    ids=list(dict.fromkeys(ids))
    emit('STUDIO: Preparing '+str(len(ids))+' emotes; checking model, profile and conversion cache')
    for index,identifier in enumerate(ids,1):
        checkpoint(True)
        emit('STUDIO: Checking '+str(index)+' / '+str(len(ids))+': '+identifier)
        job=dict(id=uuid.uuid4().hex,batch=batch,emote=identifier,variant=args.variant,target=args.target,
                 profile=str(Path(args.profile).resolve()),scene=str(Path(args.scene).resolve()),blender=str(Path(args.blender).resolve()),
                 status='Pending',attempts=0,created_at=now(),started_at=None,ended_at=None,error=None,
                 version=None,force=force,fingerprint=None,
                 montage_playback=os.environ.get('WDS_MONTAGE_PREVIEW')=='1')
        try:
            from .variants import resolve_variant
            emote=next((e for e in catalog['emotes'] if e['id']==identifier),None)
            if emote is None: raise ValueError('Unknown emote: '+identifier)
            job['variant']=resolve_variant(emote,args.target,args.variant)
            if context is None: raise ValueError(context_error)
            job['fingerprint'],payload=context.fingerprint(identifier,job['variant'],args.profile,args.target)
            current=find_current(identifier,job['variant'],job['fingerprint'],args.target,emote=emote)
            if not current and not force:
                current=reuse_profile_revision(identifier,job['variant'],job['fingerprint'],payload,args.target,args.profile)
            if current and not force:
                ensure_selected(identifier,job['variant'],current,args.target)
                job.update(status='Skipped – Up to Date',version=current['version'],ended_at=now())
        except (ValueError,OSError,KeyError) as error:
            job.update(status='Blocked – Missing Requirements',error=str(error),ended_at=now())
        entries.append(job)
        emit('STUDIO: '+identifier+': '+job['status']+((' - '+job['error']) if job['error'] else ''))
    def add(queue):
        if queue.get('preparation',{}).get('cancel_requested'):raise PreparationCancelled()
        if any(j['status']=='Running' for j in queue['jobs']): raise ValueError('Wait for the current job before replacing the active batch')
        if any(j['status']=='Pending' for j in queue['jobs']): raise ValueError('Resume or cancel the pending queue first')
        queue['batch']=batch; queue['mode']='paused'; queue['jobs'].extend(entries)
    update(add)
    return summary()


def ensure_selected(identifier,variant,metadata,target):
    emote=next(e for e in read_catalog()['emotes'] if e['id']==identifier)
    versions=[m for m in emote['versions'] if m['variant']==variant and m.get('target_id','human2_male')==target]
    selected=emote.get('selected_versions',{}).get(target+':'+variant,versions[-1]['version'] if versions else None)
    if selected!=metadata['version']: select_version(identifier,variant,metadata['version'],target)


def control(action):
    def change(queue):
        preparing=queue.get('preparation',{}).get('status')=='running'
        if preparing:
            try:
                with locked(QUEUE.with_suffix('.prepare.lock'),timeout=0):
                    queue['preparation']['status']='interrupted'
                    preparing=False
            except RuntimeError:pass
        if preparing and action in {'cancel','pause'}:queue['preparation']['cancel_requested']=True
        if preparing and action in {'start','resume','retry'}:raise ValueError('Wait for preparation to finish, or Cancel it first')
        if action=='pause': queue['mode']='paused'
        elif action=='cancel':
            queue['mode']='cancelled'
            for job in queue['jobs']:
                if job['status']=='Pending': job.update(status='Cancelled',ended_at=now())
        elif action in {'start','resume'}: queue['mode']='running'
        elif action=='retry':
            batch=queue.get('batch') if any(j['status']=='Pending' for j in queue['jobs']) else uuid.uuid4().hex
            for job in queue['jobs']:
                if job['status']=='Pending': job['batch']=batch
                if job['status']=='Failed': job.update(status='Pending',error=None,ended_at=None,batch=batch)
            queue['batch']=batch
            queue['mode']='paused'
    update(change)
    if action=='cancel':
        # A dead runner cannot finish its Running jobs. Never reclaim a live
        # runner or a Blender worker that still owns the conversion lock.
        try:
            with locked(LIBRARY/'runner.lock'),locked(LIBRARY/'conversion.lock'):
                def finish_cancel(queue):
                    if queue['mode']=='cancelled':
                        for job in queue['jobs']:
                            if job['status']=='Running':job.update(status='Cancelled',ended_at=now(),error=None)
                update(finish_cancel)
        except RuntimeError:pass
    return summary()


def recover_abandoned():
    with locked(LIBRARY/'runner.lock'):
        def recover(queue):
            for job in queue['jobs']:
                if job['status']=='Running': job.update(status='Failed',error='Interrupted runner; retry checks output integrity',ended_at=now())
        update(recover)


@validation_session()
def run_queue(emit=print):
    with locked(LIBRARY/'runner.lock'):
        def recover(queue):
            for job in queue['jobs']:
                if job['status']=='Running': job.update(status='Failed',error='Interrupted runner; retry will verify the cache before conversion',ended_at=now())
        update(recover)
        contexts={}
        while True:
            queue=read_queue()
            if queue['mode']!='running': break
            pending=next((j for j in queue['jobs'] if j['status']=='Pending'),None)
            if pending is None:
                update(lambda q:q.update(mode='idle')); break
            with montage_mode(pending.get('montage_playback')):
                job=pending
                def patch(**values):
                    def apply(q): next(j for j in q['jobs'] if j['id']==job['id']).update(values)
                    update(apply)
                try:
                    key=(job['blender'],job['scene'])
                    if key not in contexts: contexts[key]=Context(*key)
                    fingerprint,_=contexts[key].fingerprint(job['emote'],job['variant'],job['profile'],job['target'])
                    current=find_current(job['emote'],job['variant'],fingerprint,job['target'])
                    if current and (not job['force'] or current.get('queue_job_id')==job['id']):
                        ensure_selected(job['emote'],job['variant'],current,job['target'])
                        patch(status='Skipped – Up to Date',version=current['version'],fingerprint=fingerprint,ended_at=now())
                        emit('STUDIO: Cached '+job['emote']); continue
                except (ValueError,OSError,KeyError) as error:
                    patch(status='Blocked – Missing Requirements',error=str(error),ended_at=now()); continue
                # Respect a pause/cancel received during dependency checks.
                if read_queue()['mode']!='running': break
                try:
                    with locked(LIBRARY/'conversion.lock'): pass
                except RuntimeError:
                    patch(error='A previous Blender worker is still finishing; resume when it exits')
                    control('pause'); emit('STUDIO: Paused: a previous Blender worker is still finishing'); break
                def claim(q):
                    entry=next(j for j in q['jobs'] if j['id']==job['id'])
                    if q['mode']!='running' or entry['status']!='Pending':return False
                    entry.update(status='Running',attempts=job['attempts']+1,started_at=now(),error=None,fingerprint=fingerprint)
                    return True
                if not update(claim):break
                emit('STUDIO: Converting '+job['emote']+' '+job['variant'])
                directory=ROOT/'Reports'/'queue'; directory.mkdir(parents=True,exist_ok=True)
                attempt=job['id']+'_'+str(job['attempts']+1)
                report=directory/(attempt+'.json'); log=directory/(attempt+'.log'); request=directory/(attempt+'_request.json')
                patch(log=str(log),report=str(report))
                atomic_json(request,dict(blender=job['blender'],scene=job['scene'],target=job['target'],fingerprint=fingerprint,force=job['force'],job_id=job['id']))
                command=[job['blender'],'-b',job['scene'],'--python-exit-code','1','--python',str(ROOT/'blender_worker.py'),'--',
                         'library-convert','--emote',job['emote'],'--variant',job['variant'],'--profile',job['profile'],
                         '--report',str(report),'--job-request',str(request)]
                try:
                    with log.open('w',encoding='utf-8') as stream:
                        with subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as worker:
                            while worker.poll() is None:
                                if read_queue()['mode']=='cancelled':
                                    worker.terminate()
                                    worker.wait()
                                    break
                                time.sleep(.1)
                            returncode=worker.returncode
                    if read_queue()['mode']=='cancelled':
                        patch(status='Cancelled',error=None,ended_at=now())
                        emit('STUDIO: Cancelled '+job['emote'])
                        break
                    metadata=json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
                    if returncode or not valid_output(metadata) or metadata.get('fingerprint')!=fingerprint:
                        raise RuntimeError(metadata.get('error','Worker failed or did not publish a validated output')+'; log: '+str(log))
                    emote=next(e for e in read_catalog()['emotes'] if e['id']==job['emote'])
                    status='Approved' if metadata['version'] in emote.get('approvals',{}) else 'Converted – Review Needed'
                    patch(status=status,version=metadata['version'],ended_at=now(),report=str(report),log=str(log))
                    emit('STUDIO: Completed '+job['emote'])
                except Exception as error:
                    if read_queue()['mode']=='cancelled':
                        patch(status='Cancelled',error=None,ended_at=now(),log=str(log)); break
                    patch(status='Failed',error=str(error),ended_at=now(),log=str(log)); emit('STUDIO: Failed '+job['emote']+': '+str(error))
    return summary()


@validation_session()
def verify_cache(args,identifiers=None):
    try: rows=inspect_cache(Context(args.blender,args.scene),args.profile,args.target,args.variant,identifiers=identifiers)
    except (ValueError,OSError) as error:
        rows={e['id']:dict(status='Missing Dependencies',error=str(error)) for e in read_catalog()['emotes']}
    atomic_json(LIBRARY/'cache_status.json',dict(target=args.target,variant=args.variant,profile=str(Path(args.profile).resolve()),items=rows))
    return rows
