# JARVIS - Build Guide

This file helps Claude Code (or any developer) recreate and understand this project.

## What is this?

JARVIS is a double-clap activated AI assistant launcher. Clap your hands twice and:
1. Music plays instantly (pre-loaded in memory, zero delay)
2. A Jarvis-style AI voice greets you over the music
3. Claude Code opens in a new terminal with `--dangerously-skip-permissions`

## Architecture

Single Python script (`jarvis.py`) with this flow:

```
Startup:
  1. pygame.mixer initializes
  2. music.mp3 is loaded into memory
  3. Greeting audio is generated via edge-tts (or ElevenLabs) and loaded as a Sound object
  4. Microphone input stream opens via sounddevice

Runtime loop:
  1. Audio callback computes RMS of each 50ms block
  2. If RMS > THRESHOLD, count as a clap
  3. If 2 claps within DOUBLE_WINDOW seconds -> trigger welcome sequence
  4. Welcome sequence: play music -> wait VOICE_DELAY -> play voice over music -> launch Claude Code
  5. After sequence completes, reload music and resume listening
```

## Key dependencies

| Package | Purpose |
|---------|---------|
| `sounddevice` | Microphone input for clap detection |
| `numpy` | RMS calculation on audio blocks |
| `edge-tts` | Free high-quality TTS (Microsoft Edge neural voices) |
| `pygame` | Audio playback with mixing (music + voice simultaneously) |
| `requests` | ElevenLabs API calls (optional) |
| `yt-dlp` | Download music from YouTube (setup only) |

## Setup from scratch

### Prerequisites
- Python 3.10+
- A working microphone
- ffmpeg installed (`winget install Gyan.FFmpeg` on Windows)
- Claude Code CLI installed and on PATH

### Install steps

```bash
# Clone
git clone https://github.com/RafaTatay/jarvis.git
cd jarvis

# Install Python deps
pip install sounddevice numpy edge-tts pygame requests yt-dlp

# Download your music (pick any YouTube URL)
python download_music.py "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# Run
python jarvis.py
```

### Auto-start on Windows login

Create a file at:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.bat`

With contents:
```bat
@echo off
start "JARVIS" python "C:\path\to\jarvis\jarvis.py"
```

## Configuration (top of jarvis.py)

| Variable | Default | Description |
|----------|---------|-------------|
| `THRESHOLD` | `0.08` | Clap sensitivity. Raise if false triggers, lower if claps aren't detected |
| `COOLDOWN` | `0.1` | Min seconds between claps (debounce) |
| `DOUBLE_WINDOW` | `2.0` | Max seconds between first and second clap |
| `MUSIC_VOLUME` | `0.25` | Music volume (0.0-1.0) |
| `VOICE_DELAY` | `2.0` | Seconds after music starts before voice plays |
| `EDGE_TTS_VOICE` | `en-GB-RyanNeural` | TTS voice. British male sounds most Jarvis-like |
| `GREETING` | `"Welcome home sir..."` | What Jarvis says |
| `PROJECT_DIR` | `~/jarvis` | Directory Claude Code opens in |
| `ELEVENLABS_API_KEY` | `""` | Optional. Set for premium voice quality |

## Voice upgrade path

### Edge-TTS (default, free)
Works out of the box. `en-GB-RyanNeural` is a solid British male voice.

### ElevenLabs (premium)
1. Get an API key at https://elevenlabs.io
2. Set `ELEVENLABS_API_KEY` in jarvis.py
3. Optionally change `ELEVENLABS_VOICE_ID` to your preferred voice

### RVC Voice Conversion (advanced)
For the actual Paul Bettany / JARVIS voice:
1. Requires Python 3.10-3.11 (RVC packages don't support 3.12+)
2. Install `rvc-python` package
3. Download a JARVIS RVC model from HuggingFace (search "JARVIS RVC")
4. Pipe edge-tts output through RVC before playback

## Troubleshooting

- **Claps not detected**: Lower `THRESHOLD` (try 0.05). Run calibration:
  ```python
  python -c "
  import numpy as np, sounddevice as sd, time
  def cb(indata, frames, t, s):
      rms = float(np.sqrt(np.mean(indata**2)))
      if rms > 0.01: print(f'RMS={rms:.4f}  {\"#\"*int(rms*200)}')
  with sd.InputStream(samplerate=44100, blocksize=2205, channels=1, dtype='float32', callback=cb):
      time.sleep(10)
  "
  ```
- **False triggers from noise**: Raise `THRESHOLD` (try 0.15-0.20)
- **Music not found**: Run `python download_music.py <url>` first
- **No sound output**: Check Windows sound settings, make sure speakers/headphones are default device
- **Claude Code not found**: Ensure `claude` is on your PATH (`where claude`)
