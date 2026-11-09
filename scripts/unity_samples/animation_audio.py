"""The Animation Audio sample: a box moving through two shots, a chime across the cut.

The scene a person makes with the Shot Sequencer, the Audio Clips panel and the
Scene Exporter: a keyed box, two shots over its motion, and one sound keyed on
the timeline so that it starts in the first shot and runs past the cut,
exported with the data node on. The exporter embeds the sound in the FBX and
cuts it into one cue per clip (``audio`` v3): the first clip plays it until the
cut, the second plays it on from where it had reached. Unity's model importer
makes one clip per shot; unitytk's AnimationAudioImporter writes each cue into
its clip as PlayAudio and StopAudio events and gives the model its Animation
Audio Player. Its Edit Mode tests
(``Features/AnimationAudio/Tests/AnimationAudioSampleTests.cs``) state the same
cues.
"""

NAME = "AnimationAudio"
DESCRIPTION = (
    "A box moving through two shots with a chime that crosses the cut: each clip "
    "cues it with PlayAudio and StopAudio events, the first stopping it at the cut "
    "and the second playing it on from where it had reached, and the model's "
    "Animation Audio Player plays them; the demo scene plays the two clips in order."
)
#: The records the Animation Audio feature reads (its AnimationAudioImporter):
#: the sample is described, and held to its recipe, by these and the delivery's
#: structure (its takes among them).
RECORDS = ("audio",)
#: The exported file's stem (``AnimationAudio.fbx``).
MODEL = "AnimationAudio"
#: The scene's rate: Maya's ``film`` (24 fps).
TIME_UNIT = "film"
#: ``(name, first frame, last frame)`` per shot.
SHOTS = (("Approach", 1, 24), ("Exit", 25, 48))
#: The sound: its track (the file's stem), the frame it starts on, and its
#: length in seconds (12 frames: it ends on frame 30, six frames past the cut).
SOUND = ("chime", 18, 0.5)
#: The tone's pitch (Hz) and the file's sample rate.
TONE = (880.0, 22050)
#: ``(frame, attribute, value)``: the motion the shots cut (centimetres, degrees).
KEYS = (
    (1, "translateX", -300.0),
    (24, "translateX", 0.0),
    (25, "rotateY", 0.0),
    (48, "rotateY", 180.0),
)


def write_tone(path: str, seconds: float, pitch: float = TONE[0], rate: int = TONE[1]) -> str:
    """A mono 16-bit WAV of a sine tone at *pitch*, *seconds* long, faded out
    over its last tenth (no click at its end), with the standard library's
    ``wave``.

    Returns:
        *path*.
    """
    import math
    import struct
    import wave

    count = int(round(seconds * rate))
    fade = max(1, count // 10)
    frames = bytearray()
    for i in range(count):
        gain = min(1.0, (count - i) / fade)
        frames += struct.pack("<h", int(12000 * gain * math.sin(2 * math.pi * pitch * i / rate)))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


def build(out_dir: str) -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Returns:
        The names of the files written: ``["AnimationAudio.fbx"]`` (the sound
        rides inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import os

    import maya.cmds as cmds
    import mayatk as mtk

    cmds.currentUnit(time=TIME_UNIT)
    cmds.playbackOptions(minTime=SHOTS[0][1], maxTime=SHOTS[-1][2])
    box = cmds.polyCube(name="Box", width=100, height=100, depth=100)[0]
    for frame, attribute, value in KEYS:
        cmds.setKeyframe(box, attribute=attribute, time=frame, value=value)

    store = mtk.ShotStore()
    mtk.ShotStore.set_active(store)
    for name, start, end in SHOTS:
        store.define_shot(name, start, end, objects=[box])

    # The sound's source file, outside the delivery: the export embeds it.
    sources = os.path.join(out_dir, "_sources")
    os.makedirs(sources, exist_ok=True)
    track, frame, seconds = SOUND
    wav = write_tone(os.path.join(sources, f"{track}.wav"), seconds)
    mtk.AudioClips.load_tracks([wav])
    mtk.AudioClips.key_track(track, frame=frame, auto_end=True)

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[box],
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
