"""
generate_music.py
-----------------
Generates lo-fi music tracks.

Mode A (LOCAL): Uses audiocraft/MusicGen if GPU available.
Mode B (COLAB): Prints Colab-ready code + prompts to generate externally, then
                expects .mp3/.wav files dropped into music/ folder.
Mode C (MOCK):  Generates a silent/noise placeholder for testing visuals
                without needing a GPU.

Usage:
    python generate_music.py --mode mock       # test mode, no GPU needed
    python generate_music.py --mode local      # needs CUDA GPU + audiocraft
    python generate_music.py --mode colab      # prints Colab notebook code
"""

import os
import sys
import argparse
import subprocess
import random

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "..", "music")
os.makedirs(MUSIC_DIR, exist_ok=True)

# Abstract/trendy lo-fi prompts — not generic, these target current aesthetic niches
LOFI_PROMPTS = [
    "lofi hip hop, abstract jazz chords, glitchy vinyl crackle, muted trumpet, 78bpm, late night vibe, melancholic",
    "lofi bedroom pop, dreamy reverb guitar, cassette tape hiss, soft sub bass, 82bpm, introspective, hazy",
    "lofi future beats, ethereal pads, chopped vocal sample, dusty drums, 88bpm, weightless atmosphere",
    "lofi chill, abstract piano, rainfall ambience, warm analog bass, 75bpm, nostalgic, bittersweet",
    "lofi phonk, dark melodic piano, 808 sub, trap hi-hats slowed, 70bpm, cinematic dread, moody",
    "lofi jazz fusion, upright bass walk, brushed snare, muted rhodes, 90bpm, underground café feel",
    "lofi ambient, slow arpeggiated synth, tape echo, nature field recording, 65bpm, meditative float",
    "lofi soul, chopped female vocal, vinyl surface noise, soft kick, 85bpm, late summer haze",
    "lofi city pop, neon guitar riff, synth bass, night drive energy, 92bpm, retro futurism",
    "lofi indie, emotional acoustic guitar, soft cello, subtle percussion, 80bpm, introspective solitude",
]


def generate_mock(count=3, duration_secs=300):
    """Generate silent audio placeholders for testing."""
    print("[MUSIC] Mock mode — generating silent placeholders")
    paths = []
    import time
    ts = int(time.time())
    for i in range(count):
        out = os.path.join(MUSIC_DIR, f"track_mock_{ts}_{i:02d}.mp3")
        # Generate brown noise (sounds like ambient hum — good for visual testing)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anoisesrc=color=brown:amplitude=0.15",
            "-af", "lowpass=f=800,volume=0.3",
            "-t", str(duration_secs),
            "-c:a", "libmp3lame", "-b:a", "192k",
            out
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  Mock track: {out}")
        paths.append(out)
    return paths


def generate_local(count=5, duration_secs=300):
    """Generate with MusicGen locally. Requires GPU + audiocraft installed."""
    try:
        from audiocraft.models import MusicGen
        from audiocraft.data.audio import audio_write
    except ImportError:
        print("[ERROR] audiocraft not installed. Run: pip install audiocraft")
        print("        Or use --mode colab / --mode mock")
        sys.exit(1)

    print("[MUSIC] Local MusicGen mode")
    model = MusicGen.from_pretrained("facebook/musicgen-medium")
    model.set_generation_params(duration=duration_secs)

    prompts = random.sample(LOFI_PROMPTS, min(count, len(LOFI_PROMPTS)))
    paths = []
    import time
    ts = int(time.time())
    for i, prompt in enumerate(prompts):
        print(f"  Generating track {i+1}/{len(prompts)}: {prompt[:60]}...")
        wav = model.generate([prompt])
        out_stem = os.path.join(MUSIC_DIR, f"track_{ts}_{i:02d}")
        from audiocraft.data.audio import audio_write
        audio_write(out_stem, wav[0].cpu(), model.sample_rate, strategy="loudness")
        paths.append(out_stem + ".wav")
        print(f"  Saved: {out_stem}.wav")
    return paths


def print_colab_code(count=10, duration_secs=300):
    """Print Colab notebook code to copy-paste."""
    print("\n" + "="*60)
    print("GOOGLE COLAB CODE (free GPU — paste into a Colab cell)")
    print("="*60)
    print("""
!pip install audiocraft -q

from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write
import random

model = MusicGen.from_pretrained("facebook/musicgen-medium")
model.set_generation_params(duration=300)  # 5 min tracks

prompts = [""")
    for p in LOFI_PROMPTS[:count]:
        print(f'    "{p}",')
    print(f"""]

for i, prompt in enumerate(prompts):
    print(f"Generating {{i+1}}/{{len(prompts)}}: {{prompt[:50]}}...")
    wav = model.generate([prompt])
    audio_write(f"/content/track_{{i:02d}}", wav[0].cpu(), model.sample_rate, strategy="loudness")
    print(f"  Saved track_{{i:02d}}.wav")

print("Done! Download all .wav files from the /content/ panel on the left.")
""")
    print("="*60)
    print(f"\nAfter downloading, drop the .wav/.mp3 files into:")
    print(f"  {MUSIC_DIR}")
    print("="*60 + "\n")


def list_music_files():
    """List all music files in the music directory."""
    exts = (".mp3", ".wav", ".flac", ".ogg")
    files = [
        os.path.join(MUSIC_DIR, f)
        for f in os.listdir(MUSIC_DIR)
        if f.lower().endswith(exts)
    ]
    return sorted(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "local", "colab"], default="mock")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--duration", type=int, default=300, help="Track duration in seconds")
    args = parser.parse_args()

    if args.mode == "mock":
        generate_mock(args.count, args.duration)
    elif args.mode == "local":
        generate_local(args.count, args.duration)
    elif args.mode == "colab":
        print_colab_code(args.count, args.duration)
