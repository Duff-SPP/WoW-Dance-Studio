"""Strict lossless WDBC reader and append-only writer; standard library only."""
import hashlib
import math
import struct
from pathlib import Path
from .dbc_schema import SCHEMAS,REFERENCES,PRIMARY

HEADER=struct.Struct('<4s4I')


class DBCError(ValueError): pass


class DBC:
    def __init__(self,data,name):
        self.data=bytes(data)
        if name not in SCHEMAS: raise DBCError('Unsupported table schema: '+name)
        self.schema=SCHEMAS[name]; self.name=name
        if len(data)<20: raise DBCError('Truncated WDBC header')
        magic,self.count,fields,size,strings=HEADER.unpack_from(data)
        if magic!=b'WDBC': raise DBCError('Unsupported format '+repr(magic)+'; requires WDBC 12340')
        if fields!=len(self.schema.fields) or size!=self.schema.size:
            raise DBCError(f'{name}: unsupported layout {fields} fields / {size} bytes; expected {len(self.schema.fields)} / {self.schema.size}')
        end=20+self.count*size
        if end+strings!=len(data): raise DBCError('File size disagrees with record/string counts')
        self.records=data[20:end]; self.strings=data[end:]
        self.unpacker=struct.Struct('<'+'I'*fields)
        self.rows=list(self.unpacker.iter_unpack(self.records))
        self.ids={}; self.duplicates=[]; self._texts={}
        for row in self.rows:
            if row[0] in self.ids: self.duplicates.append(row[0])
            self.ids[row[0]]=row
            for column in self.schema.strings: self.text(row[column])
            for column in self.schema.floats:
                if not math.isfinite(self.f32(row[column])): raise DBCError(f'{name} ID {row[0]}: nonfinite float column {column}')
        self.sha256=hashlib.sha256(data).hexdigest()

    @classmethod
    def read(cls,path,name=None):
        path=Path(path)
        return cls(path.read_bytes(),name or path.stem)

    @staticmethod
    def f32(word): return struct.unpack('<f',struct.pack('<I',word))[0]

    @staticmethod
    def i32(word): return struct.unpack('<i',struct.pack('<I',word))[0]

    def text(self,offset):
        if offset in self._texts: return self._texts[offset]
        if not self.strings and offset==0: return ''
        if offset>=len(self.strings): raise DBCError(f'{self.name}: string offset outside block: {offset}')
        end=self.strings.find(b'\0',offset)
        if end<0: raise DBCError(f'{self.name}: unterminated string at {offset}')
        try: value=self.strings[offset:end].decode('utf-8')
        except UnicodeDecodeError as error: raise DBCError(f'{self.name}: invalid UTF-8 string at {offset}') from error
        self._texts[offset]=value
        return value

    def values(self,row):
        return [self.text(word) if i in self.schema.strings else word for i,word in enumerate(row)]

    def append(self,additions):
        if self.duplicates: raise DBCError(self.name+': duplicate IDs in baseline')
        if not additions: return self.data
        block=bytearray(self.strings)
        if not block: block.extend(b'\0')
        strings={self.text(offset):offset for row in self.rows for i,offset in enumerate(row) if i in self.schema.strings}
        ids=set(self.ids); records=[]
        for values in additions:
            if len(values)!=len(self.schema.fields): raise DBCError('New record has incorrect field count')
            if values[0] in ids: raise DBCError(f'{self.name}: duplicate/conflicting ID {values[0]}')
            ids.add(values[0]); words=[]
            for i,value in enumerate(values):
                if i in self.schema.strings:
                    if not isinstance(value,str) or '\0' in value: raise DBCError('Invalid new string')
                    if value not in strings:
                        strings[value]=len(block); block.extend(value.encode('utf-8')+b'\0')
                    value=strings[value]
                if not isinstance(value,int) or isinstance(value,bool) or not 0<=value<=0xffffffff:
                    raise DBCError('New word is not an unsigned 32-bit bit pattern')
                words.append(value)
            records.append(self.unpacker.pack(*words))
        result=HEADER.pack(b'WDBC',self.count+len(records),len(self.schema.fields),self.schema.size,len(block))+self.records+b''.join(records)+block
        reopened=DBC(result,self.name)
        if reopened.records[:len(self.records)]!=self.records or reopened.strings[:len(self.strings)]!=self.strings:
            raise DBCError('Original record/string bytes changed')
        return result

    def summary(self):
        return dict(file=self.name+'.dbc',valid=not self.duplicates,format='WDBC',build_layout=12340,
                    records=self.count,fields=len(self.schema.fields),record_size=self.schema.size,
                    highest_id=max(self.ids,default=None),duplicate_ids=sorted(set(self.duplicates)),sha256=self.sha256)


def load_tables(folder):
    folder=Path(folder)
    if not folder.is_dir(): raise DBCError('DBC input folder does not exist: '+str(folder))
    paths={}; unknown=[]
    for path in sorted(folder.iterdir()):
        if path.suffix.lower()!='.dbc' or not path.is_file(): continue
        name=next((n for n in SCHEMAS if n.casefold()==path.stem.casefold()),None)
        if name:
            if name in paths: raise DBCError('Multiple baseline files for '+name)
            paths[name]=path
        else: unknown.append(dict(file=path.name,valid=False,status='Unsupported table schema',sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    tables={}; status=unknown
    for name in SCHEMAS:
        if name not in paths:
            status.append(dict(file=name+'.dbc',valid=False if name in PRIMARY else None,status='Missing primary' if name in PRIMARY else 'Missing optional'))
            continue
        try:
            table=DBC.read(paths[name],name); tables[name]=table; status.append(table.summary())
        except (DBCError,OSError) as error:
            data=paths[name].read_bytes(); row=dict(file=name+'.dbc',valid=False,error=str(error),sha256=hashlib.sha256(data).hexdigest())
            if len(data)>=20:
                magic,count,fields,size,_=HEADER.unpack_from(data)
                row.update(format=magic.decode('ascii',errors='replace'),records=count,fields=fields,record_size=size)
            status.append(row)
    return tables,status


def reference_errors(tables,only_ids=None):
    errors=[]
    for name,refs in REFERENCES.items():
        if name not in tables: continue
        for row in tables[name].rows:
            if only_ids is not None and row[0] not in only_ids.get(name,set()): continue
            for column,target,zero_ok in refs:
                value=row[column]
                if zero_ok and value==0: continue
                if target not in tables or value not in tables[target].ids:
                    errors.append(dict(table=name,id=row[0],column=column,target=target,value=value))
    return errors
