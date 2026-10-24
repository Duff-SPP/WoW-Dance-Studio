"""Target-aware selection; never silently substitute the opposite sex."""
from pathlib import Path
import re


def main_performance(candidates):
    """Exclude named auxiliary clips, but never guess between multiple main clips.

    Intro/loop-only exports need composition and deliberately remain ambiguous.
    All source clips stay cataloged; only automatic selection changes.
    """
    if len(candidates)==1:
        return candidates[0]
    auxiliary={'static','additive','additiveidentity','traverse','traversal','intro','loop','cycle','breakout'}
    main=[]
    for candidate in candidates:
        tokens=set(re.split(r'[^a-z0-9]+',Path(candidate['path']).stem.casefold()))
        if not tokens.intersection(auxiliary):
            main.append(candidate)
    if len(main)==1:
        return main[0]
    raise ValueError('Variant is missing or ambiguous; no unique main performance')


def model_sex(model):
    # A basename or nearest asset folder takes precedence over project folders.
    for value in (model.get('sex',''), *reversed(Path(model.get('path','')).parts), model.get('id','')):
        value=value.casefold()
        if 'female' in value: return 'F'
        if 'male' in value: return 'M'
    return None


def source_candidate(skeletons, variant):
    """Pick a candidate, not a compatibility verdict. Blender checks it at import.

    CMF/CMM describes the performance, not necessarily a different skeleton.
    Keep ambiguity explicit rather than picking an arbitrary file.
    """
    sex=variant[-1] if variant in {'CMM','CMF','CLM','CLF'} else None
    matching=[p for p in skeletons if sex and model_sex({'path':str(p)})==sex]
    candidates=matching if matching else list(skeletons)
    return candidates[0] if len(candidates)==1 else None


def resolve_variant(emote, target, requested='AUTO', model=None):
    if requested.upper()!='AUTO': return requested.upper()
    from .models import get_model
    sex=model_sex(model if model is not None else get_model(target))
    if sex is None: raise ValueError('Target sex is unknown; select an explicit emote variant')
    available={v['variant'] for v in emote['variants']}
    for variant in ('CM'+sex,'CL'+sex):
        if variant in available: return variant
    raise ValueError('No '+('female' if sex=='F' else 'male')+' emote variant exported')
