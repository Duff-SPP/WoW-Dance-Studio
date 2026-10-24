"""Append-only flat Wrath MD20/264 animation tables and external key data.

Original payload offsets stay valid. Relocated tables retain original entries
and inner descriptors verbatim. No geometry, skin, collision or aliases rebuilt.
"""
import hashlib
import math
import struct

PAIR=struct.Struct('<II')
SEQUENCE=struct.Struct('<HHIfIHHIIHH6ffhH')
UNIT_SOUND_EVENT=b'$CSD'  # CUnit callback 0x732BDD -> 0x746D60; $SND is a visual-effect event.


class M2Error(ValueError): pass


def span(data,offset,size):
    if offset<0 or size<0 or offset+size>len(data): raise M2Error('M2/ANIM reference outside file')
    return bytes(data[offset:offset+size])


def append(buf,value):
    buf.extend(b'\0'*((-len(buf))%16)); offset=len(buf); buf.extend(value)
    return offset


def compressed_quat(values):
    if len(values)!=4 or any(not math.isfinite(v) for v in values): raise M2Error('Invalid quaternion')
    length=math.sqrt(sum(v*v for v in values))
    if abs(length-1)>1e-3: raise M2Error('Quaternion is not normalized')
    return struct.pack('<4h',*(max(-32768,min(32767,round(v*32767-32768 if v>=0 else v*32767+32767))) for v in values))


