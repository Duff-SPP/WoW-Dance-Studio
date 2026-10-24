from pathlib import Path


def discover(wow, emotes):
    result = []
    for category, folder in [('wow', wow), ('fortnite', emotes)]:
        folder = Path(folder).resolve()
        if not folder.is_dir():
            raise ValueError(f'Missing asset directory: {folder}')
        for file in sorted(folder.rglob('*')):
            if file.is_file():
                result.append(dict(category=category, original_path=str(file),
                                   name=file.name, extension=file.suffix.lower(), bytes=file.stat().st_size))
    return result

