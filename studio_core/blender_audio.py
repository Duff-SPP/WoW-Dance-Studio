"""Sample-derived VSE timing; optional failures never prevent the animation save."""
import math
import wave
import tempfile
from pathlib import Path
import aud
import bpy
from .audio import select_soundtrack


def padded_copy(source, destination, samples):
    """Preserve PCM bytes; Audaspace decodes other exported audio formats."""
    try:
        with wave.open(str(source), 'rb') as reader:
            with wave.open(str(destination), 'wb') as writer:
                writer.setparams(reader.getparams())
                silence = b'\x80' if reader.getsampwidth() == 1 else b'\0'
                writer.writeframes(silence*(samples*reader.getnchannels()*reader.getsampwidth()))
                while True:
                    chunk = reader.readframes(65536)
                    if not chunk:
                        break
                    writer.writeframes(chunk)
        return
    except (wave.Error, EOFError):
        pass
    sound = aud.Sound(str(source))
    rate, channels = sound.specs
    sound.delay(samples/rate).write(str(destination), int(rate), channels, aud.FORMAT_S16,
                                    aud.CONTAINER_WAV, aud.CODEC_PCM, 0, 65536)


def add_soundtrack(scene, folder, action, enabled=True, output=None):
    result = dict(status='disabled' if not enabled else 'missing', strips=[], warnings=[])
    if not enabled:
        return result
    created = []
    original_sounds = set(bpy.data.sounds)
    settings = (scene.use_audio, scene.audio_volume, scene.sync_mode)
    try:
        files, result['warnings'] = select_soundtrack(folder, action)
        if not files:
            return result
        media = {}
        for role, path in files.items():
            try:
                sound = aud.Sound(str(path))
                rate, channels = sound.specs
                samples = sound.length
                if path.suffix.lower() == '.wav':
                    try:
                        with wave.open(str(path), 'rb') as wav:
                            samples, rate, channels = wav.getnframes(), wav.getframerate(), wav.getnchannels()
                    except (wave.Error, EOFError):
                        pass  # Blender's decoder also supports non-PCM WAVs.
                duration = samples / rate
                if rate <= 0 or samples <= 0 or not math.isfinite(duration):
                    raise ValueError('invalid duration')
                media[role] = dict(path=str(path), samples=samples, sample_rate=rate,
                                   channels=channels, duration_seconds=duration)
            except Exception as error:
                result['warnings'].append(f'{role.capitalize()} could not be read: {error}')
        if not media:
            return result
        fps = scene.render.fps / scene.render.fps_base
        start = scene.frame_start
        end = scene.frame_end + 1  # Inclusive preview range, exclusive strip end.
        editor = scene.sequence_editor_create()
        # Handle bounds overlap by <1 frame for sample-accurate transitions.
        # Separate fresh channels preserve existing strips and avoid collisions.
        channel = max((s.channel for s in editor.strips_all), default=0) + 1
        if channel + 1 > 128:
            raise ValueError('No free sequencer channels for soundtrack')
        cursor = 0.0
        plan = []
        prepared = {}
        audio_directory = None
        if 'track' in media:
            plan.append(('track', 0.0))
        if 'intro' in media:
            plan.append(('intro', cursor))
            cursor += media['intro']['duration_seconds']
        if 'loop' in media:
            duration = media['loop']['duration_seconds']
            count = max(0, math.ceil(((end-start)/fps-cursor)/duration))
            if count > 10000:
                raise ValueError('Soundtrack would require more than 10,000 loop strips')
            plan.extend(('loop', cursor+i*duration) for i in range(count))
        for index, (role, seconds) in enumerate(plan):
            exact_start = start + seconds*fps
            if exact_start >= end:
                continue
            data = media[role]
            left = math.floor(exact_start + 1e-9)
            right = min(end, math.ceil(exact_start+data['duration_seconds']*fps-1e-9))
            # Audaspace starts frame-aligned strips at the next sample. Use
            # absolute sample indices so fractional FPS cannot add a sample
            # of drift when a delay is rounded independently.
            sample_rate=data['sample_rate']
            source_sample=round(exact_start/fps*sample_rate)
            strip_sample=math.ceil(left/fps*sample_rate-1e-7)
            padding = max(0,source_sample-strip_sample)
            playback = data['path']
            if padding:
                key = (data['path'], padding)
                if key not in prepared:
                    if audio_directory is None:
                        parent = Path(output).parent/'Audio'
                        parent.mkdir(parents=True, exist_ok=True)
                        audio_directory = Path(tempfile.mkdtemp(prefix=Path(output).stem+'_',dir=parent))
                    destination = audio_directory/f'{len(prepared)+1}_{role}.wav'
                    padded_copy(data['path'], destination, padding)
                    prepared[key] = str(destination)
                playback = prepared[key]
            strip = editor.strips.new_sound(f'Studio Audio {role.title()} {index+1}',
                                            playback, channel+(index%2), left)
            created.append(strip)
            # Use sample padding instead of sound_offset: Blender 5.2's
            # delayed strip playback can skip a buffer at fractional starts.
            strip.sound_offset = 0
            strip.right_handle = max(left+1, right)
            strip.mute = False
            strip.volume = 1.0
            strip.show_waveform = True
            if strip.sound is None:
                raise ValueError('Blender did not load the sound')
            strip.sound.pack()
            if strip.sound.packed_file is None:
                raise ValueError('Sound could not be embedded')
            result['strips'].append(dict(name=strip.name, role=role, **data,
                                         start_seconds=seconds, exact_start_frame=exact_start,
                                         left_handle=strip.left_handle, right_handle=strip.right_handle,
                                         sound_offset=strip.sound_offset, channel=strip.channel,
                                         playback_path=playback, leading_silence_samples=padding,
                                         packed=True))
        scene.use_audio = True
        scene.audio_volume = 1.0
        scene.sync_mode = 'AUDIO_SYNC'
        result.update(status='included' if not result['warnings'] else 'partial',
                      fps=fps, start_frame=start, end_frame_exclusive=end,
                      timing_policy='single soundtrack plays once from animation start; trim to preview range' if 'track' in media else 'intro at animation start; loop repeats after intro; trim to preview range')
        return result
    except Exception as error:
        if scene.sequence_editor:
            for strip in created:
                scene.sequence_editor.strips.remove(strip)
        for sound in set(bpy.data.sounds)-original_sounds:
            if sound.users == 0:
                bpy.data.sounds.remove(sound)
        scene.use_audio, scene.audio_volume, scene.sync_mode = settings
        result.update(status='error', strips=[])
        result['warnings'].append('Audio skipped: '+str(error))
        return result
