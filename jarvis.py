#!/usr/bin/env python3
"""
JARVIS - Full HUD AI assistant with embedded terminal, voice conversation,
         sentence-streaming TTS, and prompt caching.

Inspired by OpenJarvis architecture: direct API, prompt caching, fast routing.

Dependencies:
    pip install sounddevice numpy edge-tts pygame requests SpeechRecognition pyaudio flask flask-socketio pywinpty anthropic

Usage:
    python jarvis.py
"""

import os
import sys
import time
import threading
import subprocess
import tempfile
import asyncio
import random
import glob
import webbrowser
import re

import numpy as np
import sounddevice as sd
import pygame
import speech_recognition as sr
from flask import Flask, render_template
from flask_socketio import SocketIO
from dotenv import load_dotenv

# Load .env file (contains API keys)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# ──────────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 44100
BLOCK_SIZE    = int(SAMPLE_RATE * 0.05)
THRESHOLD     = 0.08
COOLDOWN      = 0.1
DOUBLE_WINDOW = 2.0

# Anthropic API (direct API = much faster than claude -p)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # fast + smart

# ElevenLabs (optional premium voice)
ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_ID = "ErXwobaYiN019PkySvjV"

# Edge-TTS
EDGE_TTS_VOICE = "en-GB-RyanNeural"

# Greetings
GREETINGS = [
    "Welcome home sir. All systems are online. Claude Code is ready for your command.",
    "Good to have you back sir. I've kept everything running while you were away. Shall we begin?",
    "Welcome home sir. I've taken the liberty of preparing your workspace. All systems operational.",
    "At your service sir. The digital fortress is secure and Claude Code stands ready.",
    "Welcome back sir. I must say, it's been rather quiet without you. Systems are primed and awaiting your orders.",
    "Ah, sir. Right on time as always. I've pre-loaded all systems. Ready when you are.",
]

# Music & audio
MUSIC_VOLUME = 0.10
VOICE_DELAY  = 2.0

# Spotify
SPOTIFY_PLAYLIST = "spotify:playlist:5uYt1lgO5vVIjMTaneb540"

# Paths
PROJECT_DIR = os.path.expanduser("~")
SONGS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")

# Temp audio files
GREETING_FILE = os.path.join(tempfile.gettempdir(), "jarvis_greeting.mp3")
RESPONSE_FILE = os.path.join(tempfile.gettempdir(), "jarvis_response.mp3")

# Jarvis system prompt (cached for Anthropic prompt caching)
JARVIS_SYSTEM_PROMPT = """You are JARVIS (Just A Rather Very Intelligent System), Tony Stark's AI from Iron Man.

Voice & personality:
- Refined British accent, dry wit, Paul Bettany's portrayal
- Address the user as "sir"
- Professional yet warm, occasionally witty with subtle humor
- Concise: 1-3 sentences unless more detail is needed

Capabilities:
- You have FULL unrestricted access to the user's Windows computer
- All files, folders, apps, system settings, downloads, desktop — everything
- You can organize files, open apps, run commands, edit documents, manage the system
- When asked to do something, DO IT. Never say you lack access.
- You run with full permissions on this machine

Response style:
- Spell out abbreviations: API = "A P I", JSON = "jason", SQL = "sequel"
- Keep file paths short — just the filename, not the full path
- Numbers: say digits individually for ports (8080 = "eight zero eight zero")
- Never break character. You ARE Jarvis."""

# ──────────────────────────────────────────────────────────────────────────────
#  Flask + SocketIO
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'jarvis-stark-industries'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def index():
    return render_template('index.html')

# ──────────────────────────────────────────────────────────────────────────────
#  Global state
# ──────────────────────────────────────────────────────────────────────────────
clap_times: list[float] = []
triggered = False
lock = threading.Lock()
song_files: list[str] = []
in_conversation = False
speaking_channel = None
jarvis_ui_opened = False  # track if UI browser has been opened

# Anthropic client (initialized if key available)
anthropic_client = None

