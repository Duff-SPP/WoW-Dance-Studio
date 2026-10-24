"""Selected-model conversion through deployment pack, using existing checked stages."""
import json,uuid,os
from pathlib import Path
from types import SimpleNamespace
from .catalog import ROOT,CATALOG,read_catalog,write_json
from .storage import atomic_json,locked

OUTPUT=ROOT/'Output/Workflows'


def request_path(value):
    path=Path(value).resolve()
    if not path.is_relative_to(OUTPUT.resolve()) or path.name!='request.json':
        raise ValueError('Select a workflow request inside Output/Workflows')
    return path


def selections(request):
    rows=request.get('targets')
    if rows is None:rows=[dict(target=request['target'],emotes=request.get('emotes',[]))]
    merged={}
    for row in rows:
        target=row['target'];ids=row.get('emotes',[])
        if not target or not ids:raise ValueError('Select dances for every model in the pack')
        merged.setdefault(target,[]).extend(ids)
    if not merged:raise ValueError('Select at least one model')
    return [dict(target=t,emotes=list(dict.fromkeys(ids))) for t,ids in merged.items()]


def run(path,emit=print):
    from . import batch,dbc_manager as dbc,m2_manager,pack_manager
    from .models import get_model,checked_profile
    from .cache import valid_output
    from run_hd_batch import authorize_profile
    from .addon import generate
    # Persistent allocations shared by guided runs; never overwrite unmanaged DBCs.
    dbc.OUTPUT=OUTPUT/'DBC'
    path=request_path(path);request=json.loads(path.read_text(encoding='utf-8-sig'))
    previous_montage=os.environ.get('WDS_MONTAGE_PREVIEW')
    if 'montage_playback' in request:
        if request['montage_playback']:os.environ['WDS_MONTAGE_PREVIEW']='1'
        else:os.environ.pop('WDS_MONTAGE_PREVIEW',None)
    targets=selections(request)
    folder=path.parent;cancel=folder/'cancel';state=dict(target=targets[0]['target'],targets=targets,phase='Checking requirements',complete=False,issues=[],queues={})
    def save(phase=None):
        if phase:state['phase']=phase
        atomic_json(folder/'status.json',state);emit('STUDIO: '+state['phase'])
    def cancelled():
        if cancel.exists():
            save('Cancelled — completed conversions are preserved; Resume will reuse them')
            return True
        return False
    def progress(message):
        emit(message)
        state['queue']=batch.summary();state['queues'][state['target']]=state['queue'];save()
        if cancel.exists():batch.control('cancel')
    with locked(OUTPUT/'runner.lock'),locked(batch.LIBRARY/'workflow.lock'):
        try:
            previous=folder/'status.json'
            if previous.exists():
                prior=json.loads(previous.read_text(encoding='utf-8'))
                queue=batch.read_queue()
                if prior.get('queue_batch') and queue.get('batch')==prior['queue_batch']:
                    batch.recover_abandoned();batch.control('cancel')
            save()
            models={};good=[];chosen_by_target={}
            for selection in targets:
                state['target']=selection['target']
                # Run authorizes technical export, never visual approval.
                model=authorize_profile(get_model(selection['target']));models[model['id']]=model
                checked_profile(model['profile'],model['id'],model['scene'])
                if cancelled():return state
                save('Checking cache for '+model['id'])
                args=SimpleNamespace(emotes=request['asset_root'],emote=','.join(selection['emotes']),variant='AUTO',target=model['id'],
                                     profile=model['profile'],scene=model['scene'],blender=request['blender'],force=False,command='convert-missing')
                state['queue']=batch.enqueue(args,cancelled=cancelled)
                if state['queue'].get('preparation_cancelled'):return state
                state['queue_batch']=state['queue']['jobs'][0]['batch'];save()
                if cancelled():batch.control('cancel');return state
                save('Converting missing dances for '+model['id'])
                batch.control('start');state['queue']=batch.run_queue(progress)
                state['queues'][model['id']]=state['queue']
                if cancelled():return state
                if state['queue']['remaining']:raise ValueError('Conversion paused; resume after the other Blender job finishes')
                jobs=state['queue']['jobs']
                passed=[j for j in jobs if j['status'] in ('Converted – Review Needed','Approved','Skipped – Up to Date')]
                state['issues'].extend(dict(target=model['id'],emote=j['emote'],reason=j.get('error')) for j in jobs if j not in passed)
                if not passed:raise ValueError('No selected dance passed conversion for '+model['id']+'. See issues and conversion logs.')
                good.extend(passed);chosen_by_target[model['id']]=[j['emote'] for j in passed]
            # Bind export authorization to the exact checked action and profile.
            with locked(CATALOG.with_suffix('.lock'),timeout=10):
                catalog=read_catalog()
                for job in good:
                    emote=next(e for e in catalog['emotes'] if e['id']==job['emote'])
                    version=next(v for v in emote['versions'] if v['version']==job['version'])
                    if not valid_output(version):raise ValueError('Converted output changed: '+job['emote'])
                    checked_profile(version['profile_path'],job['target'],models[job['target']]['scene'])
                    emote.setdefault('export_authorizations',{})[version['version']]=dict(kind='user_requested_batch_export',
                        sha256=version['action_library_sha256'],profile_sha256=version['profile_sha256'],visual_quality='unverified')
                write_json(CATALOG,catalog)
            chosen=sorted({j['emote'] for j in good})
            catalog={e['id']:e for e in read_catalog()['emotes']}
            state['missing_audio']=[i for i in chosen if not catalog[i]['audio']]
            if cancelled():return state
            save('Exporting linked DBC records and music')
            plan=dbc.preview(dict(emotes=chosen,include_sound=bool(request.get('include_audio',True)),
                                  include_text=True,include_client_audio=True,full_soundtrack=True,sound_template=6894))
            state['dbc']=dbc.export(plan['plan_path'])
            if cancelled():return state
            state['model_exports']=[]
            for target,ids in chosen_by_target.items():
                save('Exporting model and new ANIM files: '+target)
                plan=m2_manager.preview(dict(target=target,emotes=ids))
                result=m2_manager.export(plan['plan_path'],request['blender'],emit)
                state['model_exports'].append(result);state['model_export']=result
                if cancelled():return state
            save('Building client, server and collection addon pack')
            include_code=bool(request.get('include_addon_code',False))
            state['pack']=pack_manager.build(dict(packages=[v['output'] for v in state['model_exports']],addon_audio=True,include_addon_code=include_code))
            generate(state['pack']['output'],'addon' if request.get('include_audio',True) else 'silent',include_code=include_code)
            state.update(complete=True,visual_quality='unverified')
            save('Pack ready'+(' — some selected dances were blocked; see issues' if state['issues'] else '')+' — in-game testing required')
            return state
        except Exception as error:
            state['error']=str(error);save('Stopped: '+str(error));raise
        finally:
            if 'montage_playback' in request:
                if previous_montage is None:os.environ.pop('WDS_MONTAGE_PREVIEW',None)
                else:os.environ['WDS_MONTAGE_PREVIEW']=previous_montage


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('request');args=parser.parse_args()
    run(args.request)


if __name__=='__main__':main()
