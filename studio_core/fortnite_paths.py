"""Read-only original inputs plus separately managed additional imports."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'Input/Fortnite'
IMPORTED=ROOT/'Output/FortniteImports'


def asset_roots(folder):
    folder=Path(folder).resolve()
    roots=[folder]
    if folder in (INPUT.resolve(),(INPUT/'Assets').resolve()) and IMPORTED.is_dir():roots.append(IMPORTED.resolve())
    return roots


def allowed_audio(path):
    path=Path(path).resolve()
    return any(path.is_relative_to(root.resolve()) for root in (INPUT,IMPORTED))
