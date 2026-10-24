"""Independently validate the files listed by the completed batch exporter."""
import argparse
import hashlib
import json
import re
import struct
import wave
from pathlib import Path


def read_exact(stream, size):
    if size < 0:
        raise ValueError('Negative field size')
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Truncated container')
    return data


def read_string(stream):
    size, = struct.unpack('<i', read_exact(stream, 4))
    if not 0 <= size <= 65536:
        raise ValueError('Invalid UEFormat string size')
    return read_exact(stream, size).decode('utf-8')


def verify_animation(path, allow_large=False):
    with path.open('rb') as stream:
        if read_exact(stream, 8) != b'UEFORMAT' or read_string(stream) != 'UEANIM':
            raise ValueError('Not a UEFormat animation')
        version = read_exact(stream, 1)[0]
        if version != 10:
            raise ValueError(f'Unexpected container version {version}')
        name, source = read_string(stream), read_string(stream)
        if not name or not source:
            raise ValueError('Missing source identity')
        if not allow_large and re.search(r'(?:^|[_/])CL[MF](?:[_/.]|$)', source, re.I):
            raise ValueError('Large-body animation in export')
        compressed = read_exact(stream, 1)[0]
        if compressed != 1 or read_string(stream) != 'ZSTD':
            raise ValueError('Unexpected compression setting')
        unpacked, packed = struct.unpack('<ii', read_exact(stream, 8))
        remaining = path.stat().st_size - stream.tell()
        if unpacked <= 0 or packed != remaining or packed < 4:
            raise ValueError('Invalid compressed payload size')
        if read_exact(stream, 4) != b'\x28\xb5\x2f\xfd':
            raise ValueError('Invalid Zstandard frame magic')
    return {'name': name, 'source': source, 'version': version,
            'compressed_bytes': packed, 'uncompressed_bytes': unpacked}


def verify_audio(path):
    with wave.open(str(path), 'rb') as sound:
        frames, rate = sound.getnframes(), sound.getframerate()
        if frames <= 0 or rate <= 0:
            raise ValueError('Empty WAV audio')
        frame_size = sound.getnchannels() * sound.getsampwidth()
        count = 0
        while block := sound.readframes(65536):
            count += len(block)
        if count != frames * frame_size:
            raise ValueError('Truncated WAV sample data')
        return {'frames': frames, 'sample_rate': rate,
                'channels': sound.getnchannels(), 'duration_seconds': frames / rate}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report_root', type=Path)
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    root = args.report_root.resolve()
    selection = json.loads((root / 'selection.json').read_text(encoding='utf-8'))
    ready = {row['Id']: row for row in selection['Items'] if row['Status'] == 'ready'}
    records = json.loads((root / 'exports.json').read_text(encoding='utf-8'))
    unique_files, errors, no_audio = {}, [], []
    complete = set()
    for record in records:
        identifier = record['Id']
        if identifier not in ready:
            errors.append(f'Unselected emote exported: {identifier}')
            continue
        if record['Status'] != 'complete':
            errors.append(f'{identifier}: {record["Error"]}')
            continue
        complete.add(identifier)
        if {v['Label'] for v in record['Variants']} != {'Male Medium', 'Female Medium'}:
            errors.append(f'{identifier}: missing medium pair')
        for variant in record['Variants']:
            approved = next(v for v in ready[identifier]['Variants'] if v['Label'] == variant['Label'])
            if variant['Montage'] != approved['MontagePath']:
                errors.append(f'{identifier}: unexpected montage')
            if variant['AudioReferences'] == 0:
                no_audio.append(f'{identifier}: {variant["Label"]}')
            for file in variant['Files']:
                path = Path(file['Path'])
                key = str(path).lower()
                if key in unique_files:
                    if unique_files[key]['sha256'] != file['Sha256']:
                        errors.append(f'Conflicting file hashes: {path}')
                    continue
                try:
                    if not path.is_file() or path.stat().st_size != file['Bytes']:
                        raise ValueError('Missing file or size mismatch')
                    with path.open('rb') as stream:
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if digest != file['Sha256']:
                        raise ValueError('SHA-256 mismatch')
                    details = verify_audio(path) if file['Kind'] == 'audio' else verify_animation(path)
                    if file['Kind'] == 'animation' and details['source'] not in approved['AnimationPaths']:
                        raise ValueError('Animation source was not in the approved medium graph')
                    unique_files[key] = {'path': str(path), 'kind': file['Kind'],
                                         'sha256': digest, 'bytes': file['Bytes'], **details}
                except (OSError, ValueError, wave.Error) as error:
                    errors.append(f'{path}: {error}')
    missing = sorted(set(ready) - complete)
    if missing and not args.partial:
        errors.append(f'{len(missing)} selected emotes are not complete')
    result = {
        'complete_emotes': len(complete), 'selected_emotes': len(ready),
        'animation_files': sum(f['kind'] == 'animation' for f in unique_files.values()),
        'audio_files': sum(f['kind'] == 'audio' for f in unique_files.values()),
        'total_bytes': sum(f['bytes'] for f in unique_files.values()),
        'errors': errors, 'variants_without_audio_references': no_audio,
        'missing': missing, 'files': list(unique_files.values()),
    }
    (root / 'verification.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files' and k != 'missing'}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
