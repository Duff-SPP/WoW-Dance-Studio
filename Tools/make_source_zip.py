"""Build an audited source archive without local inputs or generated files."""
import argparse
from pathlib import Path
import zipfile
from check_release import ROOT, check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'WoW-Dance-Studio-source.zip')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Output already exists; choose a new filename to preserve the previous archive.')
    paths, errors = check()
    if errors:
        raise SystemExit('\n'.join(errors))
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, 'WoW-Dance-Studio/' + path.relative_to(ROOT).as_posix())
    print(f'Created {output} ({len(paths)} source files; no user inputs or generated output).')


if __name__ == '__main__':
    main()
