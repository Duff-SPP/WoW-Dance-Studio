"""WoW Dance Studio v0.3: persistent batch queue, verified cache and Blender preview."""
from studio_core.assets import discover
from studio_core.audio import audio_files
from studio_core.catalog import scan_emotes,approve_version
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from datetime import datetime

ROOT = Path(__file__).resolve().parent
from studio_core.runtime import defaults
_DEFAULTS = defaults()
BLENDER = Path(_DEFAULTS['blender'])
SCENE = Path(_DEFAULTS['scene'])
PROFILE = ROOT / 'Profiles' / 'profile.json'


def run(args, emit=print):
    from studio_core.batch import montage_mode
    from studio_core.models import validation_session
    with validation_session(),montage_mode(getattr(args,'montage_playback',None)):
        return _run(args,emit)


def _run(args, emit=print):
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    reports = ROOT / 'Reports'
    reports.mkdir(exist_ok=True)
    if args.command.startswith('pack-'):
        from studio_core import pack_manager as packs
        result=packs.scan() if args.command=='pack-scan' else packs.build(json.loads(Path(args.pack_request).read_text(encoding='utf-8-sig')))
        emit('STUDIO: '+json.dumps(result)); return
    if args.command.startswith('m2-'):
        from studio_core import m2_manager as m2
        if args.command=='m2-scan': result=m2.options(args.target); filename='scan.json'
        elif args.command=='m2-preview':
            request=json.loads(Path(args.m2_request).read_text(encoding='utf-8-sig')) if args.m2_request else dict(target=args.target,emotes=[v for v in (args.emote or '').split(',') if v])
            result=m2.preview(request); filename='preview_result.json'
        elif args.command=='m2-validate':
            plan=m2.validate_plan(args.m2_plan); result=dict(valid=True,target=plan['model']['id'],animations=len(plan['dances'])); filename='validation.json'
        else: result=m2.export(args.m2_plan,args.blender,emit); filename='export_result.json'
        from studio_core.storage import atomic_json
        atomic_json(m2.OUTPUT/filename,result)
        emit('STUDIO: '+json.dumps(result)); return
    if args.command.startswith('dbc-'):
        from studio_core import dbc_manager as dbc
        if args.command=='dbc-scan': result=dbc.scan(); atomic_path=dbc.OUTPUT/'scan.json'
        elif args.command=='dbc-ids':
            tables,_=dbc.inputs()
            if args.dbc_table not in tables: raise ValueError('Select a supplied DBC table')
            table=tables[args.dbc_table]
            result=dict(table=table.name,original_ids=sorted(table.ids),custom_records={owner:entry['records'].get(table.name,[]) for owner,entry in dbc.registry()['dances'].items()})
            if args.dbc_id is not None:
                result['original_record']=dict(zip(table.schema.fields,table.values(table.ids[args.dbc_id]))) if args.dbc_id in table.ids else None
                result.pop('original_ids')
            atomic_path=dbc.OUTPUT/'ids.json'
        elif args.command=='dbc-preview':
            request=json.loads(Path(args.dbc_request).read_text(encoding='utf-8-sig')) if args.dbc_request else dict(emotes=[v for v in (args.emote or '').split(',') if v],include_sound=args.dbc_sound,include_text=args.dbc_text,include_client_audio=args.dbc_sound,full_soundtrack=True,sound_template=args.dbc_sound_template)
            result=dbc.preview(request); atomic_path=dbc.OUTPUT/'preview_result.json'
        elif args.command=='dbc-validate':
            plan=dbc.validate_plan(args.dbc_plan); result=dict(valid=True,counts=plan['counts']); atomic_path=dbc.OUTPUT/'validation.json'
        else: result=dbc.export(args.dbc_plan); atomic_path=dbc.OUTPUT/'export_result.json'
        from studio_core.storage import atomic_json
        atomic_json(atomic_path,result)
        emit('STUDIO: '+json.dumps(dict(command=args.command,result_file=str(atomic_path),counts=result.get('counts'),valid=result.get('valid'),output=result.get('output')),ensure_ascii=True))
        return
    if args.command in {'models-scan','models-list','model-register','profile-generate','profile-validate','profile-approve'}:
        from studio_core.models import discover_models,read_models,get_model
        if args.command=='models-scan': emit(json.dumps(discover_models(args.wow),indent=2)); return
        if args.command=='models-list': emit(json.dumps(read_models(),indent=2)); return
        if args.command=='model-register':
            rows=discover_models(args.wow)
            from studio_core.models import relocate_models
            relocate_models(rows)
            if args.model_file: rows=[r for r in rows if Path(r['path'])==Path(args.model_file).resolve()]
            if not rows: raise ValueError('No M2 files found in selected folder')
        else: rows=[get_model(args.target)]
        for row in rows:
            if row.get('error'): emit('STUDIO: Rejected '+row['path']+': '+row['error']); continue
            scene=args.scene if args.command=='model-register' else row['scene']
            report=reports/(args.command+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
            command=[args.blender,'-b',scene,'--python-exit-code','1','--python',str(ROOT/'blender_worker.py'),'--',args.command,'--report',str(report),'--target',args.target]
            if args.command=='model-register':
                command+=['--model-file',row['path'],'--source-rig',args.source_rig]
            else:
                previous=getattr(args,'previous_profile',None) or row.get('profile')
                if previous: command+=['--previous-profile',previous]
                if args.overrides: command+=['--overrides',args.overrides]
            log=report.with_suffix('.log')
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode: raise RuntimeError('Model/profile operation failed: '+str(log))
            payload=json.loads(report.read_text(encoding='utf-8'))
            emit('STUDIO: '+json.dumps({k:payload[k] for k in ('id','profile','status','mapped','validation') if k in payload}))
        return
    batch_commands={'library-convert','convert-selected','convert-missing','convert-all','retry-failed',
                    'queue-start','queue-pause','queue-resume','queue-cancel','queue-status','verify-cache'}
    if args.command in batch_commands:
        from studio_core import batch
        if args.queue_file:
            queue_path=Path(args.queue_file).resolve()
            if not queue_path.is_relative_to(ROOT/'Output'): raise ValueError('Queue must be inside Output')
            batch.QUEUE=queue_path
        if args.command=='queue-status':
            emit(json.dumps(batch.summary(),ensure_ascii=True)); return
        if args.command=='verify-cache':
            emit(json.dumps(batch.verify_cache(args),ensure_ascii=True)); return
        if args.command in {'queue-pause','queue-cancel'}:
            emit(json.dumps(batch.control(args.command.split('-')[1]),ensure_ascii=True)); return
        if args.command=='retry-failed':
            batch.recover_abandoned(); batch.control('retry')
        elif args.command not in {'queue-start','queue-resume'}:
            if args.command in {'library-convert','convert-selected'} and not args.emote: raise ValueError('Select at least one emote')
            prepared=batch.enqueue(args,emit)
            if prepared.get('preparation_cancelled'):return
        if args.control_only:
            result=batch.control('start')
        elif not args.enqueue_only:
            batch.control('start'); result=batch.run_queue(emit)
        else: result=batch.summary()
        if result['mode']=='cancelled':
            emit('STUDIO: Batch cancelled. You can start a new conversion.'); return
        emit('STUDIO: Refreshing cache status for this batch')
        batch.verify_cache(args,identifiers={job['emote'] for job in result['jobs']})
        reasons={}
        for job in result['jobs']:
            if job.get('error'): reasons.setdefault(job['error'],[]).append(job['emote'])
        for reason,emotes in reasons.items(): emit('STUDIO: '+', '.join(emotes)+': '+reason)
        emit('STUDIO: Queue '+json.dumps({k:v for k,v in result.items() if k!='jobs'},ensure_ascii=True))
        if result['failed'] or result['blocked']: raise RuntimeError('Queue has failed or blocked jobs; inspect queue-status for details')
        return
    if args.command=='approve':
        version=approve_version(args.emote,args.variant,args.target)
        from studio_core import batch
        if batch.QUEUE.exists():
            def mark_approved(queue_state):
                for job in queue_state['jobs']:
                    if job.get('emote')==args.emote and job.get('variant')==args.variant and job.get('version')==version:
                        job['approved']=True
                        if job['status']=='Converted – Review Needed': job['status']='Approved'
            batch.update(mark_approved)
        emit('STUDIO: Manual visual approval recorded for '+version)
        return
    if args.command=='catalog':
        catalog=scan_emotes(args.emotes)
        emit(f"STUDIO: Indexed {len(catalog['emotes'])} emote families")
        return
    if args.command == 'assets':
        files = discover(args.wow, args.emotes)
        path = reports / f'assets_{stamp}.json'
        path.write_text(json.dumps(files, indent=2), encoding='utf-8')
        emit(f'{len(files)} assets indexed: {path}')
        catalog=scan_emotes(args.emotes)
        emit(f"STUDIO: Indexed {len(catalog['emotes'])} emote families; export names: "+', '.join(e['name'] for e in catalog['emotes']))
        return
    blender, scene = Path(args.blender).resolve(), Path(args.scene).resolve()
    if not blender.is_file() or not scene.is_file():
        raise ValueError('Select an existing Blender executable and .blend scene.')
    profile = Path(args.profile).resolve()
    stem=f"Human2_{args.emote}_{args.command}" if getattr(args,'emote',None) else 'Human2_AutumnTea'
    output = Path(args.output).resolve() if args.output else ROOT / 'Output' / f'{stem}_{stamp}.blend'
    # Generated writes are confined to the designated directories.
    if not profile.is_relative_to(ROOT / 'Profiles'):
        raise ValueError('Profile must be inside Profiles.')
    if not output.is_relative_to(ROOT / 'Output'):
        raise ValueError('Converted scene must be inside Output.')
    report = reports / f'{args.command}_{stamp}.json'
    preview_key=preview_fingerprint=None
    if args.command=='preview':
        from studio_core.cache import preview_dependencies,cached_preview,remember_preview
        preview_key,preview_fingerprint=preview_dependencies(args.emote,args.variant,scene,blender,args.include_audio,args.target)
        cached=cached_preview(preview_key,preview_fingerprint)
        if cached and not args.force:
            emit('STUDIO: Preview up to date: '+cached['output'])
            if args.open: subprocess.Popen([str(blender),cached['output']])
            return
    command = [str(blender), '-b', str(scene), '--python-exit-code', '1',
               '--python', str(ROOT / 'blender_worker.py'), '--', args.command,
               '--report', str(report), '--profile', str(profile), '--output', str(output)]
    command+=['--target',args.target]
    command += ['--audio-dir', str(getattr(args, 'audio_dir', None) or args.emotes),
                '--include-audio' if getattr(args, 'include_audio', True) else '--no-include-audio']
    if getattr(args,'emote',None):
        command += ['--emote',args.emote,'--variant',args.variant]
    log = reports / f'{args.command}_{stamp}.log'
    with log.open('w', encoding='utf-8') as stream:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace',
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
            for line in process.stdout:
                stream.write(line)
                if 'STUDIO:' in line or 'Error' in line or 'ValueError' in line:
                    emit(line.strip())
            code = process.wait()
    if code:
        raise RuntimeError(f'Blender failed ({code}). Details: {log}')
    if args.command=='preview': remember_preview(preview_key,preview_fingerprint,output)
    emit(f'Completed. Report: {report}')
    if args.command in {'convert','preview'}:
        emit(f'Output: {output}\nVisual quality requires review in Blender.')
    if args.command=='preview' and getattr(args,'open',False):
        subprocess.Popen([str(blender),str(output)])


def gui():
    if os.name=='nt':
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'StudioGUI.ps1')],check=True)
        return
    import tkinter as tk
    from tkinter import filedialog, ttk
    window = tk.Tk()
    window.title('WoW Dance Studio 0.2')
    window.geometry('870x530')
    fields = {}
    defaults = [('wow','WoW models folder',str(ROOT/'Input'/'WoW')),
                ('emotes','Fortnite emotes folder',str(ROOT/'Input'/'Fortnite')),
                ('blender','Blender executable',str(BLENDER)), ('scene','Prepared Blender scene',str(SCENE)),
                ('profile','Bone profile JSON',str(PROFILE))]
    def browse(key):
        value = filedialog.askdirectory() if key in ['wow','emotes'] else filedialog.askopenfilename()
        if value:
            fields[key].set(value)
    for row,(key,label,default) in enumerate(defaults):
        ttk.Label(window,text=label).grid(row=row,column=0,padx=8,pady=5,sticky='w')
        fields[key] = tk.StringVar(value=default)
        ttk.Entry(window,textvariable=fields[key]).grid(row=row,column=1,sticky='ew')
        ttk.Button(window,text='Browse',command=lambda k=key:browse(k)).grid(row=row,column=2,padx=8)
    bar = ttk.Frame(window)
    include_audio = tk.BooleanVar(value=bool(audio_files(fields['emotes'].get())))
    fields['emotes'].trace_add('write', lambda *_: include_audio.set(bool(audio_files(fields['emotes'].get()))))
    ttk.Checkbutton(window,text='Include Audio',variable=include_audio).grid(row=5,column=0,sticky='w',padx=8)
    bar.grid(row=6,column=0,columnspan=3,pady=10)
    text = tk.Text(window,wrap='word',height=17)
    text.grid(row=7,column=0,columnspan=3,sticky='nsew',padx=8,pady=8)
    events = queue.Queue()
    busy = False
    def start(command):
        nonlocal busy
        if busy:
            return
        busy = True
        args = argparse.Namespace(command=command,output=None,include_audio=include_audio.get(),**{k:v.get() for k,v in fields.items()})
        text.insert('end',f'Starting {command}...\n')
        def work():
            try:
                run(args,events.put)
            except Exception as error:
                events.put('ERROR: '+str(error))
            finally:
                events.put(None)
        threading.Thread(target=work,daemon=True).start()
    for label,command in [('Scan Assets','assets'),('Scan Skeletons','scan'),('Generate Profile','profile'),('Convert Animation','convert')]:
        ttk.Button(bar,text=label,command=lambda c=command:start(c)).pack(side='left',padx=3)
    ttk.Button(bar,text='Review Profile',command=lambda:os.startfile(fields['profile'].get())).pack(side='left',padx=3)
    ttk.Button(bar,text='Open Output',command=lambda:os.startfile(str(ROOT/'Output'))).pack(side='left',padx=3)
    def poll():
        nonlocal busy
        while not events.empty():
            event = events.get_nowait()
            if event is None:
                busy = False
            else:
                text.insert('end',event+'\n')
                text.see('end')
        window.after(100,poll)
    window.columnconfigure(1,weight=1)
    window.rowconfigure(7,weight=1)
    poll()
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='gui',choices=['gui','assets','scan','profile','convert','catalog','library-convert','preview','approve',
            'convert-selected','convert-missing','convert-all','retry-failed','queue-start','queue-pause','queue-resume','queue-cancel','queue-status','verify-cache',
            'models-scan','models-list','model-register','profile-generate','profile-validate','profile-approve',
            'dbc-scan','dbc-ids','dbc-preview','dbc-validate','dbc-export','pack-scan','pack-build','m2-scan','m2-preview','m2-validate','m2-export'])
    parser.add_argument('--blender',default=str(BLENDER))
    parser.add_argument('--scene',default=str(SCENE))
    parser.add_argument('--profile',default=str(PROFILE))
    parser.add_argument('--output')
    parser.add_argument('--wow',default=str(ROOT/'Input'/'WoW'))
    parser.add_argument('--emotes',default=str(ROOT/'Input'/'Fortnite'))
    parser.add_argument('--audio-dir',help='Optional soundtrack folder (defaults to Fortnite emotes folder)')
    parser.add_argument('--include-audio',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--montage-playback',action=argparse.BooleanOptionalAction,default=None,
                        help='Use verified Fortnite intro/loop sections; saved with conversion jobs')
    parser.add_argument('--emote',help='Stable emote ID from the catalog')
    parser.add_argument('--variant',default='CMM')
    parser.add_argument('--open',action='store_true',help='Open generated preview in Blender')
    parser.add_argument('--target',default='human2_male')
    parser.add_argument('--model-file')
    parser.add_argument('--source-rig',default='Fortnite_M_Avg_Player_Skeleton',help='Exact reference source armature in selected prepared scene; identity is recorded and enforced')
    parser.add_argument('--previous-profile')
    parser.add_argument('--overrides',help='Path to a JSON object of source-to-target manual mapping corrections')
    parser.add_argument('--force',action='store_true',help='Create a new version even when a verified cache hit exists')
    parser.add_argument('--enqueue-only',action='store_true',help='Persist jobs without starting Blender')
    parser.add_argument('--queue-file',help='Optional isolated queue JSON inside Output')
    parser.add_argument('--control-only',action='store_true',help='Signal an existing runner without launching a second scheduler')
    parser.add_argument('--dbc-request',help='DBC preview options JSON')
    parser.add_argument('--dbc-plan',help='Exact previously previewed plan inside Output/DBC/plans')
    parser.add_argument('--dbc-sound',action='store_true')
    parser.add_argument('--dbc-text',action='store_true')
    parser.add_argument('--dbc-sound-template',type=int)
    parser.add_argument('--dbc-table',default='AnimationData')
    parser.add_argument('--dbc-id',type=int)
    parser.add_argument('--pack-request')
    parser.add_argument('--m2-request')
    parser.add_argument('--m2-plan')
    args = parser.parse_args()
    if args.command == 'gui':
        gui()
    else:
        try:
            run(args)
        except Exception as error:
            parser.exit(1,str(error)+'\n')


if __name__ == '__main__':
    main()
