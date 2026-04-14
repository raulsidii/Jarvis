#!/usr/bin/env python3
"""
JARVIS - Double-clap activated AI assistant with visual UI.

Clap twice -> Music + animated Jarvis orb UI -> voice conversation.

Dependencies:
    pip install sounddevice numpy edge-tts pygame requests SpeechRecognition pyaudio flask flask-socketio anthropic

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

# ──────────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 44100
BLOCK_SIZE    = int(SAMPLE_RATE * 0.05)
THRESHOLD     = 0.08
COOLDOWN      = 0.1
DOUBLE_WINDOW = 2.0

# ElevenLabs (optional)
ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_ID = "ErXwobaYiN019PkySvjV"

# Edge-TTS
EDGE_TTS_VOICE = "en-GB-RyanNeural"

# Greetings pool
GREETINGS = [
    "Welcome home sir. All systems are online. Claude Code is ready for your command.",
    "Good to have you back sir. I've kept everything running while you were away. Shall we begin?",
    "Welcome home sir. I've taken the liberty of preparing your workspace. All systems operational.",
    "At your service sir. The digital fortress is secure and Claude Code stands ready.",
    "Welcome back sir. I must say, it's been rather quiet without you. Systems are primed and awaiting your orders.",
    "Ah, sir. Right on time as always. I've pre-loaded all systems. Ready when you are.",
]

# Music
MUSIC_VOLUME = 0.10
VOICE_DELAY  = 2.0

# Spotify
SPOTIFY_PLAYLIST = "spotify:playlist:5uYt1lgO5vVIjMTaneb540"

# Paths
PROJECT_DIR = os.path.expanduser("~")
SONGS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")
GREETING_FILE = os.path.join(tempfile.gettempdir(), "jarvis_greeting.mp3")
RESPONSE_FILE = os.path.join(tempfile.gettempdir(), "jarvis_response.mp3")

# Jarvis personality
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
#  Flask app
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'jarvis-secret'
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
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.6, "similarity_boost": 0.85},
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
        pass
    return False


def play_voice(audio_path: str):
    sound = pygame.mixer.Sound(audio_path)
    channel = sound.play()
    while channel.get_busy():
        time.sleep(0.1)


# ──────────────────────────────────────────────────────────────────────────────
#  Startup
# ──────────────────────────────────────────────────────────────────────────────
def startup_init():
    global song_files

    pygame.mixer.init(frequency=44100)

    song_files = sorted(glob.glob(os.path.join(SONGS_DIR, "*.mp3")))
    if not song_files:
        print("  [ERROR] No songs in songs/ directory. Run: python download_songs.py")
        sys.exit(1)

    print(f"  [INIT] {len(song_files)} songs loaded")
    print("  [INIT] Generating startup voice...")
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

            socketio.emit('clap_detected', {'text': f'Clap {count}/2 detected (RMS={rms:.3f})'})

            if count >= 2:
                triggered = True
                clap_times = []
                threading.Thread(target=welcome_sequence, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
#  Welcome sequence
# ──────────────────────────────────────────────────────────────────────────────
def welcome_sequence():
    global in_conversation, triggered

    socketio.emit('status', {'text': 'ACTIVATING', 'cls': 'active', 'bottom': 'INITIALIZING SEQUENCE'})

    # Pick and play random song
    song = random.choice(song_files)
    song_name = os.path.basename(song).replace("_", " ").replace(".mp3", "").title()
    socketio.emit('music', {'text': f'Now playing: {song_name}'})

    pygame.mixer.music.load(song)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play()

    time.sleep(VOICE_DELAY)

    # Speak greeting
    greeting = random.choice(GREETINGS)
    socketio.emit('jarvis_speaking', {'text': greeting})
    generate_tts(greeting, GREETING_FILE)
    play_voice(GREETING_FILE)

    # Open Claude Code
    time.sleep(0.5)
    open_claude_code()

    # Spotify after song ends (in background)
    def wait_and_spotify():
        while pygame.mixer.music.get_busy():
            time.sleep(1)
        open_spotify_playlist()
    threading.Thread(target=wait_and_spotify, daemon=True).start()

    # Enter conversation mode
    socketio.emit('listening')
    in_conversation = True
    conversation_loop()
    in_conversation = False
    triggered = False

    socketio.emit('conversation_ended')


def open_claude_code():
    socketio.emit('status', {'text': 'LAUNCHING CLAUDE CODE', 'cls': 'active', 'bottom': 'OPENING TERMINAL'})
    try:
        subprocess.Popen(
            ["wt", "new-tab", "--title", "JARVIS - Claude Code",
             "cmd", "/k",
             f"cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"],
        )
    except FileNotFoundError:
        cmd = f'start "JARVIS - Claude Code" cmd /k "cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"'
        subprocess.Popen(cmd, shell=True)


def open_spotify_playlist():
    socketio.emit('music', {'text': 'Switching to Spotify: Overdose of Rock playlist'})
    subprocess.Popen(["cmd", "/c", "start", "", SPOTIFY_PLAYLIST], shell=False)


# ──────────────────────────────────────────────────────────────────────────────
#  Conversation
# ──────────────────────────────────────────────────────────────────────────────
def conversation_loop():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    conversation_history = []
    prompt_buffer = []  # for multi-part prompts

    while True:
        socketio.emit('listening')

        user_text = listen_for_speech(recognizer)
        if user_text is None:
            continue

        lower = user_text.lower().strip()

        # Check for exit
        if any(phrase in lower for phrase in ["goodbye jarvis", "bye jarvis", "exit jarvis",
                                               "that's all jarvis", "stop jarvis", "shut down"]):
            farewell = "Very good sir. I'll be here if you need me. Just clap twice."
            socketio.emit('jarvis_speaking', {'text': farewell})
            generate_tts(farewell, RESPONSE_FILE)
            play_voice(RESPONSE_FILE)
            break

        # Check for "go go go" trigger — send buffered prompt
        if re.match(r'^go[\s,\.]*go[\s,\.]*go[\s,\.]*$', lower):
            if prompt_buffer:
                full_prompt = " ".join(prompt_buffer)
                prompt_buffer = []
                socketio.emit('user_said', {'text': full_prompt})
                socketio.emit('processing')
                response = get_jarvis_response(full_prompt, conversation_history)
                if response:
                    socketio.emit('jarvis_speaking', {'text': response})
                    conversation_history.append({"role": "user", "content": full_prompt})
                    conversation_history.append({"role": "assistant", "content": response})
                    if len(conversation_history) > 20:
                        conversation_history = conversation_history[-20:]
                    generate_tts(response, RESPONSE_FILE)
                    play_voice(RESPONSE_FILE)
            else:
                socketio.emit('jarvis_speaking', {'text': 'I don\'t have a pending command, sir. Tell me what you need, then say go go go.'})
                generate_tts("I don't have a pending command, sir. Tell me what you need, then say go go go.", RESPONSE_FILE)
                play_voice(RESPONSE_FILE)
            continue

        # Check if this is a short direct command (single sentence, no "go" needed)
        # vs a multi-part prompt that needs buffering
        word_count = len(user_text.split())

        if word_count <= 15:
            # Short command — execute immediately
            socketio.emit('user_said', {'text': user_text})
            socketio.emit('processing')

            response = get_jarvis_response(user_text, conversation_history)
            if response:
                socketio.emit('jarvis_speaking', {'text': response})
                conversation_history.append({"role": "user", "content": user_text})
                conversation_history.append({"role": "assistant", "content": response})
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]
                generate_tts(response, RESPONSE_FILE)
                play_voice(RESPONSE_FILE)
        else:
            # Longer input — buffer it, wait for "go go go"
            prompt_buffer.append(user_text)
            socketio.emit('prompt_buffered', {'text': user_text})
            socketio.emit('status', {'text': 'BUFFERING PROMPT', 'cls': 'listening',
                                     'bottom': 'SAY "GO GO GO" TO SEND'})


def listen_for_speech(recognizer: sr.Recognizer) -> str | None:
    try:
        with sr.Microphone() as source:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)
        text = recognizer.recognize_google(audio)
        return text
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return None
    except sr.RequestError as e:
        socketio.emit('status', {'text': f'SPEECH ERROR: {e}', 'cls': '', 'bottom': ''})
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
        return "Apologies sir, that took longer than expected. Do go on."
    except Exception:
        return "My systems seem to be experiencing a brief interruption, sir."


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    print()
    print("  =============================================")
    print("  J.A.R.V.I.S. - Just A Rather Very Intelligent System")
    print("  =============================================")
    print()

    startup_init()

    # Start clap detection in background
    def clap_listener():
        global triggered
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=1,
                dtype="float32",
                callback=audio_callback,
            ):
                while True:
                    time.sleep(0.1)
        except Exception as e:
            print(f"  [MIC ERROR]: {e}")

    threading.Thread(target=clap_listener, daemon=True).start()

    # Open the Jarvis UI in browser
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    print("  [SERVER] Starting Jarvis UI at http://127.0.0.1:5000")
    print("  [MIC] Listening for double clap...")
    print()

    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
