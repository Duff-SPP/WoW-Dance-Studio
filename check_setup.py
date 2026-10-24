"""Check the running Python or Blender environment without importing assets."""
import importlib
import sys


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ is required (hashlib.file_digest).')
    print('Python:', sys.version.split()[0])
    try:
        import bpy
    except ImportError:
        print('Python check passed. Run Setup.ps1 -CheckImporters for the Blender checks.')
        return
    print('Blender:', bpy.app.version_string)
    requirements = {
        'bl_ext.user_default.elune_m2.m2_import.factory': ('load_model',),
        'bl_ext.user_default.elune_m2.m2_import.builder': ('build',),
        'fortnite_porting.ueformat.importer.import_context': ('UEFormatImport',),
        'fortnite_porting.ueformat.options': ('UEModelOptions', 'UEAnimOptions'),
    }
    for name, attributes in requirements.items():
        module = importlib.import_module(name)
        for attribute in attributes:
            if not hasattr(module, attribute):
                raise RuntimeError(f'Required importer API missing: {name}.{attribute}')
        print('Importer available:', name)
    print('Importer checks passed. This does not certify asset conversion or client playback.')


if __name__ == '__main__':
    main()