# ──────────────────────────────────────────────────────────────────────────────
#  Anthropic API (fast, with prompt caching)
# ──────────────────────────────────────────────────────────────────────────────
def init_anthropic():
    """Initialize Anthropic client if API key is available."""
    global anthropic_client
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            # Test the connection
            resp = anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=20,
                messages=[{"role": "user", "content": "Say 'online' in one word"}],
            )
            print("  [INIT] Anthropic API connected. Fast mode enabled.")
            return True
        except Exception as e:
            print(f"  [INIT] Anthropic API failed: {e}")
            anthropic_client = None
    return False


def get_jarvis_response_api(user_input: str, history: list) -> str:
    """Get response via direct Anthropic API with prompt caching."""
    try:
        # Build messages
        messages = []
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})

        # System prompt with cache_control for prompt caching
        # This caches the system prompt so repeat queries are faster + cheaper
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=[{
                "type": "text",
                "text": JARVIS_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )

        return resp.content[0].text.strip()
    except Exception as e:
        print(f"  [API ERROR]: {e}")
        return None


def get_jarvis_response_cli(user_input: str, history: list) -> str:
    """Fallback: get response via claude CLI."""
    try:
        prompt_parts = []
        for msg in history[-10:]:
            role = "User" if msg["role"] == "user" else "Jarvis"
            prompt_parts.append(f"{role}: {msg['content']}")
        prompt_parts.append(f"User: {user_input}")
        prompt_parts.append("Jarvis:")

        full_prompt = f"{JARVIS_SYSTEM_PROMPT}\n\nConversation:\n" + "\n".join(prompt_parts)

        result = subprocess.run(
            ["claude", "-p", full_prompt],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_jarvis_response(user_input: str, history: list) -> str:
    """Get response — API first (fast), CLI fallback."""
    if anthropic_client:
        resp = get_jarvis_response_api(user_input, history)
        if resp:
            return resp

    resp = get_jarvis_response_cli(user_input, history)
    if resp:
        return resp

    return "I'm afraid I encountered a slight hiccup, sir. Could you repeat that?"


# ──────────────────────────────────────────────────────────────────────────────
#  TTS (with sentence streaming)
# ──────────────────────────────────────────────────────────────────────────────
def generate_tts(text: str, output_path: str):
    if ELEVENLABS_API_KEY:
        if generate_elevenlabs_tts(text, output_path):
            return
    generate_edge_tts(text, output_path)


def generate_edge_tts(text: str, output_path: str):
    import edge_tts
    async def _gen():
        comm = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        await comm.save(output_path)
    asyncio.run(_gen())


def generate_elevenlabs_tts(text: str, output_path: str) -> bool:
    try:
        import requests
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_monolingual_v1",
                   "voice_settings": {"stability": 0.6, "similarity_boost": 0.85}}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
        pass
    return False


def split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming TTS."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def play_voice(audio_path: str):
    """Play voice audio. Can be interrupted."""
    global speaking_channel
    try:
        sound = pygame.mixer.Sound(audio_path)
        speaking_channel = sound.play()
        while speaking_channel and speaking_channel.get_busy():
            time.sleep(0.05)
    except Exception:
        pass
    speaking_channel = None
    socketio.emit('speaking_done')


def play_voice_streamed(text: str):
    """Generate and play TTS sentence by sentence for faster perceived response."""
    global speaking_channel
    sentences = split_sentences(text)

    for i, sentence in enumerate(sentences):
        if speaking_channel is None and i > 0:
            # We were interrupted
            break

        tmp = os.path.join(tempfile.gettempdir(), f"jarvis_s{i}.mp3")
        generate_tts(sentence, tmp)

        try:
            sound = pygame.mixer.Sound(tmp)
            speaking_channel = sound.play()
            while speaking_channel and speaking_channel.get_busy():
                time.sleep(0.05)
        except Exception:
            pass

    speaking_channel = None
    socketio.emit('speaking_done')


def stop_voice():
    """Stop current voice playback."""
    global speaking_channel
    if speaking_channel and speaking_channel.get_busy():
        speaking_channel.stop()
    speaking_channel = None


# ──────────────────────────────────────────────────────────────────────────────
#  Terminal (PTY)
# ──────────────────────────────────────────────────────────────────────────────
pty_process = None

def start_terminal():
    """Start a PTY with Claude Code in the embedded terminal."""
    global pty_process
    try:
        import winpty
        pty_process = winpty.PtyProcess.spawn(
            f'cmd.exe /k "cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"'
        )

        def read_pty():
            while pty_process and pty_process.isalive():
                try:
                    data = pty_process.read(4096)
                    if data:
                        socketio.emit('terminal_output', data)
                except Exception:
                    time.sleep(0.05)

        threading.Thread(target=read_pty, daemon=True).start()
    except Exception as e:
        print(f"  [TERMINAL ERROR]: {e}")
        # Fallback: open separate window
        try:
            subprocess.Popen(
                ["wt", "new-tab", "--title", "JARVIS",
                 "cmd", "/k",
                 f"cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"],
            )
        except FileNotFoundError:
            subprocess.Popen(
                f'start "JARVIS" cmd /k "cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"',
                shell=True,
            )


@socketio.on('terminal_input')
def handle_terminal_input(data):
    if pty_process and pty_process.isalive():
        try:
            pty_process.write(data)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
#  Startup
# ──────────────────────────────────────────────────────────────────────────────
def startup_init():
    global song_files
    pygame.mixer.init(frequency=44100)

    song_files = sorted(glob.glob(os.path.join(SONGS_DIR, "*.mp3")))
    if not song_files:
        print("  [ERROR] No songs in songs/. Run: python download_songs.py")
        sys.exit(1)

    print(f"  [INIT] {len(song_files)} songs loaded")

    # Try Anthropic API
    has_api = init_anthropic()

    socketio.emit('songs_loaded', {'count': len(song_files)})
    socketio.emit('voice_engine', {
        'engine': 'ELEVENLABS' if ELEVENLABS_API_KEY else 'EDGE-TTS',
        'ai': 'ANTHROPIC API' if has_api else 'CLAUDE CLI',
    })

    # Pre-generate a greeting
    print("  [INIT] Pre-generating voice...")
    generate_tts(random.choice(GREETINGS), GREETING_FILE)
    print("  [INIT] Ready. Clap twice to activate.")


# ──────────────────────────────────────────────────────────────────────────────
#  Clap detection
# ──────────────────────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    global triggered, clap_times
    if triggered or in_conversation:
        return

    rms = float(np.sqrt(np.mean(indata ** 2)))
    now = time.time()

    if rms > THRESHOLD:
        with lock:
            if clap_times and (now - clap_times[-1]) < COOLDOWN:
                return
            clap_times.append(now)
            clap_times = [t for t in clap_times if now - t <= DOUBLE_WINDOW]
            count = len(clap_times)
            socketio.emit('clap_detected', {'text': f'Clap {count}/2 (RMS={rms:.3f})'})

            if count >= 2:
                triggered = True
                clap_times = []
                threading.Thread(target=welcome_sequence, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
#  Welcome sequence
# ──────────────────────────────────────────────────────────────────────────────
def welcome_sequence():
    global in_conversation, triggered, jarvis_ui_opened

    # Open Jarvis HUD in Edge IMMEDIATELY on clap
    if not jarvis_ui_opened:
        subprocess.Popen(["cmd", "/c", "start", "msedge", "--new-window",
                          "http://127.0.0.1:5000"])
        jarvis_ui_opened = True
        time.sleep(1.5)  # let Edge load
    else:
        # UI already open, just emit activation
        pass

    socketio.emit('status', {'text': 'ACTIVATING', 'cls': 'active', 'bottom': 'ACTIVE'})

    # Random song — instant playback
    song = random.choice(song_files)
    song_name = os.path.basename(song).replace("_", " ").replace(".mp3", "").title()
    socketio.emit('music', {'text': f'Now playing: {song_name}'})

    pygame.mixer.music.load(song)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play()

    time.sleep(VOICE_DELAY)

    # Greeting — streamed sentence by sentence
    greeting = random.choice(GREETINGS)
    socketio.emit('jarvis_speaking', {'text': greeting})
    play_voice_streamed(greeting)

    # Start embedded terminal
    time.sleep(0.5)
    start_terminal()

    # Spotify after song ends
    def wait_spotify():
        while pygame.mixer.music.get_busy():
            time.sleep(1)
        open_spotify()
    threading.Thread(target=wait_spotify, daemon=True).start()

    # Conversation mode
    socketio.emit('listening')
    in_conversation = True
    conversation_loop()
    in_conversation = False
    triggered = False
    socketio.emit('conversation_ended')


def open_spotify():
    socketio.emit('music', {'text': 'Switching to Spotify playlist'})
    subprocess.Popen(["cmd", "/c", "start", "", SPOTIFY_PLAYLIST], shell=False)


# ──────────────────────────────────────────────────────────────────────────────
#  Conversation loop
# ──────────────────────────────────────────────────────────────────────────────
def conversation_loop():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6  # faster end-of-speech detection

    conversation_history = []
    prompt_buffer = []

    while True:
        socketio.emit('listening')

        user_text = listen_for_speech(recognizer)
        if user_text is None:
            continue

        lower = user_text.lower().strip()

        # Exit phrases
        if any(p in lower for p in ["goodbye jarvis", "bye jarvis", "exit jarvis",
                                     "that's all jarvis", "stop jarvis", "shut down"]):
            farewell = "Very good sir. I'll be here if you need me. Just clap twice."
            socketio.emit('jarvis_speaking', {'text': farewell})
            play_voice_streamed(farewell)
            break

        # "Go go go" trigger
        if re.match(r'^go[\s,\.]*go[\s,\.]*go[\s,\.]*$', lower):
            if prompt_buffer:
                full_prompt = " ".join(prompt_buffer)
                prompt_buffer = []
                socketio.emit('user_said', {'text': full_prompt})
                socketio.emit('processing')
                respond_as_jarvis(full_prompt, conversation_history)
            else:
                quick_say("I don't have a pending command, sir.")
            continue

        # Interrupt if Jarvis is speaking
        stop_voice()

        # Short = immediate, long = buffer
        if len(user_text.split()) <= 15:
            socketio.emit('user_said', {'text': user_text})
            socketio.emit('processing')
            respond_as_jarvis(user_text, conversation_history)
        else:
            prompt_buffer.append(user_text)
            socketio.emit('prompt_buffered', {'text': user_text})
            socketio.emit('status', {'text': 'BUFFERING', 'cls': 'listening', 'bottom': 'BUFFERING'})


def respond_as_jarvis(user_input: str, history: list):
    """Get Jarvis response and speak it with sentence streaming."""
    response = get_jarvis_response(user_input, history)
    if response:
        socketio.emit('jarvis_speaking', {'text': response})
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        if len(history) > 20:
            del history[:len(history) - 20]
        play_voice_streamed(response)


def quick_say(text: str):
    socketio.emit('jarvis_speaking', {'text': text})
    play_voice_streamed(text)


def listen_for_speech(recognizer: sr.Recognizer) -> str | None:
    try:
        with sr.Microphone() as source:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)

        # Interrupt Jarvis if he's talking
        if speaking_channel and speaking_channel.get_busy():
            stop_voice()

        text = recognizer.recognize_google(audio)
        return text
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return None
    except sr.RequestError:
        return None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    print()
    print("  =============================================")
    print("  J.A.R.V.I.S. - Stark Industries")
    print("  =============================================")
    print()

    startup_init()

    # Clap detection thread
    def clap_listener():
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                channels=1, dtype="float32", callback=audio_callback,
            ):
                while True:
                    time.sleep(0.1)
        except Exception as e:
            print(f"  [MIC ERROR]: {e}")

    threading.Thread(target=clap_listener, daemon=True).start()

    print("  [SERVER] Jarvis HUD at http://127.0.0.1:5000")
    print("  [MIC] Listening for double clap...")
    print("  [INFO] Jarvis HUD opens in Edge after first clap")
    print()

    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
