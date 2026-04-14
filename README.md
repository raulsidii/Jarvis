# JARVIS - Double-Clap Activated AI Assistant

Clap your hands twice and JARVIS comes to life: music plays instantly, a Jarvis-style voice greets you, and Claude Code opens ready to work.

https://github.com/user-attachments/assets/demo.mp4

## What happens when you clap

1. **Music plays instantly** - pre-loaded in memory, zero delay
2. **Jarvis speaks over the music** - "Welcome home sir. All systems are online."
3. **Claude Code launches** - opens in a new terminal with `--dangerously-skip-permissions`
4. **Starts listening again** - clap twice anytime to re-trigger

## Quick Start

```bash
# Clone
git clone https://github.com/RafaTatay/jarvis.git
cd jarvis

# Install dependencies
pip install sounddevice numpy edge-tts pygame requests yt-dlp

# Install ffmpeg (needed for music download)
# Windows:
winget install Gyan.FFmpeg
# macOS:
brew install ffmpeg

# Download your music (pick any song)
python download_music.py "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# Run JARVIS
python jarvis.py
```

## Auto-Start on Login (Windows)

Want JARVIS listening the moment your PC boots? Create this file:

**`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.bat`**
```bat
@echo off
start "JARVIS" python "C:\path\to\jarvis\jarvis.py"
```

## Configuration

Edit the top of `jarvis.py`:

| Setting | Default | What it does |
|---------|---------|-------------|
| `THRESHOLD` | `0.08` | Clap sensitivity. Lower = more sensitive |
| `MUSIC_VOLUME` | `0.25` | Music volume (0.0 to 1.0) |
| `VOICE_DELAY` | `2.0` | Seconds after music before Jarvis speaks |
| `GREETING` | `"Welcome home sir..."` | What Jarvis says |
| `EDGE_TTS_VOICE` | `en-GB-RyanNeural` | TTS voice (British male) |
| `PROJECT_DIR` | `~/jarvis` | Directory Claude Code opens in |

## Voice Options

### Free (default)
Uses Microsoft Edge neural TTS - `en-GB-RyanNeural` (British male). Works out of the box, no API key needed.

### Premium
Set `ELEVENLABS_API_KEY` in `jarvis.py` for higher quality voices via [ElevenLabs](https://elevenlabs.io).

## Calibrating Clap Detection

If claps aren't being detected (or there are false triggers), run the calibration test:

```bash
python -c "
import numpy as np, sounddevice as sd, time
def cb(indata, frames, t, s):
    rms = float(np.sqrt(np.mean(indata**2)))
    if rms > 0.01: print(f'RMS={rms:.4f}')
with sd.InputStream(samplerate=44100, blocksize=2205, channels=1, dtype='float32', callback=cb):
    time.sleep(10)
"
```

Clap a few times and note the RMS values. Set `THRESHOLD` to about half of your clap's peak RMS.

## Requirements

- Python 3.10+
- Working microphone
- ffmpeg (for music download)
- [Claude Code](https://claude.ai/claude-code) CLI installed

## License

MIT
