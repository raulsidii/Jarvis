# JARVIS - Build Guide

## What is this?

JARVIS is a double-clap activated AI assistant. Clap twice and:
1. A random AC/DC song plays instantly (pre-loaded in memory)
2. Jarvis speaks a random greeting over the music
3. Claude Code opens with `--dangerously-skip-permissions`
4. Voice conversation mode activates — talk to Jarvis and he responds

## Architecture

```
Startup:
  1. pygame.mixer initializes
  2. All songs from songs/ are discovered
  3. A greeting is pre-generated via edge-tts
  4. Microphone input stream opens via sounddevice

Clap detection:
  1. Audio callback computes RMS of each 50ms block
  2. If RMS > THRESHOLD, count as a clap
  3. If 2 claps within DOUBLE_WINDOW seconds -> trigger

Welcome sequence:
  1. Random song loaded and plays instantly
  2. Wait VOICE_DELAY seconds
  3. Random greeting generated + played over music
  4. Claude Code launched in Windows Terminal
  5. Enter conversation mode

Conversation mode:
  1. SpeechRecognition listens via microphone
  2. Google Speech API transcribes to text
  3. Text sent to claude CLI (-p flag, print mode)
  4. Response generated with Jarvis system prompt
  5. edge-tts converts response to speech
  6. pygame plays the response audio
  7. Loop until "goodbye Jarvis"
```

## Key dependencies

| Package | Purpose |
|---------|---------|
| `sounddevice` | Microphone input for clap detection |
| `numpy` | RMS calculation on audio blocks |
| `edge-tts` | Free TTS (Microsoft Edge neural voices) |
| `pygame` | Audio playback with mixing (music + voice) |
| `SpeechRecognition` | Voice input transcription |
| `requests` | ElevenLabs API calls (optional) |
| `yt-dlp` | Download songs from YouTube (setup only) |

## Setup from scratch

```bash
git clone https://github.com/raulsidii/Jarvis.git
cd Jarvis
pip install sounddevice numpy edge-tts pygame requests SpeechRecognition yt-dlp
winget install Gyan.FFmpeg   # Windows
python download_songs.py
python jarvis.py
```

## Adding custom songs

Edit `download_songs.py` — the `SONGS` list contains tuples of:
```python
("YouTube search query", "output_filename.mp3", start_seconds_or_None)
```

Add entries and re-run `python download_songs.py`.

## Configuration

All config is at the top of `jarvis.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `THRESHOLD` | `0.08` | Clap sensitivity |
| `COOLDOWN` | `0.1` | Debounce between claps |
| `DOUBLE_WINDOW` | `2.0` | Max gap between claps |
| `MUSIC_VOLUME` | `0.25` | Song volume (0.0-1.0) |
| `VOICE_DELAY` | `2.0` | Pause before Jarvis speaks |
| `EDGE_TTS_VOICE` | `en-GB-RyanNeural` | TTS voice |
| `GREETINGS` | list of 6 | Random greeting pool |
| `PROJECT_DIR` | `~/jarvis` | Claude Code working dir |
| `ELEVENLABS_API_KEY` | `""` | Optional premium voice |

## Auto-start on Windows

File at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.bat`:
```bat
@echo off
start "JARVIS" python "C:\path\to\jarvis\jarvis.py"
```

## Troubleshooting

- **Claps not detected**: Lower `THRESHOLD` (try 0.05)
- **False triggers**: Raise `THRESHOLD` (try 0.15)
- **No songs**: Run `python download_songs.py`
- **Conversation not working**: Ensure `claude` CLI is on PATH and authenticated
- **TTS errors**: Check internet connection (edge-tts needs it)
- **Microphone issues**: Check Windows sound settings
