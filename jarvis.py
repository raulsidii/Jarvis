#!/usr/bin/env python3
"""
JARVIS - Full HUD AI assistant with embedded terminal and voice conversation.

Dependencies:
    pip install sounddevice numpy edge-tts pygame requests SpeechRecognition pyaudio flask flask-socketio pywinpty

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
import struct

import numpy as np
import sounddevice as sd
import pygame
import speech_recognition as sr
from flask import Flask, render_template
from flask_socketio import SocketIO
import winpty

# ──────────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 44100
BLOCK_SIZE    = int(SAMPLE_RATE * 0.05)
THRESHOLD     = 0.08
COOLDOWN      = 0.1
DOUBLE_WINDOW = 2.0

ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_ID = "ErXwobaYiN019PkySvjV"
EDGE_TTS_VOICE = "en-GB-RyanNeural"

GREETINGS = [
    "Welcome home sir. All systems are online. Claude Code is ready for your command.",
    "Good to have you back sir. I've kept everything running while you were away. Shall we begin?",
    "Welcome home sir. I've taken the liberty of preparing your workspace. All systems operational.",
    "At your service sir. The digital fortress is secure and Claude Code stands ready.",
    "Welcome back sir. I must say, it's been rather quiet without you. Systems are primed and awaiting your orders.",
    "Ah, sir. Right on time as always. I've pre-loaded all systems. Ready when you are.",
]

MUSIC_VOLUME = 0.10
VOICE_DELAY  = 2.0
SPOTIFY_PLAYLIST = "spotify:playlist:5uYt1lgO5vVIjMTaneb540"

PROJECT_DIR = os.path.expanduser("~")
SONGS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")
GREETING_FILE = os.path.join(tempfile.gettempdir(), "jarvis_greeting.mp3")
RESPONSE_FILE = os.path.join(tempfile.gettempdir(), "jarvis_response.mp3")

JARVIS_SYSTEM_PROMPT = """You are JARVIS (Just A Rather Very Intelligent System), the AI assistant from Iron Man.
You speak with a refined British accent and dry wit, similar to Paul Bettany's portrayal.
You address the user as "sir" and maintain a professional yet warm demeanor.
You are helpful, intelligent, and occasionally witty with subtle humor.
Keep responses concise - 1-3 sentences unless the question requires more detail.
You have FULL access to the user's Windows computer - all files, folders, applications, and system settings.
You can organize files, open apps, manage downloads, edit documents, run commands, and do anything on the system.
When asked to do something on the computer, DO IT. Do not say you lack access. You are running with full permissions.
Never break character. You ARE Jarvis."""

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
speaking_channel = None  # track current voice playback for interruption

# ──────────────────────────────────────────────────────────────────────────────
#  Terminal (PTY)
# ──────────────────────────────────────────────────────────────────────────────
pty_process = None

def start_terminal():
    """Start a PTY process with Claude Code."""
    global pty_process
    try:
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
        # Fallback: just open a regular terminal window
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
    global pty_process
    if pty_process and pty_process.isalive():
        try:
            pty_process.write(data)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
#  TTS
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


def play_voice(audio_path: str):
    """Play voice audio. Can be interrupted by calling stop_voice()."""
    global speaking_channel
    sound = pygame.mixer.Sound(audio_path)
    speaking_channel = sound.play()
    while speaking_channel and speaking_channel.get_busy():
        time.sleep(0.05)
    speaking_channel = None
    socketio.emit('speaking_done')


def stop_voice():
    """Stop current voice playback (for interruption)."""
    global speaking_channel
    if speaking_channel and speaking_channel.get_busy():
        speaking_channel.stop()
        speaking_channel = None


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
    socketio.emit('songs_loaded', {'count': len(song_files)})
    socketio.emit('voice_engine', {'engine': 'ELEVENLABS' if ELEVENLABS_API_KEY else 'EDGE-TTS'})

    print("  [INIT] Pre-generating voice...")
    generate_tts(random.choice(GREETINGS), GREETING_FILE)
    print("  [INIT] Ready.")


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
    global in_conversation, triggered

    socketio.emit('status', {'text': 'ACTIVATING', 'cls': 'active', 'bottom': 'ACTIVE'})

    # Random song
    song = random.choice(song_files)
    song_name = os.path.basename(song).replace("_", " ").replace(".mp3", "").title()
    socketio.emit('music', {'text': f'Now playing: {song_name}'})

    pygame.mixer.music.load(song)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play()

    time.sleep(VOICE_DELAY)

    # Greeting
    greeting = random.choice(GREETINGS)
    socketio.emit('jarvis_speaking', {'text': greeting})
    generate_tts(greeting, GREETING_FILE)
    play_voice(GREETING_FILE)

    # Start terminal with Claude Code
    time.sleep(0.5)
    start_terminal()

    # Spotify after song
    def wait_spotify():
        while pygame.mixer.music.get_busy():
            time.sleep(1)
        open_spotify()
    threading.Thread(target=wait_spotify, daemon=True).start()

    # Conversation
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
#  Conversation
# ──────────────────────────────────────────────────────────────────────────────
def conversation_loop():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8  # faster end-of-speech detection

    conversation_history = []
    prompt_buffer = []

    while True:
        socketio.emit('listening')

        user_text = listen_for_speech(recognizer)
        if user_text is None:
            continue

        lower = user_text.lower().strip()

        # Exit
        if any(p in lower for p in ["goodbye jarvis", "bye jarvis", "exit jarvis",
                                     "that's all jarvis", "stop jarvis", "shut down"]):
            farewell = "Very good sir. I'll be here if you need me. Just clap twice."
            socketio.emit('jarvis_speaking', {'text': farewell})
            generate_tts(farewell, RESPONSE_FILE)
            play_voice(RESPONSE_FILE)
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
                quick_say("I don't have a pending command, sir. Tell me what you need, then say go go go.")
            continue

        # Short = immediate, long = buffer
        if len(user_text.split()) <= 15:
            # Interrupt current speech if Jarvis is talking
            stop_voice()
            socketio.emit('user_said', {'text': user_text})
            socketio.emit('processing')
            respond_as_jarvis(user_text, conversation_history)
        else:
            prompt_buffer.append(user_text)
            socketio.emit('prompt_buffered', {'text': user_text})
            socketio.emit('status', {'text': 'BUFFERING', 'cls': 'listening', 'bottom': 'BUFFERING'})


def respond_as_jarvis(user_input: str, history: list):
    """Get response from Claude and speak it."""
    response = get_jarvis_response(user_input, history)
    if response:
        socketio.emit('jarvis_speaking', {'text': response})
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        if len(history) > 20:
            del history[:len(history) - 20]
        generate_tts(response, RESPONSE_FILE)
        play_voice(RESPONSE_FILE)


def quick_say(text: str):
    """Quick TTS for short system messages."""
    socketio.emit('jarvis_speaking', {'text': text})
    generate_tts(text, RESPONSE_FILE)
    play_voice(RESPONSE_FILE)


def listen_for_speech(recognizer: sr.Recognizer) -> str | None:
    try:
        with sr.Microphone() as source:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)

        # If Jarvis is currently speaking, this is an interruption
        if speaking_channel and speaking_channel.get_busy():
            stop_voice()
            socketio.emit('status', {'text': 'INTERRUPTED', 'cls': '', 'bottom': 'INTERRUPTED'})

        text = recognizer.recognize_google(audio)
        return text
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return None
    except sr.RequestError as e:
        socketio.emit('status', {'text': f'SPEECH ERROR', 'cls': '', 'bottom': 'ERROR'})
        return None
    except Exception:
        return None


def get_jarvis_response(user_input: str, history: list) -> str | None:
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
        return "I'm afraid I encountered a slight hiccup, sir. Could you repeat that?"
    except subprocess.TimeoutExpired:
        return "Apologies sir, that took longer than expected."
    except Exception:
        return "My systems are experiencing a brief interruption, sir."


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

    # Open browser
    def open_browser():
        time.sleep(2)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    print("  [SERVER] Jarvis HUD at http://127.0.0.1:5000")
    print("  [MIC] Listening for double clap...")
    print()

    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
