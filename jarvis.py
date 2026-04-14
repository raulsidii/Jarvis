#!/usr/bin/env python3
"""
JARVIS - Double-clap activated AI assistant launcher.

Clap twice -> Music plays instantly -> Jarvis speaks -> Claude Code opens.

All audio is pre-loaded at startup for instant playback. No browser loading delay.

Dependencies:
    pip install sounddevice numpy edge-tts pygame requests

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

import numpy as np
import sounddevice as sd
import pygame

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

# What Jarvis says
GREETING = "Welcome home sir. All systems are online. Claude Code is ready for your command."

# Music settings
MUSIC_VOLUME = 0.25  # 0.0 to 1.0 — lower so Jarvis voice is clear over it
VOICE_DELAY  = 2.0   # seconds to wait after music starts before Jarvis speaks

# Where Claude Code opens
PROJECT_DIR = os.path.expanduser("~/jarvis")

# ──────────────────────────────────────────────────────────────────────────────
#  File paths (pre-generated at startup)
# ──────────────────────────────────────────────────────────────────────────────
MUSIC_FILE    = os.path.join(os.path.dirname(__file__), "music.mp3")
GREETING_FILE = os.path.join(tempfile.gettempdir(), "jarvis_greeting.mp3")

# ──────────────────────────────────────────────────────────────────────────────
#  Global state
# ──────────────────────────────────────────────────────────────────────────────
clap_times: list[float] = []
triggered = False
lock = threading.Lock()
voice_sound = None  # pygame Sound object, loaded at startup


# ──────────────────────────────────────────────────────────────────────────────
#  Startup: pre-generate all audio
# ──────────────────────────────────────────────────────────────────────────────
def startup_init():
    """Pre-generate greeting audio and init pygame so everything is instant."""
    global voice_sound

    # Init pygame mixer
    pygame.mixer.init(frequency=44100)

    # Check music file exists
    if not os.path.exists(MUSIC_FILE):
        print("  [ERROR] music.mp3 not found! Run the download script first.")
        print(f"  Expected at: {MUSIC_FILE}")
        sys.exit(1)

    # Pre-load music
    pygame.mixer.music.load(MUSIC_FILE)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    print("  [INIT] Music loaded.")

    # Generate greeting audio
    if ELEVENLABS_API_KEY:
        generate_elevenlabs_greeting()
    else:
        generate_edge_tts_greeting()

    # Pre-load voice as a Sound object (plays on separate channel from music)
    voice_sound = pygame.mixer.Sound(GREETING_FILE)
    print("  [INIT] Voice loaded. Ready to go.")


def generate_edge_tts_greeting():
    """Generate greeting with edge-tts."""
    import edge_tts
    print("  [INIT] Generating Jarvis voice with edge-tts...")
    async def _gen():
        comm = edge_tts.Communicate(GREETING, EDGE_TTS_VOICE)
        await comm.save(GREETING_FILE)
    asyncio.run(_gen())
    print("  [INIT] Voice ready.")


def generate_elevenlabs_greeting():
    """Generate greeting with ElevenLabs API."""
    import requests
    print("  [INIT] Generating Jarvis voice with ElevenLabs...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": GREETING,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.85},
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code == 200:
        with open(GREETING_FILE, "wb") as f:
            f.write(resp.content)
        print("  [INIT] ElevenLabs voice ready.")
    else:
        print(f"  [INIT] ElevenLabs failed ({resp.status_code}), using edge-tts...")
        generate_edge_tts_greeting()


# ──────────────────────────────────────────────────────────────────────────────
#  Clap detection
# ──────────────────────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    global triggered, clap_times

    if triggered:
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
    print()
    print("  ======================================")
    print("  J.A.R.V.I.S. ACTIVATED")
    print("  ======================================")
    print()

    # Step 1: Music plays INSTANTLY (already loaded in memory)
    print("  [MUSIC] Playing...")
    pygame.mixer.music.play()

    # Step 2: Wait a beat, then Jarvis speaks OVER the music
    time.sleep(VOICE_DELAY)
    print(f'  [JARVIS]: "{GREETING}"')
    voice_sound.play()

    # Step 3: Wait for voice to finish, then open Claude Code
    time.sleep(5)
    open_claude_code()

    # Wait for the full song to finish
    while pygame.mixer.music.get_busy():
        time.sleep(1)

    print()
    print("  ======================================")
    print("  SEQUENCE COMPLETE")
    print("  ======================================")
    print()

    # Reload music for next trigger
    pygame.mixer.music.load(MUSIC_FILE)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)


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
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    global triggered

    print()
    print("  =============================================")
    print("  J.A.R.V.I.S. - Just A Rather Very Intelligent System")
    print("  =============================================")
    print()

    # Pre-load everything at startup
    startup_init()

    print()
    print(f"  Listening for double clap... (threshold: {THRESHOLD})")
    print(f"  Voice: {'ElevenLabs' if ELEVENLABS_API_KEY else f'Edge-TTS ({EDGE_TTS_VOICE})'}")
    print("  Ctrl+C to exit")
    print("  =============================================")
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
                    time.sleep(20)
                    triggered = False
                    print("  [LISTENING] Waiting for double clap...\n")
    except KeyboardInterrupt:
        print("\n  Jarvis signing off. Goodbye, sir.")
        pygame.mixer.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