class Model:
    def __init__(self,data):
        self.data=bytes(data)
        if len(data)<304 or data[:4]!=b'MD20' or struct.unpack_from('<I',data,4)[0]!=264:
            raise M2Error('Only flat Wrath MD20 version 264 is supported')
        self.sequences=self.array(28,64); self.bones=self.array(44,88)
        self.lookup=list(struct.unpack('<'+'h'*(len(self.array(36,2))//2),self.array(36,2)))
        self.count=len(self.sequences)//64; self.bone_count=len(self.bones)//88
        if not self.count or not self.bone_count or self.count>32767: raise M2Error('Invalid sequence/bone count')
        for offset,label in ((264,'lights'),(288,'ribbon emitters'),(296,'particle emitters')):
            if PAIR.unpack_from(data,offset)[0]: raise M2Error('Append-only export does not yet support '+label)
        self.parents=[]
        for i in range(self.bone_count):
            parent=struct.unpack_from('<h',self.bones,i*88+8)[0]
            if parent<-1 or parent>=self.bone_count or parent==i: raise M2Error('Invalid bone parent')
            self.parents.append(parent)
        for i in range(self.bone_count):
            visited={i}; parent=self.parents[i]
            while parent>=0:
                if parent in visited: raise M2Error('Cyclic bone hierarchy')
                visited.add(parent); parent=self.parents[parent]
        if any(index>=self.count or index<-1 for index in self.lookup): raise M2Error('Invalid animation lookup index')

    def array(self,header,stride):
        count,offset=PAIR.unpack_from(self.data,header)
        return span(self.data,offset,count*stride) if count else b''

    def validate_load_ring(self,index):
        """Native 0x83DC05 follows uint16 links at +62 until it reaches its start.

        This is the shared animation-load ring, distinct from variation_next
        at +60. A standalone sequence must link to itself, not sequence zero.
        """
        start=index;seen=set();order=[]
        while index not in seen:
            if not 0<=index<self.count: raise M2Error('Animation load ring points outside sequence table')
            seen.add(index);order.append(index)
            index=struct.unpack_from('<H',self.sequences,index*64+62)[0]
            if index==start:return order
        raise M2Error('Animation load ring never returns to its starting sequence; native client would freeze')

    def descriptors(self,record,offset,event=False):
        interpolation,global_sequence=struct.unpack_from('<HH',record,offset)
        pairs=[]
        for j in range(1 if event else 2):
            count,pointer=PAIR.unpack_from(record,offset+4+j*8)
            if count>self.count and global_sequence==65535: raise M2Error('Track array exceeds sequence count')
            raw=span(self.data,pointer,count*8) if count else b''
            pairs.append([PAIR.unpack_from(raw,i*8) for i in range(count)])
        if any(pairs) and global_sequence!=65535 and global_sequence>=PAIR.unpack_from(self.data,20)[0]: raise M2Error('Invalid global sequence reference')
        if not event and len(pairs[0])!=len(pairs[1]): raise M2Error('Mismatched timestamp/value outer arrays')
        return interpolation,global_sequence,pairs

    def track_locations(self):
        # Camera tracks are independent character-selection camera motion and
        # are deliberately not extended with character animation sequences.
        for header,stride,tracks in ((44,88,((16,'vec3',None),(36,'quat',None),(56,'vec3',None))),
                (72,40,((0,'vec3',(1.,1.,1.)),(20,'short',(32767,)))),
                (88,20,((0,'short',(32767,)),)),
                (96,60,((0,'vec3',(0.,0.,0.)),(20,'floatquat',(0.,0.,0.,1.)),(40,'vec3',(1.,1.,1.)))),
                (240,40,((20,'byte',(1,)),)),(256,36,((24,'event',None),))):
            block=self.array(header,stride)
            yield header,stride,tracks,block


def pack_values(kind,values):
    if kind=='quat': return b''.join(compressed_quat(v) for v in values)
    formats={'vec3':'3f','floatquat':'4f','short':'h','byte':'B'}
    if kind not in formats: raise M2Error('Unsupported key type')
    if any(any(not math.isfinite(v) for v in value) for value in values): raise M2Error('Nonfinite animation value')
    return b''.join(struct.pack('<'+formats[kind],*value) for value in values)


def export_model(original,clips):
    model=Model(original); output=bytearray(original); anims={}; changed=[]
    ids={struct.unpack_from('<H',model.sequences,i*64)[0] for i in range(model.count)}
    if not clips: raise M2Error('Select at least one converted animation')
    if model.count+len(clips)>32767: raise M2Error('Sequence lookup exceeds signed int16 limit')
    for clip in clips:
        identifier=clip['animation_id']
        if not isinstance(identifier,int) or not 0<identifier<65535 or identifier in ids: raise M2Error('Animation ID collision or outside uint16 range')
        if identifier<len(model.lookup) and model.lookup[identifier]>=0: raise M2Error('Occupied original lookup ID')
        ids.add(identifier)
        if len(clip['bones'])!=model.bone_count: raise M2Error('Clip/raw bone count differs')
        times=clip['times']
        if len(times)<2 or any(not isinstance(t,int) or isinstance(t,bool) for t in times) or times[0]!=0 or times[-1]!=clip['duration'] or any(a>=b for a,b in zip(times,times[1:])):
            raise M2Error('Animation timestamps must be strictly increasing from zero to duration')
        if clip['duration']>600000 or clip['duration']<=0: raise M2Error('Unsupported animation duration')
        if len(clip['bounds'])!=7 or any(not math.isfinite(v) for v in clip['bounds']) or any(clip['bounds'][i]>clip['bounds'][i+3] for i in range(3)) or clip['bounds'][6]<0: raise M2Error('Invalid bounds')
        anims[identifier]=bytearray()
    for header,stride,tracks,old_block in model.track_locations():
        if not old_block: continue
        new_block=bytearray(old_block)
        for index in range(len(old_block)//stride):
            for local,kind,default in tracks:
                at=index*stride+local
                interpolation,global_sequence,pairs=model.descriptors(old_block,at,kind=='event')
                if global_sequence!=65535:
                    if header==44:
                        channel=(local-16)//20
                        expected=((0.,0.,0.),(0.,0.,0.,1.),(1.,1.,1.))[channel]
                        if any(any(abs(a-b)>1e-5 for a,b in zip(v,expected)) for clip in clips for v in clip['bones'][index][channel]):
                            raise M2Error('New motion conflicts with an original global-sequence bone track')
                    continue
                if kind!='event' and interpolation not in (0,1): raise M2Error('Unsupported original track interpolation')
                for entries in pairs: entries.extend([(0,0)]*(model.count-len(entries)))
                for clip in clips:
                    if kind=='event':
                        pairs[0].append((0,0)); continue
                    values=clip['bones'][index][(local-16)//20] if header==44 else [default]
                    if len(values) not in (1,len(clip['times'])): raise M2Error('Key count differs from timestamps')
                    if header==44 and not struct.unpack_from('<I',model.bones,index*88+4)[0]&0x200:
                        channel=(local-16)//20; identity=((0.,0.,0.),(0.,0.,0.,1.),(1.,1.,1.))[channel]
                        if any(any(abs(a-b)>1e-5 for a,b in zip(v,identity)) for v in values): raise M2Error('Motion on a bone without its original transform flag')
                    timestamps=[0] if len(values)==1 else clip['times']
                    binary=anims[clip['animation_id']]
                    ts_offset=append(binary,struct.pack('<'+'I'*len(timestamps),*timestamps))
                    key_offset=append(binary,pack_values(kind,values))
                    pairs[0].append((len(timestamps),ts_offset)); pairs[1].append((len(values),key_offset))
                for j,entries in enumerate(pairs):
                    pointer=append(output,b''.join(PAIR.pack(*entry) for entry in entries))
                    PAIR.pack_into(new_block,at+4+j*8,len(entries),pointer)
        pointer=append(output,new_block); PAIR.pack_into(output,header,len(old_block)//stride,pointer); changed.append((header,8))
    sound_clips=[(i,c) for i,c in enumerate(clips,model.count) if c.get('sound_id')]
    if sound_clips:
        event_count,event_pointer=PAIR.unpack_from(output,256)
        events=bytearray(span(output,event_pointer,event_count*36)) if event_count else bytearray()
        for sequence_index,clip in sound_clips:
            sound_id=clip['sound_id']
            if not isinstance(sound_id,int) or not 0<sound_id<0x100000000:raise M2Error('Invalid native soundtrack sound ID')
            entries=[(0,0)]*(model.count+len(clips))
            timestamp=append(anims[clip['animation_id']],struct.pack('<I',1))
            entries[sequence_index]=(1,timestamp)
            outer=append(output,b''.join(PAIR.pack(*entry) for entry in entries))
            events.extend(struct.pack('<4sII3fHHII',UNIT_SOUND_EVENT,sound_id,0,0.,0.,0.,0,65535,len(entries),outer))
        PAIR.pack_into(output,256,len(events)//36,append(output,events));changed.append((256,8))
    sequences=bytearray(model.sequences); lookup=list(model.lookup)
    for index,clip in enumerate(clips,model.count):
        # The native sampler clamps only when bit 0 is set; otherwise it uses
        # time modulo duration (CM2Model::AnimateMT). Copy blend settings from
        # this exact model's native dance, never its storage/alias/load bits.
        dance=next((at for at in range(model.count) if struct.unpack_from('<H',model.sequences,at*64)[0]==69),None)
        flags=(struct.unpack_from('<I',model.sequences,dance*64+12)[0]&0x80) if dance is not None else 0
        blend=struct.unpack_from('<H',model.sequences,dance*64+28)[0] if dance is not None else 0
        if not clip.get('loop',True):flags|=1
        sequences.extend(SEQUENCE.pack(clip['animation_id'],0,clip['duration'],0.,flags,32767,0,0,0,blend,0,*clip['bounds'],-1,index))
        if len(lookup)<=clip['animation_id']: lookup.extend([-1]*(clip['animation_id']+1-len(lookup)))
        lookup[clip['animation_id']]=index
    PAIR.pack_into(output,28,len(sequences)//64,append(output,sequences)); changed.append((28,8))
    PAIR.pack_into(output,36,len(lookup),append(output,struct.pack('<'+'h'*len(lookup),*lookup))); changed.append((36,8))
    bounds=list(struct.unpack_from('<7f',original,160))
    for clip in clips:
        for i in range(3): bounds[i]=min(bounds[i],clip['bounds'][i]); bounds[i+3]=max(bounds[i+3],clip['bounds'][i+3])
        bounds[6]=max(bounds[6],clip['bounds'][6])
    struct.pack_into('<7f',output,160,*bounds); changed.append((160,28))
    validation=verify_preservation(original,bytes(output),changed)
    return bytes(output),{key:bytes(value) for key,value in anims.items()},validation


def verify_preservation(original,result,allowed=None):
    before=Model(original); after=Model(result)
    for index in range(before.count,after.count): after.validate_load_ring(index)
    if after.sequences[:len(before.sequences)]!=before.sequences: raise M2Error('Original sequences/aliases changed')
    for identifier,old_index in enumerate(before.lookup):
        new_index=after.lookup[identifier]
        if new_index==old_index: continue
        if old_index>=0 or new_index<before.count or struct.unpack_from('<H',after.sequences,new_index*64)[0]!=identifier:
            raise M2Error('Original assigned lookup entry changed')
    for (header,stride,tracks,block),(_,_,_,new) in zip(before.track_locations(),after.track_locations()):
        for index in range(len(block)//stride):
            masked=bytearray(new[index*stride:(index+1)*stride]); expected=bytearray(block[index*stride:(index+1)*stride])
            for local,kind,_ in tracks:
                a=before.descriptors(block,index*stride+local,kind=='event'); b=after.descriptors(new,index*stride+local,kind=='event')
                if a[:2]!=b[:2] or any(y[:len(x)]!=x for x,y in zip(a[2],b[2])): raise M2Error('Original track descriptors/global sequences changed')
                size=12 if kind=='event' else 20; masked[local:local+size]=expected[local:local+size]
            if masked!=expected: raise M2Error('Original bone/attachment metadata changed')
    if allowed is None: allowed=[(28,8),(36,8),(160,28)]+[(h,8) for h,_,_,b in before.track_locations() if b]
    if after.array(256,36) and not before.array(256,36):allowed=allowed+[(256,8)]
    restored=bytearray(result[:len(original)])
    for start,size in allowed: restored[start:start+size]=original[start:start+size]
    if bytes(restored)!=original: raise M2Error('Original payload bytes changed outside declared header fields')
    return dict(original_prefix_bytes=len(original),original_prefix_preserved_except_relocated_header_refs_and_expanded_render_bounds=True,
                original_sequences=before.count,original_sequences_unchanged=True,original_track_descriptors_unchanged=True,
                original_lookup_assigned_entries_unchanged=True,original_lookup_prefix_unchanged=after.lookup[:len(before.lookup)]==before.lookup,
                original_geometry_collision_and_camera_bytes_unchanged=True,
                original_sha256=hashlib.sha256(original).hexdigest(),output_sha256=hashlib.sha256(result).hexdigest())
