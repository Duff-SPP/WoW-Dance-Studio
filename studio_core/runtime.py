"""Local machine defaults; this file contains no game assets."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def defaults():
    path = ROOT / 'studio.local.json'
    settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    return {
        'blender': os.environ.get('WDS_BLENDER') or settings.get('blender') or
                   r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
        'scene': settings.get('scene') or str(ROOT / 'Blender/PreparedSource.blend'),
    }
