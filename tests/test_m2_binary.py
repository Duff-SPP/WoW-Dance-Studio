import copy,struct,unittest
from studio_core.m2_binary import Model,M2Error,PAIR,SEQUENCE,append,export_model,verify_preservation,compressed_quat


def fixture(external=False):
    data=bytearray(304); data[:4]=b'MD20'; struct.pack_into('<I',data,4,264)
    sequence=SEQUENCE.pack(0,0,1000,0.,0 if external else 0x20,32767,0,0,0,0,0,-1.,-1.,-1.,1.,1.,1.,2.,-1,0)
    PAIR.pack_into(data,28,1,append(data,sequence)); PAIR.pack_into(data,36,1,append(data,struct.pack('<h',0)))
    bone=bytearray(88); struct.pack_into('<iIhHI',bone,0,-1,512,-1,0,123)
    for local in (16,36,56):
        outer=append(data,PAIR.pack(1,0x12345678) if external else PAIR.pack(0,0))
        struct.pack_into('<HHIIII',bone,local,1,65535,1,outer,1,outer)
    PAIR.pack_into(data,44,1,append(data,bone)); struct.pack_into('<7f',data,160,-1,-1,-1,1,1,1,2)
    return bytes(data)


def clip():
    return dict(animation_id=1792,duration=1000,times=[0,1000],bounds=[-1,-1,-1,2,2,2,4],
                bones=[[[[0,0,0],[1,0,0]],[[0,0,0,1]],[[1,1,1]]]])


class AppendM2Tests(unittest.TestCase):
    def test_loop_clamp_and_native_blend_settings_preserve_external_storage(self):
        data=bytearray(fixture());_,offset=PAIR.unpack_from(data,28)
        struct.pack_into('<H',data,offset,69);struct.pack_into('<I',data,offset+12,0x80)
        struct.pack_into('<H',data,offset+28,150)
        result,_,_=export_model(bytes(data),[clip()]);native=Model(result)
        self.assertEqual(struct.unpack_from('<I',native.sequences,64+12)[0],0x80)
        self.assertEqual(struct.unpack_from('<H',native.sequences,64+28)[0],150)
        once=clip();once['loop']=False
        result,_,_=export_model(bytes(data),[once]);self.assertEqual(struct.unpack_from('<I',Model(result).sequences,64+12)[0],0x81)
    def test_hundred_dance_batch_and_unused_lookup_slots(self):
        data=bytearray(fixture())
        lookup=[0]+[-1]*2000
        PAIR.pack_into(data,36,len(lookup),append(data,struct.pack('<'+'h'*len(lookup),*lookup)))
        clips=[]
        for i in range(100):
            value=clip(); value['animation_id']=1792+i; clips.append(value)
        result,anims,check=export_model(bytes(data),clips)
        self.assertEqual(len(anims),100); self.assertEqual(Model(result).count,101)
        self.assertTrue(check['original_lookup_assigned_entries_unchanged'])
        self.assertFalse(check['original_lookup_prefix_unchanged'])
        self.assertEqual(Model(result).lookup[1891],100)
        for index in range(1,101): self.assertEqual(Model(result).validate_load_ring(index),[index])

    def test_native_loader_ring_must_return_to_requested_sequence(self):
        original=fixture();result,_,_=export_model(original,[clip()])
        native=Model(result)
        self.assertEqual(native.validate_load_ring(1),[1])
        # Exact live hang: sequence 1 -> sequence 0 -> sequence 0 forever.
        broken=bytearray(result);_,pointer=PAIR.unpack_from(broken,28)
        struct.pack_into('<H',broken,pointer+64+62,0)
        with self.assertRaisesRegex(M2Error,'never returns'):
            verify_preservation(original,bytes(broken))
        struct.pack_into('<H',broken,pointer+64+62,65535)
        with self.assertRaisesRegex(M2Error,'outside sequence table'):
            Model(broken).validate_load_ring(1)

    def test_sound_event_isolated_to_new_animation_external_timestamps(self):
        value=clip();value['sound_id']=123456
        original=fixture();result,anims,_=export_model(original,[value])
        model=Model(result);events=model.array(256,36)
        self.assertEqual(len(events),36)
        self.assertEqual(events[:4],b'$CSD')
        self.assertEqual(struct.unpack_from('<I',events,4)[0],123456)
        _,global_sequence,pairs=model.descriptors(events,24,True)
        self.assertEqual(global_sequence,65535)
        self.assertEqual(pairs[0][0],(0,0),'No soundtrack on original animation')
        count,offset=pairs[0][1];self.assertEqual(count,1)
        self.assertEqual(struct.unpack_from('<I',anims[1792],offset)[0],1)
        self.assertTrue(verify_preservation(original,result)['original_sequences_unchanged'])

    def test_original_payload_lookup_and_external_descriptors_preserved(self):
        for external in (False,True):
            original=fixture(external); result,anims,checks=export_model(original,[clip()])
            self.assertTrue(checks['original_sequences_unchanged']); self.assertTrue(anims[1792])
            self.assertEqual(Model(result).lookup[1792],1)
            self.assertEqual(Model(result).sequences[:64],Model(original).sequences)
            self.assertTrue(verify_preservation(original,result)['original_track_descriptors_unchanged'])

    def test_batch_and_variation_collision(self):
        second=clip(); second['animation_id']=1793
        result,anims,_=export_model(fixture(),[clip(),second])
        self.assertEqual(Model(result).count,3); self.assertEqual(set(anims),{1792,1793})
        for bad in (0,65535,1792):
            second['animation_id']=bad
            with self.assertRaises(M2Error): export_model(fixture(),[clip(),second])

    def test_corrupt_originals_rejected(self):
        for data in (b'',b'MD21'+fixture()[4:],fixture()[:200]):
            with self.assertRaises(M2Error): Model(data)
        data=bytearray(fixture()); PAIR.pack_into(data,264,1,0)
        with self.assertRaisesRegex(M2Error,'lights'): Model(data)

    def test_invalid_keys_and_codec(self):
        for times in ([0,0],[0,999],[-1,1000]):
            value=clip(); value['times']=times
            with self.assertRaises(M2Error): export_model(fixture(),[value])
        with self.assertRaises(M2Error): compressed_quat([0,0,0,2])
        raw=struct.unpack('<4h',compressed_quat([0,0,0,1]))
        decoded=[((v+32768) if v<0 else (v-32767))/32767 for v in raw]
        self.assertEqual(decoded,[0,0,0,1])

    def test_global_channels_and_original_mutation_blocked(self):
        data=bytearray(fixture()); _,offset=PAIR.unpack_from(data,44); struct.pack_into('<H',data,offset+18,0)
        PAIR.pack_into(data,20,1,0)
        with self.assertRaisesRegex(M2Error,'global-sequence'): export_model(bytes(data),[clip()])
        original=fixture(); result,_,_=export_model(original,[clip()]); bad=bytearray(result); bad[300]^=1
        with self.assertRaises(M2Error): verify_preservation(original,bytes(bad))

if __name__=='__main__': unittest.main()
