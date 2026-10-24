"""Crash-safe JSON replacement and OS-released cross-process locks."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time


class ContentChecks:
    """Reuse a hash only while the file's identity and metadata remain unchanged."""
    def __init__(self,hash_file):
        self.hash_file=hash_file
        self.entries={}

    @staticmethod
    def stamp(path):
        stat=path.stat()
        return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns

    def digest(self,path):
        path=Path(path)
        key=str(path.absolute())
        before=self.stamp(path)
        previous=self.entries.get(key)
        if previous is not None and previous[0]==before: return previous[1]
        value=self.hash_file(path)
        if self.stamp(path)!=before: raise ValueError('File changed during checksum verification: '+str(path))
        if len(self.entries)>=4096: self.entries.clear()
        self.entries[key]=(before,value)
        return value


def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2); stream.flush(); os.fsync(stream.fileno())
        # Windows readers (including the GUI's Get-Content) can briefly open
        # the destination without delete sharing, blocking atomic replacement.
        deadline=time.monotonic()+2
        while True:
            try:
                os.replace(name,path)
                break
            except OSError as error:
                if getattr(error,'winerror',None) not in {5,32,33} or time.monotonic()>=deadline:raise
                time.sleep(.025)
    finally:
        if Path(name).exists(): Path(name).unlink()


@contextmanager
def locked(path,timeout=0):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if not stream.tell(): stream.write(b'0'); stream.flush()
        stream.seek(0)
        deadline=time.monotonic()+timeout
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic()>=deadline: raise RuntimeError('Another operation owns '+str(path)) from error
                time.sleep(.05)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream,fcntl.LOCK_UN)
