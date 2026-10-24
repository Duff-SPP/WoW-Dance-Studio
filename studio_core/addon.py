"""Generate a 3.3.5 collection addon from the pack's actual models and DBC tokens."""
import json,re,shutil,struct,wave
from pathlib import Path,PureWindowsPath
from .catalog import ROOT,read_catalog,digest
from .dbc_binary import DBC
from .m2_binary import Model,UNIT_SOUND_EVENT,M2Error
from .storage import atomic_json

SOURCE=ROOT/'Addon/WoWDanceStudio'

def lua(value):
    if value is None:return 'nil'
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,str):
        return '"'+''.join('\\'+c if c in ('\\','"') else ('\\%03d'%ord(c) if ord(c)<32 else c) for c in value)+'"'
    if isinstance(value,list):return '{'+','.join(lua(v) for v in value)+'}'
    return '{'+','.join('['+lua(str(k))+']='+lua(v) for k,v in sorted(value.items()))+'}'

def suppress_native_sound(raw,manifest):
    """Modify only the added animations' $CSD timestamp descriptors in deployment copies."""
    model=Model(raw);out=bytearray(raw);events=model.array(256,36);mutations=[]
    original_count=manifest['preservation']['original_sequences']
    for dance in manifest['dances']:
        audio=dance.get('client_audio')
        if not audio:continue
        index=model.lookup[dance['animation_id']]
        if index<original_count:raise M2Error('Cannot suppress audio on an original animation')
        found=False
        for i in range(0,len(events),36):
            if events[i:i+4]!=UNIT_SOUND_EVENT or struct.unpack_from('<I',events,i+4)[0]!=audio['sound_id']:continue
            count,pointer=struct.unpack_from('<II',events,i+28)
            if index>=count:continue
            at=pointer+index*8
            if struct.unpack_from('<II',raw,at)[0]:
                struct.pack_into('<II',out,at,0,0);mutations.append(dict(animation_id=dance['animation_id'],event=i//36,descriptor_offset=at));found=True
        if not found:raise M2Error('Expected native character soundtrack event before addon suppression')
    return bytes(out),mutations

def publish_main():
    """Publish the reusable addon runtime once per source-code version."""
    import hashlib
    names=('WoWDanceStudio.toc','Core.lua','Collection.lua')
    version=hashlib.sha256(''.join(digest(SOURCE/name) for name in names).encode()).hexdigest()[:16]
    destination=ROOT/'Output/Addons/Main'/version/'WoWDanceStudio'
    destination.mkdir(parents=True,exist_ok=True)
    for name in names:
        target=destination/name
        if target.exists() and digest(target)!=digest(SOURCE/name):raise ValueError('Published main addon changed: '+str(target))
        if not target.exists():shutil.copyfile(SOURCE/name,target)
    if not (destination/'Data.lua').exists():
        (destination/'Data.lua').write_text('WoWDanceStudioData = {schema=1,audioMode="addon",emotes={}}\n',encoding='utf-8')
    if not (destination/'silence.wav').exists():
        with wave.open(str(destination/'silence.wav'),'wb') as sound:
            sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(44100);sound.writeframes(b'\0'*8820)
    note=destination/'INSTALL.txt'
    if not note.exists():note.write_text('Install this WoWDanceStudio folder once under Interface/AddOns. This reusable runtime has an empty Data.lua; apply the final combined pack Interface folder afterward to install its dance catalog. Later packs normally update Data.lua only. To update code and catalog together, check Include main addon code update when building the pack. SavedVariables are preserved.\n',encoding='utf-8')
    result=dict(version=version,folder=str(destination))
    atomic_json(ROOT/'Output/Addons/Main/latest.json',result)
    return result


def generate(pack,audio_mode='native',include_code=True):
    pack=Path(pack).resolve()
    if not pack.is_relative_to((ROOT/'Output/Packs').resolve()):raise ValueError('Addon output must be in a project pack')
    manifest=json.loads((pack/'manifest.json').read_text(encoding='utf-8'))
    texts=DBC.read(pack/'Client/DBFilesClient/EmotesText.dbc')
    tokens={}
    for row in texts.rows:tokens.setdefault(row[2],[]).append(texts.text(row[1]))
    entries={e['id']:dict(id=e['id'],name=e['name'],models=[]) for e in read_catalog()['emotes']}
    for row in manifest['models']:
        meta=json.loads((pack/'Metadata'/(row['model']+'.json')).read_text(encoding='utf-8'))
        paths=meta['client_model_path_candidates']
        if len(paths)!=1:raise ValueError('Addon needs one client path per model')
        path=PureWindowsPath(paths[0]).with_suffix('.m2');race=re.sub(r'\d+$','',path.parts[1]).lower();sex=path.parts[2].lower()
        model_file=pack/'Client'/Path(*path.parts)
        if not model_file.is_file():model_file=next(model_file.parent.glob('*.m2'))
        native=Model(model_file.read_bytes())
        for dance in meta['dances']:
            identifier=dance['emote'];entry=entries.setdefault(identifier,dict(id=identifier,name=identifier,models=[]))
            if not re.fullmatch('[a-z][a-z0-9]*',identifier):raise ValueError('Unsafe addon emote alias')
            available=sorted(tokens.get(dance['emote_id'],[]))
            token=next((t for t in available if re.sub('[^a-z0-9]','',t.lower()).removeprefix('wds')==identifier),None)
            index=native.lookup[dance['animation_id']];duration=struct.unpack_from('<I',native.sequences,index*64+4)[0]
            item=dict(path=str(path),race=race,sex=sex,animationID=dance['animation_id'],durationMS=duration,token=token)
            if dance.get('native_loop_region'):item['loopStartMS']=dance['native_loop_region']['start_ms']
            audio=dance.get('client_audio')
            if audio:item['audio']=str(PureWindowsPath(audio['client_directory'])/audio['client_file'])
            item['nativeLoop']=not bool(struct.unpack_from('<I',native.sequences,index*64+12)[0]&1)
            item['loop']=item['nativeLoop']
            full=dance.get('full_soundtrack',{})
            for role,asset in full.items():
                sound=str(PureWindowsPath(asset['client_directory'])/asset['client_file'])
                if role=='intro':item.update(audioIntro=sound,introMS=asset['duration_ms'])
                elif role in ('track','loop'):item.update(audio=sound,audioDurationMS=asset['duration_ms'])
            entry['models'].append(item)
    destination=pack/'Interface/AddOns/WoWDanceStudio';destination.mkdir(parents=True,exist_ok=True)
    main=publish_main()
    if include_code:
        for name in ('WoWDanceStudio.toc','Core.lua','Collection.lua'):shutil.copyfile(SOURCE/name,destination/name)
    data=dict(schema=1,audioMode=audio_mode,emotes=sorted(entries.values(),key=lambda e:e['name'].casefold()))
    (destination/'Data.lua').write_text('-- Generated from this pack; do not mix catalogs from other packs.\nWoWDanceStudioData = '+lua(data)+'\n',encoding='utf-8')
    if include_code:
        shutil.copyfile(Path(main['folder'])/'silence.wav',destination/'silence.wav')
    else:
        for name in ('WoWDanceStudio.toc','Core.lua','Collection.lua','silence.wav'):
            if (destination/name).exists():(destination/name).unlink()
    (destination/'README.txt').write_text('''Install this WoWDanceStudio folder under your client Interface/AddOns, then restart the client (or /reload for Lua changes).
/wds opens the collection. /autumntea and other included dance aliases play their DBC tokens. /wds stop stops the dance; /wds music toggles addon music. Existing slash commands are preserved; /wds <emote> remains available if an alias conflicts.
Gray entries are not included for your current model. Preview animates the dressed character model only. Favorites are saved per account. Preview rendering requires the matching installed M2 and extended-animation DLL.
Addon-managed music uses the Music channel and stops on movement, jumping/falling, death, casting, combat or another DoEmote call. Keep Music enabled. This controls your own playback; it does not synchronize nearby players. Other addons that use PlayMusic share this channel. Native-audio packs cannot be stopped by this addon; build an addon-managed pack instead. Do not mix native and addon-managed custom MPQs.
Install Client/ contents in your MPQ with Character, DBFilesClient and Sound at its root. Install Interface/ as an ordinary client folder, outside the MPQ. Existing original model companions remain in baseline client patches.
''',encoding='utf-8')
    manifest['addon']=dict(folder='Interface/AddOns/WoWDanceStudio',audio_mode=audio_mode,emotes=len(data['emotes']),included=sum(bool(e['models']) for e in data['emotes']),runtime_verified=False,
                          includes_runtime=bool(include_code),required_runtime=main)
    if not include_code:
        readme=destination/'README.txt'
        readme.write_text('CATALOG UPDATE ONLY: this folder contains Data.lua, not the addon runtime. Keep the installed main addon. For a first installation, install the matching main addon from '+main['folder']+' before applying this catalog. Required runtime version: '+main['version']+'.\n\n'+readme.read_text(encoding='utf-8'),encoding='utf-8')
    manifest['checksums']={str(p.relative_to(pack)):digest(p) for p in pack.rglob('*') if p.is_file() and p.name!='manifest.json'}
    atomic_json(pack/'manifest.json',manifest)
    return manifest['addon']
