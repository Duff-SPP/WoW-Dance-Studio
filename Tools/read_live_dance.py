"""Read-only animation state capture. Never suspends threads or writes client memory."""
import argparse,ctypes as C,json,struct,time
from ctypes import wintypes as W
from pathlib import Path
K=C.WinDLL('kernel32',use_last_error=True);N=C.WinDLL('ntdll')
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenProcess.restype=W.HANDLE
K.OpenThread.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenThread.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE]
K.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];K.CreateToolhelp32Snapshot.restype=W.HANDLE
K.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
class TE(C.Structure):
    _fields_=[('size',W.DWORD),('usage',W.DWORD),('tid',W.DWORD),('pid',W.DWORD),('pri',W.LONG),('delta',W.LONG),('flags',W.DWORD)]
class TBI(C.Structure):
    _fields_=[('status',W.LONG),('teb',C.c_void_p),('pid',C.c_void_p),('tid',C.c_void_p),('affinity',C.c_size_t),('pri',W.LONG),('base',W.LONG)]
K.Thread32First.argtypes=[W.HANDLE,C.POINTER(TE)];K.Thread32Next.argtypes=[W.HANDLE,C.POINTER(TE)]
N.NtQueryInformationThread.argtypes=[W.HANDLE,W.ULONG,C.c_void_p,W.ULONG,C.c_void_p]


def capture(pid):
    process=K.OpenProcess(0x410,False,pid)
    if not process:raise C.WinError(C.get_last_error())
    def read(a,n):
        if not a or not 0<n<=65536:return None
        b=C.create_string_buffer(n);got=C.c_size_t()
        return b.raw if K.ReadProcessMemory(process,a,b,n,C.byref(got)) and got.value==n else None
    def u(a):
        b=read(a,4);return struct.unpack('<I',b)[0] if b else 0
    result=dict(pid=pid,read_only=True,managers=[],models=[],hooks={})
    try:
        for a in (0x82f4f9,0x82f618):
            b=read(a,9);result['hooks'][hex(a)]=b.hex() if b else None
        snapshot=K.CreateToolhelp32Snapshot(4,0);entry=TE();entry.size=C.sizeof(entry)
        ok=K.Thread32First(snapshot,C.byref(entry));managers=set()
        while ok:
            if entry.pid==pid:
                thread=K.OpenThread(0x40,False,entry.tid)
                if thread:
                    info=TBI()
                    if N.NtQueryInformationThread(thread,0,C.byref(info),C.sizeof(info),None)==0:
                        for teb in (info.teb,info.teb+0x2000,info.teb-0x2000):
                            if teb>0xffffffff:continue
                            # Validate self/owner before following a WOW64 TLS pointer.
                            if u(teb+0x18)==teb and u(teb+0x20)==pid and u(teb+0x24)==entry.tid:
                                slot=u(0xd439bc)
                                if slot<1024:
                                    mgr=u(u(u(teb+0x2c)+slot*4)+8)
                                    if mgr:managers.add(mgr)
                    K.CloseHandle(thread)
            ok=K.Thread32Next(snapshot,C.byref(entry))
        K.CloseHandle(snapshot)
        for mgr in managers:
            guid=read(mgr+0xc0,8)
            if not guid or guid==b'\0'*8:continue
            lo,hi=struct.unpack('<II',guid);mask=u(mgr+0x24);buckets=u(mgr+0x1c)
            if mask==0xffffffff or mask>0xfffff:continue
            bucket=buckets+(mask&lo)*12;node=u(bucket+8);seen=set();player=0
            while node and not node&1 and node not in seen and len(seen)<4096:
                seen.add(node)
                if u(node+0x18)==lo and read(node+0x30,8)==guid:player=node;break
                node=u((node+u(bucket)+4)&0xffffffff)
            result['managers'].append(dict(manager=hex(mgr),player=hex(player)))
            if not player:continue
            descriptors=u(player+8)
            result['unit_fields_hex']=read(descriptors,0x280).hex() if descriptors and read(descriptors,0x280) else None
            for offset in range(0,0x1800,4):
                model=u(player+offset);shared=u(model+0x2c) if model else 0;data=u(shared+0x150) if shared else 0
                count=u(data+0x1c) if data else 0
                if not 100<=count<1024:continue
                sequences=u(data+0x20);raw=read(sequences,count*64)
                if not raw or not any(struct.unpack_from('<H',raw,i*64)[0]==1797 for i in range(count)):continue
                bone_count=u(data+0x2c);bones=u(model+0x94)
                if not 10<bone_count<1000 or not bones:continue
                controllers=[]
                for i in range(bone_count):
                    b=read(bones+i*0xac,0xac)
                    if not b:break
                    idx=struct.unpack_from('<H',b,0x48)[0]
                    if idx!=65535:
                        controllers.append(dict(bone=i,time=struct.unpack_from('<I',b,0x40)[0],index=idx,
                            anim=struct.unpack_from('<H',raw,idx*64)[0] if idx<count else None,
                            start=struct.unpack_from('<I',b,0x4c)[0],end=struct.unpack_from('<I',b,0x50)[0],
                            rate=struct.unpack_from('<f',b,0x54)[0],offset=struct.unpack_from('<I',b,0x5c)[0]))
                result['models'].append(dict(unit_offset=hex(offset),model=hex(model),shared=hex(shared),
                    name=(read(shared+0x3c,160) or b'').split(b'\0')[0].decode('ascii','replace'),
                    scene_time=u(u(model+0x28)+0xc),model_time=u(model+0x64),controllers=controllers))
        return result
    finally:K.CloseHandle(process)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('--output',default='Reports/live_dance_state.json');a=p.parse_args()
    result=capture(a.pid);Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='unit_fields_hex'},indent=2))
