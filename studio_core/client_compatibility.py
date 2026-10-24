"""Conservative client limits backed by local binary/runtime evidence."""
import json
from pathlib import Path
from .catalog import ROOT,digest

PROFILE=ROOT/'Profiles/Clients/active.json'


def check_animation_ids(identifiers):
    if not PROFILE.exists():
        raise ValueError('Client compatibility is not configured. Read docs/CLIENT_COMPATIBILITY.md before native export.')
    profile=json.loads(PROFILE.read_text(encoding='utf-8-sig'))
    limit=profile.get('animation_id_limit_exclusive')
    if profile.get('schema')!=1 or not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=65535:
        raise ValueError('Invalid client compatibility profile: '+str(PROFILE))
    required=profile.get('required_client_dll')
    if required:
        binary=Path(required['path']).resolve()
        if not binary.is_relative_to((ROOT/'Output').resolve()) or not binary.is_file() or digest(binary)!=required['sha256']:
            raise ValueError('Required experimental client DLL is missing or changed; rebuild and revalidate the test package')
    installed=profile.get('installed_client_dll')
    if installed:
        binary=Path(installed['path'])
        if not binary.is_file() or digest(binary)!=installed['sha256']:
            raise ValueError('Installed client DLL differs from the tested version; restore the tested DLL or select the original-client compatibility profile')
    bad=sorted({identifier for identifier in identifiers if identifier>=limit})
    if bad:
        raise ValueError('Client compatibility blocked: animation IDs '+', '.join(map(str,bad))+
                         ' exceed the conservative limit '+str(limit-1)+' for '+profile['client']+
                         '. This client has crashed/frozen resolving extended animation IDs. An addon or server command does not fix the native resolver. No compatible append-only ID allocation has been established; existing IDs will not be overwritten. See '+str(PROFILE))
    return dict(profile=str(PROFILE),sha256=digest(PROFILE),limit_exclusive=limit,required_client_dll=required,client_playback_verified=False)
