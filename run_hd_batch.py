"""Resumable HD conversion/export run authorized by the user's bulk export request.

Input assets and prior profiles/visual approvals are never modified. New profile
revisions and action authorizations explicitly remain visually unverified.
"""
import argparse,copy,json,os,subprocess,time,uuid,traceback
from pathlib import Path
from datetime import datetime,timezone
from studio_core.catalog import ROOT,read_catalog,select_emote,digest,write_json,CATALOG
from studio_core.storage import atomic_json,locked
from studio_core.models import read_models,publish,checked_profile,profile_content_hash
from studio_core.cache import Context,find_current,valid_output
from studio_core.variants import resolve_variant,main_performance

WORK=ROOT/'Output/HDBatch';REPORTS=ROOT/'Reports/HDBatch'
from studio_core.runtime import defaults
BLENDER=Path(defaults()['blender'])
def now():return datetime.now(timezone.utc).isoformat()
def emit(message):print(message,flush=True)

def authorize_profile(model):
    original=Path(model['profile']);p=checked_profile(original,model['id'],model['scene'],require_approval=False)
    if not p.get('generator'):return model
    if p.get('status') in ('Approved','Batch Export Authorized'):
        checked_profile(original,model['id'],model['scene']);return model
    if not p.get('validation',{}).get('passed'):raise ValueError('Profile technical validation failed')
    p=copy.deepcopy(p);p.update(parent_revision=p['revision'],revision=uuid.uuid4().hex[:12],status='Batch Export Authorized',visual_quality='unverified')
    p['approval']=dict(kind='user_requested_batch_export',manual=False,recorded_at=now(),
                       scope='User requested conversion and export for this model. Technical validation only; visual review outstanding.')
    p['approval']['content_sha256']=profile_content_hash(p)
    path=ROOT/'Profiles'/model['id']/(p['revision']+'.json');atomic_json(path,p)
    model=copy.deepcopy(model);model['profile']=str(path)
    model.setdefault('approved_profiles',{})[p['source_signature']]=str(path)
    publish(model);return model

def authorize_outputs():
    targets={m['id']:m for m in read_models()['models'] if 'Client_HD' in m.get('path','')}
    with locked(CATALOG.with_suffix('.lock'),timeout=10):
        c=read_catalog()
        for e in c['emotes']:
            for v in e['versions']:
                if v.get('target_id') not in targets:continue
                validation=v.get('validation',{})
                if not valid_output(v) or not validation.get('motion',{}).get('passed'):continue
                checked_profile(v['profile_path'],v['target_id'],targets[v['target_id']]['scene'])
                e.setdefault('export_authorizations',{})[v['version']]=dict(kind='user_requested_batch_export',
                    recorded_at=now(),sha256=v['action_library_sha256'],profile_sha256=v['profile_sha256'],visual_quality='unverified')
        write_json(CATALOG,c)

def status(state):
    jobs=state['jobs'];counts={name:sum(j['status']==name for j in jobs) for name in ['Pending','Converted','Cached','Blocked','Failed']}
    state.update(updated_at=now(),counts=counts)
    atomic_json(WORK/'progress.json',state)
    summary=' | '.join(f'{k}: {v}' for k,v in counts.items())
    (WORK/'Progress.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>HD Dance Batch</title><body style="background:#16151d;color:#eee;font:18px system-ui;padding:40px"><h1>WoW Dance Studio — HD batch</h1><p>'+summary+'</p><p>'+state.get('phase','')+'</p><p>Updated '+state['updated_at']+'</p><p>Visual review remains outstanding. See progress.json for job details.</p>',encoding='utf-8')
    return summary

