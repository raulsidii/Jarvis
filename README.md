# JARVIS - Double-Clap Activated AI Assistant

Clap your hands twice and JARVIS comes to life: a random AC/DC track blasts, Jarvis greets you, Claude Code opens, and you can have a full voice conversation with Jarvis.

## What happens when you clap

1. **Random AC/DC song plays instantly** - Back in Black, Thunderstruck, Shoot to Thrill, T.N.T., Highway to Hell, or The Razors Edge
2. **Jarvis speaks over the music** - random greeting from a pool of Jarvis-style lines
3. **Claude Code launches** - opens in a new terminal with `--dangerously-skip-permissions`
4. **Conversation mode activates** - talk to Jarvis and he responds as the AI from Iron Man
5. **Say "goodbye Jarvis"** to end the conversation and go back to listening for claps

## Quick Start

```bash
# Clone
git clone https://github.com/raulsidii/Jarvis.git
cd Jarvis

# Install dependencies
pip install sounddevice numpy edge-tts pygame requests SpeechRecognition yt-dlp

# Install ffmpeg (needed for music download)
# Windows:
winget install Gyan.FFmpeg
# macOS:
brew install ffmpeg

# Download the AC/DC songs
python download_songs.py

# Run JARVIS
python jarvis.py
```

## Auto-Start on Login (Windows)

Create this file at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.bat`:
```bat
@echo off
start "JARVIS" python "C:\path\to\jarvis\jarvis.py"
```

JARVIS will start listening the moment your PC boots up.

## Songs Included

| Song | Start Time | Notes |
|------|-----------|-------|
| Back in Black | 4s | Skips the intro, straight to the riff |
| Thunderstruck | 0s | Full legendary guitar intro |
| Shoot to Thrill | 0s | Iron Man 2 / Avengers |
| T.N.T. | 0s | Pure energy |
| Highway to Hell | 0s | Classic |
| The Razors Edge | 30s | Skips to the heavy part |

A random song is picked each time you clap.

## Voice Conversation

After the welcome sequence, Jarvis enters conversation mode:
- Speak naturally and Jarvis will respond
- He uses Claude (via the CLI) as his brain
- Responses are spoken back in a British voice
- Say **"goodbye Jarvis"** to end the conversation

Requires: Claude Code CLI installed and authenticated, working microphone.

## Configuration

Edit the top of `jarvis.py`:

| Setting | Default | What it does |
|---------|---------|-------------|
| `THRESHOLD` | `0.08` | Clap sensitivity. Lower = more sensitive |
| `MUSIC_VOLUME` | `0.25` | Music volume (0.0 to 1.0) |
| `VOICE_DELAY` | `2.0` | Seconds after music before Jarvis speaks |
| `GREETINGS` | 6 variants | Pool of random Jarvis greetings |
| `EDGE_TTS_VOICE` | `en-GB-RyanNeural` | TTS voice (British male) |
| `PROJECT_DIR` | `~/jarvis` | Directory Claude Code opens in |

## Voice Upgrade

### Free (default)
Microsoft Edge neural TTS with `en-GB-RyanNeural`. No API key needed.

### Premium
Set `ELEVENLABS_API_KEY` in `jarvis.py` for [ElevenLabs](https://elevenlabs.io) voices.

## Calibrating Clap Detection

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

Clap and note the RMS values. Set `THRESHOLD` to about half your peak.

## Requirements

- Python 3.10+
- Working microphone
- ffmpeg
- [Claude Code](https://claude.ai/claude-code) CLI installed and authenticated

## License

MIT
