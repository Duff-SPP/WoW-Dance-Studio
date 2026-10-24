"""Cached plan resolution without changing the conversion implementation identity."""
import copy
import json
from functools import lru_cache
from . import montage


@lru_cache(maxsize=1)
def document(path,stamp):
    value=json.loads(path.read_text(encoding='utf-8'))
    stat=path.stat()
    if (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)!=stamp:
        raise ValueError('Montage plans changed while reading; retry')
    return value


def playback(emote,variant):
    path=montage.PLANS
    if not path.is_file():return None
    stat=path.stat()
    plans_document=document(path,(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
    identifiers=emote.get('export_ids',[]) or [emote.get('export_id')]
    plans=[plans_document['emotes'][i]['variants'].get(variant) for i in identifiers if i in plans_document['emotes']]
    plans=[p for p in plans if p]
    if not plans:return None
    if any(p!=plans[0] for p in plans[1:]):raise ValueError('Favorite aliases have differing montage playback plans')
    return copy.deepcopy(plans[0])