def build_exports(state):
    from studio_core import dbc_manager as dbc,m2_manager,pack_manager
    from studio_core.addon import generate
    authorize_outputs()
    dbc.OUTPUT=WORK/'DBC';dbc.OUTPUT.mkdir(parents=True,exist_ok=True)
    # Keep the identity of the previously confirmed Autumn Tea pack.
    if not (dbc.OUTPUT/'registry.json').exists():
        old=ROOT/'Output/HD_Scourge_DLL_Test_b6bccb57/DBC/registry.json'
        atomic_json(dbc.OUTPUT/'registry.json',json.loads(old.read_text()))
    good=sorted({j['emote'] for j in state['jobs'] if j['status'] in ('Converted','Cached')})
    if not good:raise ValueError('No technically validated conversions to export')
    preview=dbc.preview(dict(emotes=good,include_sound=True,include_text=True,include_client_audio=True,full_soundtrack=True,sound_template=6894))
    state['dbc']=dbc.export(preview['plan_path']);state['phase']='Exporting M2/ANIM';status(state)
    exports=[]
    for target in state['targets']:
        ids=sorted({j['emote'] for j in state['jobs'] if j['target']==target and j['status'] in ('Converted','Cached')})
        if not ids:continue
        try:
            plan=m2_manager.preview(dict(target=target,emotes=ids))
            result=m2_manager.export(plan['plan_path'],BLENDER,emit)
            exports.append(result['output']);state.setdefault('model_exports',{})[target]=result
            status(state)
        except Exception as error:
            state.setdefault('export_errors',{})[target]=str(error);status(state)
    if not exports:raise ValueError('No model export passed validation')
    result=pack_manager.build(dict(packages=exports,addon_audio=True))
    generate(result['output'],'addon')
    state['pack']=result;state['phase']='Complete — visual review and in-game testing required';status(state)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-jobs',type=int,default=0);parser.add_argument('--retry-failed',action='store_true');args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True);REPORTS.mkdir(parents=True,exist_ok=True)
    with locked(WORK/'runner.lock'):
        path=WORK/'progress.json'
        if path.exists():state=json.loads(path.read_text())
        else:
            catalog=read_catalog();models=[]
            for m in read_models()['models']:
                if 'Client_HD' in m.get('path',''):
                    emit('Checking HD profile '+m['id'])
                    models.append(authorize_profile(m))
            state=dict(started_at=now(),phase='Converting',targets=[m['id'] for m in models],jobs=[],missing_audio=[e['id'] for e in catalog['emotes'] if not e['audio']],visual_quality='unverified')
            for model in models:
                for emote in catalog['emotes']:
                    job=dict(target=model['id'],emote=emote['id'],status='Pending',report=str(REPORTS/(model['id']+'_'+emote['id']+'.json')))
                    try:
                        job['variant']=resolve_variant(emote,model['id'],'AUTO',model=model)
                        asset=main_performance([v for v in emote['variants'] if v['variant']==job['variant']])
                        if asset['missing_dependencies']:raise ValueError('; '.join(asset['missing_dependencies']))
                    except ValueError as error:job.update(status='Blocked',error=str(error))
                    state['jobs'].append(job)
            status(state)
        remaining_budget=args.max_jobs or 10**9
        for target in state['targets']:
            model=next(m for m in read_models()['models'] if m['id']==target)
            context=None;pending=[]
            for job in state['jobs']:
                if job['target']!=target:continue
                report=Path(job['report'])
                if report.exists():
                    result=json.loads(report.read_text())
                    if result.get('ok') and valid_output(result['metadata']):job.update(status='Converted',seconds=result['seconds']);continue
                    if not args.retry_failed:job.update(status='Failed',error=result.get('error'));continue
                if job['status']=='Blocked':
                    try:select_emote(job['emote'],job['variant'])
                    except (ValueError,KeyError):continue
                    job.update(status='Pending');job.pop('error',None)
                if len(pending)>=remaining_budget:break
                if context is None:context=Context(BLENDER,model['scene'])
                fingerprint,_=context.fingerprint(job['emote'],job['variant'],model['profile'],target)
                cached=find_current(job['emote'],job['variant'],fingerprint,target)
                if cached:job.update(status='Cached',version=cached['version']);continue
                job['cache_request']=dict(blender=str(BLENDER),scene=model['scene'],target=target,fingerprint=fingerprint,job_id='hd_bulk_'+target+'_'+job['emote'])
                pending.append(job)
            if pending:
                request=REPORTS/(target+'_request.json');atomic_json(request,dict(target=target,scene=model['scene'],profile=model['profile'],jobs=pending))
                state['current_target']=target;state['phase']='Converting '+target;emit(status(state))
                command=[str(BLENDER),'-b',model['scene'],'--python-exit-code','1','--python',str(ROOT/'hd_batch_worker.py'),'--',str(request)]
                with (REPORTS/(target+'.log')).open('a',encoding='utf-8') as log:
                    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    for line in process.stdout:
                        log.write(line);log.flush()
                        if line.startswith('HD_BATCH '):
                            result=json.loads(line[len('HD_BATCH '):]);emit(line.rstrip())
                            job=next(j for j in pending if j['emote']==result['emote']);job.update(status='Converted' if result['ok'] else 'Failed',seconds=result['seconds'])
                            if result.get('error'):job['error']=result['error']
                            status(state)
                    if process.wait():
                        state['phase']='Paused: worker stopped unexpectedly; successful jobs remain resumable'
                        status(state)
                        raise RuntimeError(state['phase'])
                remaining_budget-=len(pending)
            if remaining_budget<=0:
                state['phase']='Paused after requested sample; resume with python run_hd_batch.py';status(state);return
        state['phase']='Building shared DBC and model exports';status(state)
        try:build_exports(state)
        except Exception as error:state['phase']='Export blocked: '+str(error);status(state);raise

if __name__=='__main__':
    try:main()
    except Exception:
        WORK.mkdir(parents=True,exist_ok=True)
        (WORK/'last_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
