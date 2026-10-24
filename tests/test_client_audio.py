import array,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
from studio_core import client_audio
from studio_core.catalog import ROOT,digest

class ClientAudioTests(unittest.TestCase):
    def test_intro_then_loop_repeated_and_cropped_to_animation_cycle(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Reports') as folder:
            root=Path(folder);parts={};inputs=root/'Input/Fortnite';inputs.mkdir(parents=True)
            for role,value in (('intro',1000),('loop',2000)):
                path=inputs/(role+'.wav')
                with wave.open(str(path),'wb') as w:
                    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(array.array('h',[value]*2205).tobytes())
                parts[role]=dict(source=str(path),sha256=digest(path))
            with patch.object(client_audio,'ROOT',root),patch('studio_core.fortnite_paths.INPUT',inputs):
                result=client_audio.render_cycle(dict(duration_ms=350,parts=parts),root/'cycle.wav')
            with wave.open(str(root/'cycle.wav'),'rb') as reader:
                self.assertEqual(reader.getframerate(),44100);self.assertEqual(reader.getnchannels(),2)
                samples=array.array('h',reader.readframes(reader.getnframes()))
            self.assertEqual(result['samples'],15435)
            self.assertEqual(samples[0],1000);self.assertEqual(samples[8820],2000);self.assertEqual(samples[-1],2000)

    def test_clip_duration_uses_actual_frame_range(self):
        self.assertEqual(client_audio.duration_ms(dict(validation=dict(frames=[10,70],fps=30))),2000)
        with self.assertRaises(ValueError):client_audio.duration_ms(dict(validation=dict(frames=[0,10],fps=0)))

    def test_complete_source_is_not_cropped_to_short_animation(self):
        (ROOT/'Output/FortniteImports').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'Output/FortniteImports') as folder:
            path=Path(folder)/'song.wav'
            with wave.open(str(path),'wb') as writer:
                writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(22050)
                writer.writeframes(array.array('h',[321]*44100).tobytes())
            result=client_audio.render_full(dict(source=str(path),sha256=digest(path)),Path(folder)/'full.wav')
            self.assertEqual(result['duration_ms'],2000);self.assertEqual(result['samples'],88200)
        version=dict(validation=dict(frames=[0,293],fps=30.102390229752725),imported={'num_frames':294})
        self.assertEqual(client_audio.duration_ms(version),9767)

if __name__=='__main__':unittest.main()
