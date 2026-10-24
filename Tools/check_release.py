"""Audit publishable source; runtime files are excluded from source archives."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = {'Input', 'Output', 'Reports', 'Blender', 'Profiles'}
ALLOWED = {'.py', '.ps1', '.cmd', '.md', '.txt', '.json', '.patch', '.lua', '.toc', '.cs', '.cpp', '.hpp'}
SPECIAL = {'.gitignore', '.gitattributes', '.gitkeep', 'LICENSE'}
TEMPLATE = 'Profiles/Clients/conservative.example.json'


def sources():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in {'.git', '__pycache__', '.venv', 'venv', '.idea', '.vscode', 'bin', 'obj'} for part in rel.parts):
            continue
        if path.name == 'studio.local.json':
            continue
        if rel.parts[0] in RUNTIME and path.name != '.gitkeep' and rel.as_posix() != TEMPLATE:
            continue
        yield path


def check():
    errors = []
    paths = list(sources())
    personal_path = re.compile(r'[A-Za-z]:[\\/]Users[\\/][^\s"\'<>]+', re.I)
    secret = re.compile(r'\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() not in ALLOWED and path.name not in SPECIAL:
            errors.append('Unapproved source file type: ' + rel)
            continue
        try:
            content = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            errors.append('Non-text content: ' + rel)
            continue
        if personal_path.search(content):
            errors.append('Personal Windows path: ' + rel)
        if secret.search(content):
            errors.append('Potential credential/private key: ' + rel)
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', content):
                if '://' in target or target.startswith('#'):
                    continue
                destination = target.split('#')[0]
                if destination and not (path.parent / destination).exists():
                    errors.append('Missing documentation target: ' + rel + ' -> ' + destination)
    for name in ('LICENSE', 'LICENSES/GPL-2.0-or-later.txt', 'README.md', '.gitignore', 'docs/SETUP.md', 'docs/USAGE.md'):
        if not (ROOT / name).is_file():
            errors.append('Required release file missing: ' + name)
    # Catch accidentally force-added assets/settings when this is a Git checkout.
    if (ROOT / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
        publishable = {p.relative_to(ROOT).as_posix() for p in paths}
        for raw in result.stdout.decode().split('\0'):
            if raw and raw not in publishable:
                errors.append('Tracked local asset/state file: ' + raw)
    return paths, errors


def main():
    paths, errors = check()
    for error in errors:
        print(error, file=sys.stderr)
    print(f'Public source audit: {len(paths)} files; {len(errors)} errors. Local assets/state are excluded.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
