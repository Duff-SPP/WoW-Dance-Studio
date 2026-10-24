"""Exported emote soundtrack discovery, independent of Blender."""
from pathlib import Path
import re

AUDIO_EXTENSIONS = {'.wav', '.ogg', '.flac', '.mp3'}


def normalized(value):
    value = re.sub(r'[^a-z0-9]', '', value.lower())
    return value.removeprefix('emote')


def audio_files(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)


def tokens(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r'(?<![a-z0-9])(intro|loop)(\d+)(?![a-z0-9])', r'\1 \2', value, flags=re.IGNORECASE)
    return re.findall(r"[a-z0-9]+", value.lower())


VARIANTS = {'cmm','cmf','clm','clf','male','female','test','static'}
LABELS = {'mx','pl','music','bgm','audio','soundtrack','theme','mix','master','final','stereo','mono','cue'}
EFFECTS = {'sfx','foley','voice','vo','footstep','footsteps','soundeffect','soundeffects'}


def action_aliases(action):
    # Blender disambiguates an imported action with .001, .002, etc. This is
    # an action datablock suffix, not part of the exported emote identity.
    action = re.sub(r'\.\d{3}$', '', action)
    parts = tokens(action)
    aliases = {normalized(action)}
    while parts and parts[-1] in VARIANTS | {'intro','loop'}:
        parts.pop()
        aliases.add(normalized(''.join(parts)))
    return aliases - {''}


def build_audio_index(folder):
    """Parse the filesystem once; share this index across catalog families."""
    root = Path(folder).resolve()
    from .fortnite_paths import asset_roots
    roots=asset_roots(root)
    index = []
    for path in sorted({p for source in roots for p in audio_files(source)}):
        parts = tokens(path.stem)
        if any(part in EFFECTS for part in parts):
            continue
        roles = {part for part in parts if part in {'intro','loop'}}
        if len(roles) > 1:
            continue
        role = next(iter(roles), 'track')
        # Keep identity digits in names such as Dance2, while accepting export
        # suffixes after section/format labels (Loop_01, MX_v2_Loop).
        base = [part for part in parts if part not in roles]
        while base and (base[-1] in LABELS | VARIANTS or
                        ((roles or any(p in LABELS for p in parts)) and re.fullmatch(r'(?:v)?\d+',base[-1]))):
            base.pop()
        aliases = {normalized(''.join(base))}
        while base and base[0] in {'emote','music','mx','bgm','audio','soundtrack'}:
            base.pop(0)
            aliases.add(normalized(''.join(base)))
        ancestors = []
        parent = path.parent.resolve()
        scope=next(source for source in roots if path.resolve().is_relative_to(source))
        while parent.is_relative_to(scope):
            ancestors.append(parent)
            if parent == scope:
                break
            parent = parent.parent
        index.append(dict(path=path.resolve(),role=role,aliases=aliases-{''},ancestors=ancestors,
                          explicit_identity=path.stem.lower().startswith('emote'),
                          plain=all(part in {'intro','loop','music','audio','soundtrack'} for part in parts)))
    return dict(root=root,files=index)


def match_soundtrack(index, action):
    aliases = action_aliases(action)
    groups = {}
    for entry in index['files']:
        anchor = next((p for p in entry['ancestors'] if normalized(p.name) in aliases),None)
        exact = bool(entry['aliases'] & aliases)
        if entry['explicit_identity'] and not exact:
            continue  # A folder cannot override an explicit different emote.
        scoped = entry['plain'] and entry['path'].parent == index['root']
        if not exact and anchor is None and not scoped:
            continue
        score = 100 if exact else 60 if anchor is not None else 40
        if exact and anchor is not None:
            score += 20
        reason = 'filename and emote folder' if score==120 else 'filename identity' if exact else 'emote folder' if anchor else 'plain audio in selected folder'
        # Matching family folders permit Intro/Loop subdirectories. Separate
        # export roots remain separate alternatives rather than being merged.
        key = str(anchor or entry['path'].parent)
        groups.setdefault(key,[]).append(dict(**entry,score=score,reason=reason))
    if not groups:
        return {}, ['No matching soundtrack found for '+action], dict(status='missing',candidates=[])
    rank = max(max(row['score'] for row in group) for group in groups.values())
    winners = [group for group in groups.values() if max(row['score'] for row in group)==rank]
    candidates = [dict(path=str(row['path']),role=row['role'],reason=row['reason']) for group in groups.values() for row in group]
    details = dict(status='matched',candidates=candidates)
    if len(winners)!=1:
        details['status']='ambiguous'
        return {}, ['Multiple soundtrack locations match; scope the audio folder to the intended export.'], details
    rows = winners[0]
    if any(row['role'] in {'intro','loop'} for row in rows):
        rows = [row for row in rows if row['role']!='track']
    selected = {}
    for role in {row['role'] for row in rows}:
        options = [row for row in rows if row['role']==role]
        best = max(row['score'] for row in options)
        options = [row for row in options if row['score']==best]
        if len(options)!=1:
            details['status']='ambiguous'
            return {}, ['Multiple '+role+' files match; no soundtrack selected.'],details
        selected[role]=options[0]
    files = {role:row['path'] for role,row in selected.items()}
    details['reason'] = ', '.join(sorted({row['reason'] for row in selected.values()}))
    warnings = [] if 'track' in files else [role.capitalize()+' audio is missing.' for role in ['intro','loop'] if role not in files]
    return files,warnings,details


def select_soundtrack(folder, action):
    """Compatibility entry point used by Blender previews and legacy conversion."""
    files,warnings,_ = match_soundtrack(build_audio_index(folder),action)
    return files,warnings
