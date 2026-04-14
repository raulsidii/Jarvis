#!/usr/bin/env python3
"""
JARVIS - Double-clap activated AI assistant with voice conversation.

Clap twice -> Random AC/DC song plays -> Jarvis speaks -> Claude Code opens.
Then enter conversation mode: talk to Jarvis and he responds.

Dependencies:
    pip install sounddevice numpy edge-tts pygame requests SpeechRecognition anthropic

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

import numpy as np
import sounddevice as sd
import pygame
import speech_recognition as sr

# ──────────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 44100
BLOCK_SIZE    = int(SAMPLE_RATE * 0.05)   # 50 ms per block
THRESHOLD     = 0.08     # minimum RMS to count as a clap — adjust if needed
COOLDOWN      = 0.1      # minimum seconds between claps
DOUBLE_WINDOW = 2.0      # time window for the second clap

# ElevenLabs config (leave API key empty to use edge-tts)
ELEVENLABS_API_KEY = ""   # Paste your key here, e.g. "sk_..."
ELEVENLABS_VOICE_ID = "ErXwobaYiN019PkySvjV"  # "Antoni" - deep, British

# Edge-TTS voice (used when ElevenLabs key is empty)
EDGE_TTS_VOICE = "en-GB-RyanNeural"  # British male — closest to Jarvis

# Jarvis greetings — one is chosen randomly each time
GREETINGS = [
    "Welcome home sir. All systems are online. Claude Code is ready for your command.",
    "Good to have you back sir. I've kept everything running while you were away. Shall we begin?",
    "Welcome home sir. I've taken the liberty of preparing your workspace. All systems operational.",
    "At your service sir. The digital fortress is secure and Claude Code stands ready.",
    "Welcome back sir. I must say, it's been rather quiet without you. Systems are primed and awaiting your orders.",
    "Ah, sir. Right on time as always. I've pre-loaded all systems. Ready when you are.",
]

# Music settings
MUSIC_VOLUME = 0.25  # 0.0 to 1.0
VOICE_DELAY  = 2.0   # seconds after music starts before Jarvis speaks

# Where Claude Code opens
PROJECT_DIR = os.path.expanduser("~/jarvis")

# Songs directory
SONGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")

# Conversation mode
JARVIS_SYSTEM_PROMPT = """You are JARVIS (Just A Rather Very Intelligent System), the AI assistant from Iron Man.
You speak with a refined British accent and dry wit, similar to Paul Bettany's portrayal.
You address the user as "sir" and maintain a professional yet warm demeanor.
You are helpful, intelligent, and occasionally witty with subtle humor.
Keep responses concise — 1-3 sentences unless the question requires more detail.
You have access to all of the user's systems and can help with any task.
Never break character. You ARE Jarvis."""

# ──────────────────────────────────────────────────────────────────────────────
#  File paths
# ──────────────────────────────────────────────────────────────────────────────
GREETING_FILE = os.path.join(tempfile.gettempdir(), "jarvis_greeting.mp3")
RESPONSE_FILE = os.path.join(tempfile.gettempdir(), "jarvis_response.mp3")

# ──────────────────────────────────────────────────────────────────────────────
#  Global state
# ──────────────────────────────────────────────────────────────────────────────
clap_times: list[float] = []
triggered = False
lock = threading.Lock()
voice_sound = None
song_files: list[str] = []
in_conversation = False


# ──────────────────────────────────────────────────────────────────────────────
#  TTS helpers
# ──────────────────────────────────────────────────────────────────────────────
def generate_tts(text: str, output_path: str):
    """Generate speech audio file from text."""
    if ELEVENLABS_API_KEY:
        if generate_elevenlabs_tts(text, output_path):
            return
    generate_edge_tts(text, output_path)


def generate_edge_tts(text: str, output_path: str):
    """Generate speech with edge-tts."""
    import edge_tts
    async def _gen():
        comm = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        await comm.save(output_path)
    asyncio.run(_gen())


def generate_elevenlabs_tts(text: str, output_path: str) -> bool:
    """Generate speech with ElevenLabs API. Returns True on success."""
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
    """Play a voice audio file (blocks until done)."""
    sound = pygame.mixer.Sound(audio_path)
    channel = sound.play()
    while channel.get_busy():
        time.sleep(0.1)


# ──────────────────────────────────────────────────────────────────────────────
#  Startup
# ──────────────────────────────────────────────────────────────────────────────
def startup_init():
    """Pre-load everything at startup."""
    global song_files

    # Init pygame mixer
    pygame.mixer.init(frequency=44100)

    # Find all songs
    song_files = sorted(glob.glob(os.path.join(SONGS_DIR, "*.mp3")))
    if not song_files:
        print("  [ERROR] No songs found in songs/ directory!")
        print("  Run: python download_songs.py")
        sys.exit(1)

    print(f"  [INIT] Loaded {len(song_files)} songs:")
    for s in song_files:
        print(f"         - {os.path.basename(s)}")

    # Pre-generate a greeting
    greeting = random.choice(GREETINGS)
    print(f"  [INIT] Generating voice: \"{greeting[:50]}...\"")
    generate_tts(greeting, GREETING_FILE)
    print("  [INIT] Voice ready.")


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
            print(f"  [CLAP {count}/2]  RMS={rms:.3f}")

            if count >= 2:
                triggered = True
                clap_times = []
                threading.Thread(target=welcome_sequence, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
#  Welcome sequence
# ──────────────────────────────────────────────────────────────────────────────
def welcome_sequence():
    global in_conversation

    print()
    print("  ======================================")
    print("  J.A.R.V.I.S. ACTIVATED")
    print("  ======================================")
    print()

    # Pick a random song
    song = random.choice(song_files)
    song_name = os.path.basename(song).replace("_", " ").replace(".mp3", "").title()
    print(f"  [MUSIC] Playing: {song_name}")

    # Load and play song
    pygame.mixer.music.load(song)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play()

    # Wait, then speak
    time.sleep(VOICE_DELAY)

    # Pick and speak greeting
    greeting = random.choice(GREETINGS)
    print(f'  [JARVIS]: "{greeting}"')
    generate_tts(greeting, GREETING_FILE)
    play_voice(GREETING_FILE)

    # Open Claude Code
    time.sleep(1)
    open_claude_code()

    # Enter conversation mode
    print()
    print("  ======================================")
    print("  CONVERSATION MODE - Talk to Jarvis!")
    print("  Say \"goodbye Jarvis\" to exit")
    print("  ======================================")
    print()

    in_conversation = True
    conversation_loop()
    in_conversation = False

    # Fade out music if still playing
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.fadeout(3000)
        time.sleep(3)

    print()
    print("  ======================================")
    print("  JARVIS STANDING BY")
    print("  ======================================")
    print()


def open_claude_code():
    """Open a new terminal with Claude Code + --dangerously-skip-permissions."""
    print("  [CLAUDE CODE] Launching...")
    os.makedirs(PROJECT_DIR, exist_ok=True)

    try:
        subprocess.Popen(
            ["wt", "new-tab", "--title", "JARVIS - Claude Code",
             "cmd", "/k",
             f"cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"],
        )
        print("  [CLAUDE CODE] Opened in Windows Terminal")
    except FileNotFoundError:
        cmd = f'start "JARVIS - Claude Code" cmd /k "cd /d {PROJECT_DIR} && claude --dangerously-skip-permissions"'
        subprocess.Popen(cmd, shell=True)
        print("  [CLAUDE CODE] Opened in cmd")


# ──────────────────────────────────────────────────────────────────────────────
#  Conversation mode
# ──────────────────────────────────────────────────────────────────────────────
def conversation_loop():
    """Listen for voice input, respond as Jarvis."""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    conversation_history = []

    while True:
        # Listen for speech
        user_text = listen_for_speech(recognizer)
        if user_text is None:
            continue

        print(f'  [YOU]: "{user_text}"')

        # Check for exit phrases
        lower = user_text.lower()
        if any(phrase in lower for phrase in ["goodbye jarvis", "bye jarvis", "exit jarvis",
                                               "that's all jarvis", "stop jarvis", "shut down"]):
            farewell = "Very good sir. I'll be here if you need me. Just clap twice."
            print(f'  [JARVIS]: "{farewell}"')
            generate_tts(farewell, RESPONSE_FILE)
            play_voice(RESPONSE_FILE)
            break

        # Get Jarvis response via Claude
        response = get_jarvis_response(user_text, conversation_history)
        if response:
            print(f'  [JARVIS]: "{response}"')
            conversation_history.append({"role": "user", "content": user_text})
            conversation_history.append({"role": "assistant", "content": response})

            # Keep history manageable
            if len(conversation_history) > 20:
                conversation_history = conversation_history[-20:]

            # Speak it
            generate_tts(response, RESPONSE_FILE)
            play_voice(RESPONSE_FILE)


def listen_for_speech(recognizer: sr.Recognizer) -> str | None:
    """Listen to microphone and return recognized text, or None."""
    try:
        with sr.Microphone() as source:
            print("  [LISTENING...]", end="\r")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)

        print("  [PROCESSING...]", end="\r")
        text = recognizer.recognize_google(audio)
        return text
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"  [SPEECH ERROR]: {e}")
        return None
    except Exception:
        return None


def get_jarvis_response(user_input: str, history: list) -> str | None:
    """Get a Jarvis response using Claude CLI."""
    try:
        # Build the prompt with conversation history
        prompt_parts = []
        for msg in history[-10:]:  # last 10 messages for context
            role = "User" if msg["role"] == "user" else "Jarvis"
            prompt_parts.append(f"{role}: {msg['content']}")
        prompt_parts.append(f"User: {user_input}")
        prompt_parts.append("Jarvis:")

        full_prompt = f"{JARVIS_SYSTEM_PROMPT}\n\nConversation:\n" + "\n".join(prompt_parts)

        # Use claude CLI in print mode (already authenticated)
        result = subprocess.run(
            ["claude", "-p", full_prompt],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return "I'm afraid I encountered a slight hiccup, sir. Could you repeat that?"
    except subprocess.TimeoutExpired:
        return "Apologies sir, that took longer than expected. Do go on."
    except Exception as e:
        print(f"  [LLM ERROR]: {e}")
        return "My systems seem to be experiencing a brief interruption, sir."


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    global triggered

    print()
    print("  =============================================")
    print("  J.A.R.V.I.S. - Just A Rather Very Intelligent System")
    print("  =============================================")
    print()

    startup_init()

    print()
    print(f"  Clap detection threshold: {THRESHOLD}")
    print(f"  Voice: {'ElevenLabs' if ELEVENLABS_API_KEY else f'Edge-TTS ({EDGE_TTS_VOICE})'}")
    print(f"  Songs: {len(song_files)} loaded")
    print("  Conversation: Enabled (via Claude CLI)")
    print("  Ctrl+C to exit")
    print("  =============================================")
    print()
    print("  Listening for double clap...")
    print()

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
                if triggered:
                    # Wait for the welcome sequence + conversation to finish
                    while triggered or in_conversation:
                        time.sleep(1)
                    triggered = False
                    print("  Listening for double clap...\n")
    except KeyboardInterrupt:
        print("\n  Jarvis signing off. Goodbye, sir.")
        pygame.mixer.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
